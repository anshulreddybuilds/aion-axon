from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from .guardian import RiskLevel


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
        self.pending: dict[str, ApprovalRequest] = {}

    def create(
        self,
        action: str,
        risk: RiskLevel,
        reason: str,
    ) -> ApprovalRequest:
        request = ApprovalRequest(
            action=action,
            risk=risk,
            reason=reason,
        )
        self.pending[request.request_id] = request
        return request

    def decide(
        self,
        request_id: str,
        approved: bool,
        decided_by: str = "human",
    ) -> ApprovalRequest:
        request = self.pending[request_id]

        if approved:
            request.approve(decided_by)
        else:
            request.reject(decided_by)

        return request

    def get(self, request_id: str) -> Optional[ApprovalRequest]:
        return self.pending.get(request_id)


approval_manager = ApprovalManager()
