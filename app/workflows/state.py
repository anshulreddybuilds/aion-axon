from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4


@dataclass
class WorkflowState:
    user_request: str
    workflow_id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "PLANNING"

    plan: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    proposed_actions: list[dict[str, Any]] = field(default_factory=list)

    approval_request_id: Optional[str] = None

    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None

    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def update_status(self, status: str) -> None:
        self.status = status
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_observation(self, source: str, data: Any) -> None:
        self.observations.append({
            "source": source,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def add_action(
        self,
        action: str,
        risk: str,
        description: str,
    ) -> None:
        self.proposed_actions.append({
            "action": action,
            "risk": risk,
            "description": description,
        })


def create_workflow(user_request: str) -> WorkflowState:
    return WorkflowState(user_request=user_request)
