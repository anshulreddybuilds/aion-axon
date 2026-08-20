from typing import Callable, Any

from app.governance.guardian import guardian, RiskLevel, Decision
from app.governance.approval import approval_manager
from app.governance.kill_switch import kill_switch
from app.memory.firestore_store import firestore_store


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

        decision = guardian.evaluate(action, risk)

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

        try:
            result = tool(*args, **kwargs)

            firestore_store.write_audit_event(
                "ACTION_EXECUTED",
                {
                    "action": action,
                    "risk": risk.value,
                    "result": str(result),
                },
            )

            return {
                "status": "EXECUTED",
                "result": result,
            }

        except Exception as exc:
            firestore_store.write_audit_event(
                "ACTION_FAILED",
                {
                    "action": action,
                    "risk": risk.value,
                    "error": str(exc),
                },
            )

            return {
                "status": "FAILED",
                "error": str(exc),
            }


execution_gate = ExecutionGate()
