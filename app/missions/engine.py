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
            results.append({**record, "reason": outcome.get("reason")})

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
