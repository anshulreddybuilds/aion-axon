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
from datetime import datetime, timezone
from typing import Any, Optional

from app.agents.plan_schema import MissionPlan, MissionStep
from app.capabilities.registry import registry
from app.governance.autonomy_ledger import autonomy_ledger
from app.governance.evidence_engine import VERIFIED_VERDICT, verify_research
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

            outcome = orchestrator.execute_tool(
                workflow,
                step.tool,
                step.action,
                RiskLevel(step.risk),
                *step.args,
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
                evidence = self._verify(step, outcome.get("result"))

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

    def _verify(
        self,
        step: MissionStep,
        result: Any,
    ) -> Optional[dict[str, Any]]:
        """Check a completed step's claim against evidence, and score it.

        Scoped to web_research per Amendment 7 P0. This is the point where
        the agent's own "EXECUTED" stops being the last word: the gate
        says the step ran, the Evidence Engine says whether what it
        produced can be believed, and the ledger moves autonomy on the
        answer.

        A verification failure must never fail the mission. The step did
        run; what changed is how much the agent is trusted next time.
        """
        if step.tool != "web_research" or not isinstance(result, dict):
            return None

        try:
            report = verify_research(result)

            change = autonomy_ledger.record_outcome(
                "web_research",
                verified=report.verdict == VERIFIED_VERDICT,
                reason=(
                    report.contradiction_detail
                    or f"Evidence verdict: {report.verdict}"
                ),
            )

            return {
                "verdict": report.verdict,
                "confidence": report.confidence,
                "checklist": report.checklist,
                "grounded": report.grounded,
                "source_count": report.source_count,
                "autonomy_before": change.before,
                "autonomy_after": change.after,
                "oversight_restored": change.oversight_restored,
            }
        except Exception as error:  # noqa: BLE001 - never fail the mission
            return {"verdict": "UNVERIFIED", "error": str(error)}

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
