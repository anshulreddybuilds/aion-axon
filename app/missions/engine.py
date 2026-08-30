"""Executes a MissionPlan step by step, through the gate, with state.

Design constraints that are not negotiable:

- Every step executes via ExecutionGate. The engine resolves and orders
  work; it never calls a tool function directly.
- A step that needs a capability AION does not have does not fail and
  does not get skipped. The mission goes BLOCKED at that step and records
  the gap. Phase 4 turns that record into an Evolution Event and wakes
  SYNAPSE.
- A step needing approval suspends the mission at that exact step. On
  resume the engine continues from there rather than replaying completed
  steps, because replaying an EXTERNAL_EFFECT step would perform it twice.
"""
import inspect
import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from app.agents.plan_schema import MissionPlan, MissionStep
from app.capabilities.registry import registry
from app.governance.guardian import RiskLevel
from app.memory.firestore_store import firestore_store
from app.workflows.orchestrator import orchestrator
from app.workflows.state import WorkflowState


class MissionEngine:

    def run(
        self,
        workflow: WorkflowState,
        plan: MissionPlan,
        start_at: int = 0,
        completed: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """Execute plan steps from `start_at`.

        Returns a summary describing where the mission stopped and why.
        """
        results: list[dict[str, Any]] = list(completed or [])

        for index in range(start_at, len(plan.steps)):
            step = plan.steps[index]

            gap = self._gap_for(step)

            if gap is not None:
                workflow.update_status("BLOCKED")
                workflow.add_observation("capability_gap", gap)

                firestore_store.write_audit_event("CAPABILITY_GAP", gap)

                return self._summary(
                    "BLOCKED", results, index, plan,
                    blocked_on=gap,
                )

            # BUG-018, 30 Aug 2026: the natural-language "Plan it" flow
            # (POST /missions/planned) planned a step naming an EXISTING,
            # already-registered capability (generate_nepal_crisis_image --
            # the same capability BUG-014 was found on) but left `args: []`,
            # the schema's own default (app/agents/plan_schema.py). BUG-014's
            # fix already turns the resulting call into one clean sentence
            # instead of a crash, but the mission still never completes --
            # which is exactly resume_blocked()'s own already-documented
            # "Found live 21 Aug" failure, just reached from the first-run
            # path instead of the capability-gap resume path it was
            # originally fixed for. Root cause: the planner's prompt
            # (mission_planner.INSTRUCTION, rule 5) only spells out argument
            # shape for calculator and web_research by name, and a
            # SYNAPSE-acquired capability's catalog entry carries no
            # signature at all -- its registered function is always
            # `_sandbox_proxy`'s bare `invoke(*args)`, so
            # `declarations._signature_of()` deliberately returns "" for it
            # rather than a misleading `(*args)`. The planner was never told
            # this capability takes an argument, so it could not have
            # written one.
            #
            # Same backfill as resume_blocked(), same justification: the
            # mission's own free-text request is the only material this
            # step was ever given, so it becomes the sole positional arg --
            # only when args are still empty, never overwriting an explicit
            # one. Unlike resume_blocked() (which only ever backfills a step
            # whose tool was just installed for it), this runs for every
            # first-run step, so it is gated on the capability's own known
            # minimum argument count: a capability KNOWN to take zero
            # arguments must never be force-fed one it never asked for --
            # that would trade BUG-018 for a new, self-inflicted arity
            # error. An UNKNOWN minimum (can't be determined by static
            # reading) is treated as "needs at least one", matching
            # resume_blocked()'s own unconditional backfill for the one
            # case it handles.
            if not step.args:
                minimum = self._minimum_args_required(step.tool)

                if minimum is None or minimum > 0:
                    step.args = [workflow.user_request]

            args = self._resolve_args(step.args, results)

            outcome = orchestrator.execute_tool(
                workflow,
                step.tool,
                step.action,
                RiskLevel(step.risk),
                *args,
                # The action label is short and often innocuous; the real
                # intent usually lives in the description. Guardian must
                # see both, or a prohibited request can hide behind a
                # bland label.
                description=step.description,
                capability=step.tool,
            )

            status = outcome.get("status")

            record = {
                "step": step.step,
                "description": step.description,
                "tool": step.tool,
                "action": step.action,
                "risk": step.risk,
                "kind": step.kind,
                "status": status,
                "result": outcome.get("result"),
                "at": datetime.now(timezone.utc).isoformat(),
            }

            if status == "EXECUTED":
                # EXECUTED means the GATE ran the tool, not that the tool
                # succeeded. A capability that returns
                # {"status": "ERROR", ...} ran perfectly well and failed at
                # its job, and those are different facts.
                #
                # Found live 22 Aug in the first Phase 8 fire drill: the
                # BigQuery step hit a byte cap and errored, the analysis
                # step then errored on the empty input, and the mission
                # still marched to COMPLETED and produced a confident
                # Business Action Brief built from nothing. Every step was
                # "EXECUTED"; nobody read what they returned.
                #
                # That is the exact failure this project exists to argue
                # against — not a crash, but something that looks like
                # success. A mission that cannot do the job must say so.
                tool_error = self._tool_error(outcome.get("result"))

                if tool_error is not None:
                    results.append({**record, "status": "FAILED",
                                    "reason": tool_error})

                    workflow.update_status("FAILED")

                    firestore_store.write_audit_event("STEP_FAILED", {
                        "step": step.step,
                        "tool": step.tool,
                        "error": tool_error,
                    })

                    return self._summary("FAILED", results, index, plan)

                # The orchestrator already verified and recorded the
                # outcome. Read its verdict; never recompute it, or one
                # action would move autonomy twice.
                evidence = outcome.get("evidence")

                if evidence:
                    record["evidence"] = evidence

                results.append(record)
                continue

            # Anything that is not EXECUTED stops the mission here.
            # Approval suspends it; refusal and blocking end it.
            #
            # BUG-007: a step whose tool raised a real exception (a bug
            # in the capability's own code, not a `{"status": "ERROR"}`
            # return value -- that case is handled above via
            # _tool_error()) reaches execution_gate._execute_tool()'s
            # exception handler, which reports the message under
            # "error", not "reason". Reading only "reason" here silently
            # dropped it -- a mission would report FAILED (honest, no
            # fabricated success) but with `"reason": null`, even though
            # the real exception text was sitting one key over the whole
            # time. Found by actually raising a real exception inside a
            # capability and reading the resulting step_results, the
            # same way BUG-005's swallowed "reason"/"error" mismatch was
            # found in the approval-resume path.
            results.append({
                **record,
                "reason": outcome.get("reason") or outcome.get("error"),
            })

            if status == "APPROVAL_REQUIRED":
                return self._summary(
                    "AWAITING_APPROVAL", results, index, plan,
                    approval_request_id=outcome.get("request_id"),
                )

            return self._summary(status or "UNKNOWN", results, index, plan)

        workflow.update_status("COMPLETED")

        return self._summary("COMPLETED", results, len(plan.steps), plan)

    @staticmethod
    def _resolve_args(
        args: list[str], results: list[dict[str, Any]],
    ) -> list[str]:
        """Substitute `$STEP_n` with step n's actual output.

        Without this, every step receives static strings the planner wrote
        before any of them ran, so a three-step mission is really three
        unrelated missions. Found live 22 Aug: the fire drill's brief was
        built from the planner's own description of step 3 rather than
        from the anomalies step 2 was supposed to find.

        The reference is explicit rather than inferred. Silently feeding
        each step the previous one's output would guess wrong the moment a
        plan branches, and a wrong guess here is invisible — it produces a
        plausible answer to the wrong question.

        An unresolvable reference is left untouched rather than blanked,
        so it surfaces as a visibly wrong argument instead of a quietly
        empty one.
        """
        by_step = {r.get("step"): r for r in results}

        def value_of(n: int, path: Optional[str]) -> Optional[str]:
            record = by_step.get(n)

            if record is None:
                return None

            result = record.get("result")
            inner = result.get("result") if isinstance(result, dict) else None
            payload = inner if isinstance(inner, dict) else result

            if payload is None:
                return None

            # `$STEP_1.rows` reaches inside the envelope. Capabilities
            # return {status, rows, row_count, ...}, so passing the whole
            # object to one that wants the rows fails on a type it was
            # never offered -- which is precisely how the second fire
            # drill died: "JSON input must be a list of records".
            if path:
                for part in path.split("."):
                    if isinstance(payload, dict) and part in payload:
                        payload = payload[part]
                    else:
                        return None

            return (
                payload if isinstance(payload, str)
                else json.dumps(payload, default=str)
            )

        def substitute(arg: Any) -> Any:
            if not isinstance(arg, str):
                return arg

            def repl(match: "re.Match[str]") -> str:
                resolved = value_of(int(match.group(1)), match.group(2))
                return match.group(0) if resolved is None else resolved

            return re.sub(
                r"\$STEP_(\d+)(?:\.([A-Za-z_][A-Za-z0-9_.]*))?", repl, arg
            )

        return [substitute(a) for a in args]

    @staticmethod
    def _tool_error(result: Any) -> Optional[str]:
        """Return the tool's own error message, or None if it succeeded.

        Capabilities report failure in their return value rather than by
        raising, because generated code runs in the sandbox and a raised
        exception there is not an exception here. That convention is fine
        — but it means a caller who only checks the gate's status learns
        nothing about whether the work actually happened.
        """
        if not isinstance(result, dict):
            return None

        # Sandbox-proxied capabilities nest their payload one level down.
        inner = result.get("result")
        target = inner if isinstance(inner, dict) else result

        if target.get("status") == "ERROR":
            return str(target.get("error") or "Capability reported ERROR.")

        return None

    @staticmethod
    def _minimum_args_required(tool_name: str) -> Optional[int]:
        """Best-effort minimum positional-arg count for `tool_name`.

        Returns None when it can't be determined. BUG-018's backfill above
        treats that the same as "needs at least one" -- the only case worth
        guarding against is a capability KNOWN to need zero, and an unknown
        minimum is not that.

        A SYNAPSE-acquired capability's registered function is always
        `_sandbox_proxy`'s own `invoke(*args)` closure -- its Python
        signature reveals nothing, on purpose, the same reason
        `declarations._signature_of()` returns "" for these rather than a
        misleading `(*args)`. The real shape lives in the generated source
        Firestore still holds for it (`passport.candidate.code` /
        `.entrypoint`, the same record `rehydrate.py` reads to re-register
        it after a restart), so it's read the same static way
        `SynapseEngine._entrypoint_arity` already reads it for the exact
        same reason -- see that method and BUG-014's fix in
        `_sandbox_proxy`, this same class of problem one layer down.

        A hand-written seed capability (calculator, web_research, ...) IS
        its own real function, so `inspect.signature` on it is enough, the
        same way `declarations._signature_of()` already relies on it for
        the planner's catalog.
        """
        # Imported locally: rehydrate.py already sets the precedent for
        # reaching synapse.engine lazily from this layer rather than
        # risking a cycle at module load ("synapse.engine imports the
        # registry, and the registry must not import synapse").
        from app.synapse.engine import synapse

        stored = firestore_store.get_capability(tool_name) or {}
        candidate = (stored.get("passport") or {}).get("candidate") or {}
        code = candidate.get("code")
        entrypoint = candidate.get("entrypoint")

        if code and entrypoint:
            arity = synapse._entrypoint_arity(code, entrypoint)

            if arity is not None:
                return arity[0]

        tool = registry.describe(tool_name)

        if tool is None or tool.function is None:
            return None

        try:
            parameters = inspect.signature(tool.function).parameters
        except (TypeError, ValueError):  # builtins and C callables
            return None

        if any(
            p.kind is inspect.Parameter.VAR_POSITIONAL
            for p in parameters.values()
        ):
            # `*args` alone -- the sandbox proxy's own shape, or a
            # genuinely variadic seed function -- says nothing about how
            # many are actually required. Indeterminate, not zero.
            return None

        return sum(
            1 for p in parameters.values()
            if p.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
            and p.default is inspect.Parameter.empty
        )

    def _gap_for(self, step: MissionStep) -> Optional[dict[str, Any]]:
        """Describe the capability gap at this step, if there is one."""
        if step.tool is None:
            return {
                "step": step.step,
                "description": step.description,
                "missing_capability": None,
                "reason": (
                    "The planner found no registered capability for this "
                    "step."
                ),
                "detected_at": datetime.now(timezone.utc).isoformat(),
            }

        described = registry.describe(step.tool)

        if described is None:
            return {
                "step": step.step,
                "description": step.description,
                "missing_capability": step.tool,
                "reason": f"Capability '{step.tool}' is not registered.",
                "detected_at": datetime.now(timezone.utc).isoformat(),
            }

        if not described.implemented:
            return {
                "step": step.step,
                "description": step.description,
                "missing_capability": step.tool,
                "reason": (
                    f"Capability '{step.tool}' is declared but has no "
                    "implementation."
                ),
                "capability_description": described.description,
                "detected_at": datetime.now(timezone.utc).isoformat(),
            }

        return None

    def _summary(
        self,
        status: str,
        results: list[dict[str, Any]],
        index: int,
        plan: MissionPlan,
        approval_request_id: Optional[str] = None,
        blocked_on: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "steps_completed": len(
                [r for r in results if r.get("status") == "EXECUTED"]
            ),
            "steps_total": len(plan.steps),
            "next_step_index": index,
            "step_results": results,
            "approval_request_id": approval_request_id,
            "blocked_on": blocked_on,
        }


mission_engine = MissionEngine()
