from app.agents.planner import planner_agent
from app.workflows.state import WorkflowState, create_workflow


class TaskmasterPlanner:

    def create(self, user_request: str) -> WorkflowState:
        return create_workflow(user_request)

    def describe(self) -> dict:
        return {
            "name": planner_agent.name,
            "model": planner_agent.model,
            "role": "workflow_planner",
            "execution_policy": "planner_never_executes_external_side_effects",
            "governance": [
                "guardian",
                "human_approval",
                "kill_switch",
            ],
        }


taskmaster = TaskmasterPlanner()
