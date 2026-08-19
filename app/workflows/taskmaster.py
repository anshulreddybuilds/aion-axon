from app.agents.planner import planner_agent
from app.agents.planner_runner import planner_available, run_planner
from app.workflows.state import WorkflowState, create_workflow


class TaskmasterPlanner:

    def create(self, user_request: str) -> WorkflowState:
        workflow = create_workflow(user_request)

        # The planner is advisory. It shapes the plan; it never executes.
        # Skipped when no API key is configured, so tests stay offline.
        plan = run_planner(user_request)

        workflow.add_observation(
            "planner",
            {
                "event": "plan_generated" if plan else "plan_skipped",
                "framework": "google.adk",
                "model": planner_agent.model,
                "plan": plan,
                "reason": None if plan else "no_api_key",
            },
        )

        return workflow

    def describe(self) -> dict:
        return {
            "name": planner_agent.name,
            "model": planner_agent.model,
            "role": "workflow_planner",
            "framework": "google.adk",
            "planner_available": planner_available(),
            "execution_policy": "planner_never_executes_external_side_effects",
            "governance": [
                "guardian",
                "human_approval",
                "kill_switch",
            ],
        }


taskmaster = TaskmasterPlanner()
