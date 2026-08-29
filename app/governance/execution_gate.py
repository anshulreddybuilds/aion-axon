from typing import Callable, Any

from app.governance.guardian import guardian, RiskLevel, Decision
from app.governance.approval import approval_manager
from app.governance.kill_switch import kill_switch
from app.memory.firestore_store import firestore_store
from app.observability.telemetry import timed


class ExecutionGate:
    def execute(
        self,
        action: str,
        risk: RiskLevel,
        tool: Callable[..., Any],
        *args,
        description: str | None = None,
        capability: str | None = None,
        **kwargs,
    ) -> dict:

        if kill_switch.is_active():
            firestore_store.write_audit_event(
                "EXECUTION_BLOCKED",
                {
                    "action": action,
                    "risk": risk.value,
                    "reason": "Kill switch active",
                },
            )

            return {
                "status": "BLOCKED",
                "reason": "Kill switch is active.",
            }

        decision = guardian.evaluate(
            action,
            risk,
            description=description,
            capability=capability,
        )

        firestore_store.write_audit_event(
            "GUARDIAN_DECISION",
            {
                "action": action,
                "risk": risk.value,
                "decision": decision.decision.value,
                "reason": decision.reason,
                "policy_id": decision.policy_id,
                "policy_title": decision.policy_title,
            },
        )

        if decision.decision == Decision.REFUSE:
            return {
                "status": "REFUSED",
                "reason": decision.reason,
                "policy_id": decision.policy_id,
                "policy_title": decision.policy_title,
                "rationale": decision.rationale,
            }

        if decision.decision == Decision.APPROVAL_REQUIRED:
            request = approval_manager.create(
                action=action,
                risk=risk,
                reason=decision.reason,
                policy_id=decision.policy_id,
                capability=capability,
            )

            return {
                "status": "APPROVAL_REQUIRED",
                "request_id": request.request_id,
                "action": action,
                "risk": risk.value,
                "reason": decision.reason,
                "policy_id": decision.policy_id,
                "policy_title": decision.policy_title,
            }

        return self._execute_tool(
            action,
            risk,
            tool,
            *args,
            **kwargs,
        )

    def execute_approved(
        self,
        action: str,
        risk: RiskLevel,
        tool: Callable[..., Any],
        approval_request_id: str,
        *args,
        description: str | None = None,
        capability: str | None = None,
        **kwargs,
    ) -> dict:

        if kill_switch.is_active():
            firestore_store.write_audit_event(
                "APPROVED_EXECUTION_BLOCKED",
                {
                    "action": action,
                    "risk": risk.value,
                    "approval_request_id": approval_request_id,
                    "reason": "Kill switch active.",
                },
            )

            return {
                "status": "BLOCKED",
                "reason": "Kill switch is active.",
            }

        approval = firestore_store.get_approval(approval_request_id)

        if approval is None:
            return {
                "status": "FAILED",
                "error": "Approval request not found in Firestore.",
            }

        if approval.get("status") != "APPROVED":
            return {
                "status": "APPROVAL_REQUIRED",
                "request_id": approval_request_id,
                "reason": (
                    f"Approval status is {approval.get('status', 'UNKNOWN')}."
                ),
            }

        # The re-check must be at least as strong as execute()'s original
        # check, or it is theatre: this is the path that actually runs the
        # tool. Passing only `action` meant the policy catalog -- which
        # matches across action AND description AND capability
        # (find_policy) -- saw just the short, often innocuous label, so a
        # prohibited intent carried in the description was screened on the
        # unapproved path and NOT on the approved one. It also left
        # Guardian's G-07 autonomy-demotion branch (`if capability and
        # ...`) permanently dead here, because `capability` was always
        # None -- a demoted capability was re-checked as if it were still
        # fully trusted, precisely when a human had just said yes.
        #
        # Both fall back to the approval record itself, which already
        # persists `capability` and `reason`, so callers that predate
        # these arguments are covered too rather than silently keeping
        # the weaker check.
        capability = capability or approval.get("capability")
        description = description or approval.get("reason")

        decision = guardian.evaluate(
            action,
            risk,
            description=description,
            capability=capability,
        )

        firestore_store.write_audit_event(
            "APPROVED_EXECUTION_GUARDIAN_RECHECK",
            {
                "action": action,
                "risk": risk.value,
                "approval_request_id": approval_request_id,
                "decision": decision.decision.value,
                "reason": decision.reason,
            },
        )

        if decision.decision == Decision.REFUSE:
            return {
                "status": "REFUSED",
                "reason": decision.reason,
            }

        if decision.decision == Decision.APPROVAL_REQUIRED:
            firestore_store.write_audit_event(
                "APPROVED_EXECUTION_AUTHORIZED",
                {
                    "action": action,
                    "risk": risk.value,
                    "approval_request_id": approval_request_id,
                    "approved_by": approval.get("decided_by"),
                },
            )

        return self._execute_tool(
            action,
            risk,
            tool,
            *args,
            **kwargs,
        )

    def _execute_tool(
        self,
        action: str,
        risk: RiskLevel,
        tool: Callable[..., Any],
        *args,
        **kwargs,
    ) -> dict:

        # Timed here because this is the ONE place a tool actually runs.
        # Measuring anywhere else would miss a path, and a latency number
        # that silently excludes some executions is worse than none.
        with timed() as clock:
            try:
                result = tool(*args, **kwargs)
                failure = None
            except Exception as exc:  # noqa: BLE001 - reported, not raised
                result = None
                failure = exc

        if failure is None:
            firestore_store.write_audit_event(
                "ACTION_EXECUTED",
                {
                    "action": action,
                    "risk": risk.value,
                    "result": str(result),
                    "duration_ms": round(clock["ms"], 1),
                },
            )

            return {
                "status": "EXECUTED",
                "result": result,
                "duration_ms": round(clock["ms"], 1),
            }

        firestore_store.write_audit_event(
            "ACTION_FAILED",
            {
                "action": action,
                "risk": risk.value,
                "error": str(failure),
                "duration_ms": round(clock["ms"], 1),
            },
        )

        return {
            "status": "FAILED",
            "error": str(failure),
            "duration_ms": round(clock["ms"], 1),
        }


execution_gate = ExecutionGate()
