"""Mission lifecycle, persisted so approval-resume survives a restart.

Cloud Run is multi-instance and scales to zero. An in-memory mission store
would make the approval demo fail the moment the request that approves a
mission lands on a different instance than the one that created it, so
mission state goes to Firestore alongside the approval record.

This layer NEVER executes anything itself. Every execution goes through
the orchestrator and therefore through the Unified Execution Gate.
"""
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import app.capabilities.bootstrap  # noqa: F401 - registers default tools
from app.governance.guardian import RiskLevel
from app.memory.firestore_store import firestore_store
from app.workflows.orchestrator import orchestrator
from app.workflows.state import WorkflowState


class MissionService:

    def start(
        self,
        request: str,
        tool: str,
        action: str,
        risk: str,
        args: Optional[list[Any]] = None,
    ) -> dict[str, Any]:

        args = args or []
        risk_level = RiskLevel(risk)

        workflow = orchestrator.create_workflow(request)

        result = orchestrator.execute_tool(
            workflow,
            tool,
            action,
            risk_level,
            *args,
        )

        mission_id = str(uuid4())

        self._persist(mission_id, workflow, tool, action, risk, args, result)

        return {
            "mission_id": mission_id,
            "workflow_id": workflow.workflow_id,
            "status": workflow.status,
            "result": result,
            "approval_request_id": workflow.approval_request_id,
            "plan": self._plan_of(workflow),
        }

    def resume(self, mission_id: str) -> dict[str, Any]:
        mission = firestore_store.get_mission(mission_id)

        if mission is None:
            return {"status": "FAILED", "error": "Unknown mission."}

        if mission.get("status") != "AWAITING_APPROVAL":
            return {
                "status": "FAILED",
                "error": (
                    "Mission is not awaiting approval. "
                    f"Current status: {mission.get('status')}"
                ),
            }

        # Rebuild just enough workflow state to resume. The gate re-reads
        # the approval from Firestore regardless, so this cannot be used
        # to fake an approval.
        workflow = WorkflowState(
            user_request=mission["request"],
            workflow_id=mission["workflow_id"],
        )
        workflow.status = "AWAITING_APPROVAL"
        workflow.approval_request_id = mission["approval_request_id"]

        result = orchestrator.approve_and_resume(
            workflow,
            mission["tool"],
            mission["action"],
            RiskLevel(mission["risk"]),
            mission["approval_request_id"],
            *mission.get("args", []),
        )

        self._persist(
            mission_id,
            workflow,
            mission["tool"],
            mission["action"],
            mission["risk"],
            mission.get("args", []),
            result,
        )

        return {
            "mission_id": mission_id,
            "workflow_id": workflow.workflow_id,
            "status": workflow.status,
            "result": result,
        }

    def get(self, mission_id: str) -> Optional[dict[str, Any]]:
        return firestore_store.get_mission(mission_id)

    def _plan_of(self, workflow: WorkflowState) -> Optional[str]:
        for observation in workflow.observations:
            data = observation.get("data") or {}
            if observation.get("source") == "planner":
                return data.get("plan")
        return None

    def _persist(
        self,
        mission_id: str,
        workflow: WorkflowState,
        tool: str,
        action: str,
        risk: str,
        args: list[Any],
        result: dict[str, Any],
    ) -> None:
        firestore_store.save_mission(mission_id, {
            "mission_id": mission_id,
            "workflow_id": workflow.workflow_id,
            "request": workflow.user_request,
            "status": workflow.status,
            "tool": tool,
            "action": action,
            "risk": risk,
            "args": args,
            "approval_request_id": workflow.approval_request_id,
            "result": result,
            "plan": self._plan_of(workflow),
            "created_at": workflow.created_at,
            "persisted_at": datetime.now(timezone.utc).isoformat(),
        })


mission_service = MissionService()
