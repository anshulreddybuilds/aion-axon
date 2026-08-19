from typing import Any

from app.workflows.taskmaster import taskmaster
from app.workflows.state import WorkflowState
from app.capabilities.registry import registry
from app.governance.execution_gate import execution_gate
from app.governance.guardian import RiskLevel
from app.governance.approval import approval_manager


class AxonOrchestrator:
    """
    Central orchestration layer for AION AXON.

    Responsibilities:
    - Create and manage WorkflowState.
    - Resolve registered tools.
    - Route executable actions through the Unified Execution Gate.
    - Resume approved workflows safely.
    - Never bypass Guardian, approval, or kill switch.
    """

    def create_workflow(self, user_request: str) -> WorkflowState:
        workflow = taskmaster.create(user_request)

        workflow.add_observation(
            "orchestrator",
            {
                "event": "workflow_created",
                "planner": taskmaster.describe(),
            },
        )

        return workflow

    def execute_tool(
        self,
        workflow: WorkflowState,
        tool_name: str,
        action: str,
        risk: RiskLevel,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:

        tool = registry.get(tool_name)

        workflow.add_action(
            action=action,
            risk=risk.value,
            description=tool.description,
        )

        workflow.update_status("EXECUTING")

        result = execution_gate.execute(
            action,
            risk,
            tool.function,
            *args,
            **kwargs,
        )

        workflow.add_observation(
            "execution_gate",
            {
                "tool": tool_name,
                "result": result,
            },
        )

        status = result.get("status")

        if status == "EXECUTED":
            workflow.result = result
            workflow.update_status("COMPLETED")

        elif status == "APPROVAL_REQUIRED":
            workflow.approval_request_id = result.get("request_id")
            workflow.update_status("AWAITING_APPROVAL")

            workflow.add_observation(
                "approval",
                {
                    "event": "approval_requested",
                    "request_id": workflow.approval_request_id,
                },
            )

        elif status == "REFUSED":
            workflow.result = result
            workflow.update_status("REFUSED")

        elif status == "BLOCKED":
            workflow.result = result
            workflow.update_status("BLOCKED")

        elif status == "FAILED":
            workflow.error = result.get("error")
            workflow.result = result
            workflow.update_status("FAILED")

        else:
            workflow.result = result
            workflow.update_status("UNKNOWN")

        return result

    def approve_and_resume(
        self,
        workflow: WorkflowState,
        tool_name: str,
        action: str,
        risk: RiskLevel,
        approval_request_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:

        # 1. The workflow must actually be waiting for approval.
        if workflow.status != "AWAITING_APPROVAL":
            result = {
                "status": "FAILED",
                "error": (
                    "Workflow is not awaiting approval. "
                    f"Current status: {workflow.status}"
                ),
            }
            workflow.result = result
            return result

        # 2. Approval ID must match the workflow.
        if workflow.approval_request_id != approval_request_id:
            result = {
                "status": "FAILED",
                "error": "Approval request does not match workflow.",
            }
            workflow.result = result
            return result

        # 3. Resolve approval from Firestore-backed manager.
        approval = approval_manager.get(approval_request_id)

        if approval is None:
            result = {
                "status": "FAILED",
                "error": "Approval request not found.",
            }
            workflow.result = result
            workflow.update_status("FAILED")
            return result

        # 4. Never execute without explicit human approval.
        if approval.approved is not True:
            result = {
                "status": "APPROVAL_REQUIRED",
                "request_id": approval_request_id,
                "reason": "Human approval has not been granted.",
            }
            workflow.result = result
            workflow.update_status("AWAITING_APPROVAL")
            return result

        # 5. Resolve the tool through the registry.
        tool = registry.get(tool_name)

        workflow.add_observation(
            "approval",
            {
                "event": "approval_verified",
                "request_id": approval_request_id,
                "decided_by": approval.decided_by,
            },
        )

        workflow.update_status("EXECUTING")

        # 6. Approved execution STILL goes through the gate.
        #    The gate re-checks Kill Switch + Guardian.
        result = execution_gate.execute_approved(
            action,
            risk,
            tool.function,
            approval_request_id,
            *args,
            **kwargs,
        )

        workflow.add_observation(
            "approved_execution",
            {
                "tool": tool_name,
                "approval_request_id": approval_request_id,
                "result": result,
            },
        )

        status = result.get("status")

        if status == "EXECUTED":
            workflow.result = result
            workflow.update_status("COMPLETED")

        elif status == "BLOCKED":
            workflow.result = result
            workflow.update_status("BLOCKED")

        elif status == "REFUSED":
            workflow.result = result
            workflow.update_status("REFUSED")

        elif status == "FAILED":
            workflow.error = result.get("error")
            workflow.result = result
            workflow.update_status("FAILED")

        else:
            workflow.result = result
            workflow.update_status("UNKNOWN")

        return result


orchestrator = AxonOrchestrator()
