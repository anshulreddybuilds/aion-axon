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
        **kwargs,
    ) -> dict:

        # 1. Emergency stop
        if kill_switch.is_active():
            firestore_store.write_audit_event(
                "EXECUTION_BLOCKED",
                {
                    "action": action,
                    "reason": "Kill switch active",
                },
            )

            return {
                "status": "BLOCKED",
                "reason": "Kill switch is active.",
            }

        # 2. Guardian decision
        decision = guardian.evaluate(action, risk)

        firestore_store.write_audit_event(
            "GUARDIAN_DECISION",
            {
                "action": action,
                "risk": risk.value,
                "decision": decision.decision.value,
                "reason": decision.reason,
            },
        )

        # 3. Refuse dangerous action
        if decision.decision == Decision.REFUSE:
            return {
                "status": "REFUSED",
                "reason": decision.reason,
            }

        # 4. Require human approval
        if decision.decision == Decision.APPROVAL_REQUIRED:

            request = approval_manager.create(
                action=action,
                risk=risk,
                reason=decision.reason,
            )

            firestore_store.create_approval(
                request.request_id,
                {
                    "action": action,
                    "risk": risk.value,
                    "reason": decision.reason,
                },
            )

            return {
                "status": "APPROVAL_REQUIRED",
                "request_id": request.request_id,
                "action": action,
                "risk": risk.value,
                "reason": decision.reason,
            }

        # 5. Execute low-risk action
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
                    "error": str(exc),
                },
            )

            return {
                "status": "FAILED",
                "error": str(exc),
            }


execution_gate = ExecutionGate()
