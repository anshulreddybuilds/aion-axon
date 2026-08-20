from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from .guardian import RiskLevel
from app.memory.firestore_store import firestore_store


@dataclass
class ApprovalRequest:
    action: str
    risk: RiskLevel
    reason: str
    request_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    approved: Optional[bool] = None
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None

    # Which policy demanded this approval, and for which capability. G-07
    # asks the human to VERIFY a capability, so the answer has to be
    # recorded as evidence -- otherwise the same question is asked again
    # on the very next call and the gate becomes a treadmill.
    policy_id: Optional[str] = None
    capability: Optional[str] = None

    @property
    def pending(self) -> bool:
        return self.approved is None

    def approve(self, decided_by: str = "human") -> None:
        self.approved = True
        self.decided_by = decided_by
        self.decided_at = datetime.now(timezone.utc).isoformat()

    def reject(self, decided_by: str = "human") -> None:
        self.approved = False
        self.decided_by = decided_by
        self.decided_at = datetime.now(timezone.utc).isoformat()


class ApprovalManager:

    def __init__(self):
        # Local cache only.
        # Firestore is the persistent source of truth.
        self.pending: dict[str, ApprovalRequest] = {}

    def create(
        self,
        action: str,
        risk: RiskLevel,
        reason: str,
        policy_id: Optional[str] = None,
        capability: Optional[str] = None,
    ) -> ApprovalRequest:

        request = ApprovalRequest(
            action=action,
            risk=risk,
            reason=reason,
            policy_id=policy_id,
            capability=capability,
        )

        self.pending[request.request_id] = request

        firestore_store.create_approval(
            request.request_id,
            {
                "action": request.action,
                "risk": request.risk.value,
                "reason": request.reason,
                "policy_id": request.policy_id,
                "capability": request.capability,
            },
        )

        return request

    def get(
        self,
        request_id: str,
    ) -> Optional[ApprovalRequest]:

        # Firestore is the persistent source of truth.
        data = firestore_store.get_approval(request_id)

        if data is not None:
            status = data.get("status", "PENDING")

            approved = None

            if status == "APPROVED":
                approved = True
            elif status == "REJECTED":
                approved = False

            request = ApprovalRequest(
                action=data["action"],
                risk=RiskLevel(data["risk"]),
                reason=data["reason"],
                request_id=request_id,
                created_at=data.get(
                    "created_at",
                    datetime.now(timezone.utc).isoformat(),
                ),
                approved=approved,
                decided_at=data.get("decided_at"),
                decided_by=data.get("decided_by"),
                policy_id=data.get("policy_id"),
                capability=data.get("capability"),
            )

            self.pending[request_id] = request

            return request

        # Fall back to local cache only if Firestore has no record.
        return self.pending.get(request_id)

    def decide(
        self,
        request_id: str,
        approved: bool,
        decided_by: str = "human",
    ) -> ApprovalRequest:

        request = self.get(request_id)

        if request is None:
            raise KeyError(
                f"Unknown approval request: {request_id}"
            )

        if not request.pending:
            raise ValueError(
                f"Approval request {request_id} has already been decided."
            )

        if approved:
            request.approve(decided_by)
        else:
            request.reject(decided_by)

        firestore_store.update_approval(
            request_id,
            approved=approved,
            decided_by=decided_by,
        )

        firestore_store.write_audit_event(
            "HUMAN_APPROVAL_DECISION",
            {
                "request_id": request_id,
                "approved": approved,
                "decided_by": decided_by,
                "action": request.action,
                "risk": request.risk.value,
                "policy_id": request.policy_id,
                "capability": request.capability,
            },
        )

        # G-07 asked the human to VERIFY a capability. Recording the answer
        # is what stops the gate asking the same question forever: without
        # this the capability stays below the threshold and is held again
        # on the very next call, which trains the owner to click without
        # reading -- the exact failure the gate exists to prevent.
        #
        # Imported here: autonomy_ledger reads firestore_store, and this
        # module is imported by the gate.
        if request.policy_id == "G-07" and request.capability:
            from app.governance.autonomy_ledger import autonomy_ledger

            autonomy_ledger.record_outcome(
                request.capability,
                verified=approved,
                reason=(
                    f"Human verification under G-07 by {decided_by}: "
                    f"{'approved' if approved else 'rejected'}."
                ),
                intervened=True,
            )

        return request


approval_manager = ApprovalManager()
