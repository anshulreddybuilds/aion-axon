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
from app.agents.mission_planner import plan_mission
from app.agents.plan_schema import MissionPlan
from app.governance.guardian import RiskLevel
from app.memory.firestore_store import firestore_store
from app.missions.engine import mission_engine
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
            # The planned path passed these and the direct path did not,
            # so G-07 autonomy supervision was silently skipped whenever a
            # capability was invoked directly. A governance check that
            # depends on which endpoint the caller used is not a check.
            description=request,
            capability=tool,
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

    def start_planned(self, request: str) -> dict[str, Any]:
        """Plan a messy request, then execute the plan through the gate."""
        workflow = WorkflowState(user_request=request)
        mission_id = str(uuid4())

        plan, error = plan_mission(request)

        if plan is None:
            workflow.update_status("FAILED")
            workflow.error = error

            firestore_store.save_mission(mission_id, {
                "mission_id": mission_id,
                "workflow_id": workflow.workflow_id,
                "request": request,
                "mode": "planned",
                "status": "FAILED",
                "error": error,
                "created_at": workflow.created_at,
            })

            return {
                "mission_id": mission_id,
                "status": "FAILED",
                "error": error,
            }

        workflow.plan = [step.model_dump() for step in plan.steps]
        workflow.update_status("EXECUTING")

        summary = mission_engine.run(workflow, plan)

        self._persist_planned(mission_id, workflow, request, plan, summary)

        return {
            "mission_id": mission_id,
            "workflow_id": workflow.workflow_id,
            "goal": plan.goal,
            "plan": [step.model_dump() for step in plan.steps],
            **summary,
        }

    def resume_planned(self, mission_id: str) -> dict[str, Any]:
        """Continue a planned mission from the step that suspended it."""
        mission = firestore_store.get_mission(mission_id)

        if mission is None:
            return {"status": "FAILED", "error": "Unknown mission."}

        if mission.get("mode") != "planned":
            return {"status": "FAILED", "error": "Not a planned mission."}

        if mission.get("status") != "AWAITING_APPROVAL":
            return {
                "status": "FAILED",
                "error": (
                    "Mission is not awaiting approval. "
                    f"Current status: {mission.get('status')}"
                ),
            }

        plan = MissionPlan.model_validate(mission["plan_document"])

        workflow = WorkflowState(
            user_request=mission["request"],
            workflow_id=mission["workflow_id"],
        )
        workflow.status = "EXECUTING"

        index = mission.get("next_step_index", 0)
        completed = [
            r for r in mission.get("step_results", [])
            if r.get("status") == "EXECUTED"
        ]

        # Resume the suspended step through the approved path, then let
        # the engine carry on with the rest.
        step = plan.steps[index]

        approved = orchestrator.approve_and_resume(
            workflow,
            step.tool,
            step.action,
            RiskLevel(step.risk),
            mission["approval_request_id"],
            *step.args,
        )

        if approved.get("status") != "EXECUTED":
            summary = {
                "status": approved.get("status", "UNKNOWN"),
                "steps_completed": len(completed),
                "steps_total": len(plan.steps),
                "next_step_index": index,
                "step_results": completed,
                "approval_request_id": mission["approval_request_id"],
                "blocked_on": None,
                "reason": approved.get("reason"),
            }
        else:
            completed.append({
                "step": step.step,
                "description": step.description,
                "tool": step.tool,
                "action": step.action,
                "risk": step.risk,
                "kind": step.kind,
                "status": "EXECUTED",
                "result": approved.get("result"),
                "approved": True,
                "at": datetime.now(timezone.utc).isoformat(),
            })

            summary = mission_engine.run(
                workflow, plan, start_at=index + 1, completed=completed,
            )

        self._persist_planned(
            mission_id, workflow, mission["request"], plan, summary,
        )

        return {"mission_id": mission_id, "goal": plan.goal, **summary}

    def _persist_planned(
        self,
        mission_id: str,
        workflow: WorkflowState,
        request: str,
        plan: MissionPlan,
        summary: dict[str, Any],
    ) -> None:
        firestore_store.save_mission(mission_id, {
            "mission_id": mission_id,
            "workflow_id": workflow.workflow_id,
            "request": request,
            "mode": "planned",
            "goal": plan.goal,
            "status": summary["status"],
            "plan_document": plan.model_dump(),
            "step_results": summary["step_results"],
            "next_step_index": summary["next_step_index"],
            "steps_completed": summary["steps_completed"],
            "steps_total": summary["steps_total"],
            "approval_request_id": summary.get("approval_request_id"),
            "blocked_on": summary.get("blocked_on"),
            "created_at": workflow.created_at,
        })

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
