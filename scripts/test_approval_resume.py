from app.workflows.orchestrator import orchestrator
from app.capabilities.registry import registry
from app.governance.guardian import RiskLevel
from app.tools.calculator import calculate
from app.governance.approval import approval_manager
from app.memory.firestore_store import firestore_store


registry.register(
    "calculator",
    "Performs safe basic arithmetic calculations.",
    "LOW",
    calculate,
)

workflow = orchestrator.create_workflow(
    "Test end-to-end approval resume with calculator"
)

result = orchestrator.execute_tool(
    workflow,
    "calculator",
    "purchase item",
    RiskLevel.MEDIUM,
    "1250 * 1.18",
)

print("STEP 1 - INITIAL EXECUTION")
print("RESULT:", result)
print("WORKFLOW STATUS:", workflow.status)
print("APPROVAL ID:", workflow.approval_request_id)

approval_id = workflow.approval_request_id

assert result["status"] == "APPROVAL_REQUIRED"
assert workflow.status == "AWAITING_APPROVAL"
assert approval_id is not None

print()
print("STEP 2 - APPROVE REQUEST")

approval_manager.decide(
    approval_id,
    True,
    "anshul",
)

persisted = firestore_store.get_approval(approval_id)

print("FIRESTORE STATUS:", persisted.get("status"))
print("DECIDED BY:", persisted.get("decided_by"))

assert persisted.get("status") == "APPROVED"

print()
print("STEP 3 - RESUME APPROVED WORKFLOW")

resume_result = orchestrator.approve_and_resume(
    workflow,
    "calculator",
    "purchase item",
    RiskLevel.MEDIUM,
    approval_id,
    "1250 * 1.18",
)

print("RESULT:", resume_result)
print("WORKFLOW STATUS:", workflow.status)
print("WORKFLOW ID:", workflow.workflow_id)

assert resume_result["status"] == "EXECUTED"
assert workflow.status == "COMPLETED"

print()
print("END-TO-END APPROVAL RESUME: PASS")
