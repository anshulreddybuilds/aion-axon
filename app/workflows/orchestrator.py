import inspect
from typing import Any, Optional

from app.workflows.taskmaster import taskmaster
from app.workflows.state import WorkflowState
from app.capabilities.registry import registry
from app.governance.execution_gate import execution_gate
from app.governance.guardian import RiskLevel
from app.governance.approval import approval_manager
from app.governance.verification import verify_outcome
from app.memory.firestore_store import firestore_store


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

        # An unknown or unbuilt capability is a CAPABILITY GAP, not a
        # server error. Letting the KeyError escape produced an unhandled
        # 500 with a stack trace, which reads as "the agent crashed"
        # rather than "the agent cannot do that yet" -- and the second is
        # both true and the thing SYNAPSE acts on.
        try:
            tool = registry.get(tool_name)
        except KeyError as error:
            gap = {
                "status": "BLOCKED",
                "reason": str(error).strip("'"),
                "missing_capability": tool_name,
            }

            workflow.error = gap["reason"]
            workflow.update_status("BLOCKED")
            workflow.add_observation("capability_gap", gap)

            firestore_store.write_audit_event("CAPABILITY_GAP", {
                "action": action,
                "missing_capability": tool_name,
                "reason": gap["reason"],
            })

            return gap

        # BUG-014, 29 Aug 2026: a mission step's args were passed straight
        # to tool.function(*args) with nothing checking the count/names
        # against what the capability actually requires. The real failure
        # this produced (generate_nepal_crisis_image() missing 1 required
        # positional argument: 'input_str') was already being caught by
        # execution_gate._execute_tool()'s broad except -- so it never
        # crashed the server -- but it burned a real Guardian check, a
        # real audit trail entry, and an "EXECUTING" status transition on
        # a call that could never have succeeded, and it surfaced a raw
        # Python TypeError as the mission's failure reason instead of a
        # clear governance-style explanation. Checking here, with the
        # tool's own real signature, catches it before any of that -- the
        # same shape as the CAPABILITY_GAP check just above, one step
        # later in the same lookup.
        try:
            inspect.signature(tool.function).bind(*args)
        except TypeError as error:
            gap = {
                "status": "BLOCKED",
                "reason": (
                    f"'{tool_name}' cannot run with the arguments this "
                    f"step supplied: {error}"
                ),
                "argument_mismatch": tool_name,
            }

            workflow.error = gap["reason"]
            workflow.update_status("BLOCKED")
            workflow.add_observation("argument_mismatch", gap)

            firestore_store.write_audit_event("ARGUMENT_MISMATCH", {
                "action": action,
                "capability": tool_name,
                "reason": gap["reason"],
                "args_given": len(args),
            })

            return gap

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

        # Verification lives HERE, not in the mission engine, because both
        # mission paths (direct /missions and planned) pass through the
        # orchestrator while only the planned one uses the engine. Putting
        # it in the engine left the direct path unverified -- a research
        # claim could execute and move no autonomy at all.
        verify_outcome(tool_name, result)

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
        description: Optional[str] = None,
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
            # Give the gate the same two fields execute() gets. The tool
            # name is already here, so every existing caller gains the
            # capability-aware re-check without changing its own call.
            description=description,
            capability=tool_name,
            **kwargs,
        )

        # Approved work is verified on the same terms as unapproved work.
        # A human saying yes authorises the ACTION; it does not certify
        # the RESULT, and the ledger scores results.
        verify_outcome(tool_name, result)

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
