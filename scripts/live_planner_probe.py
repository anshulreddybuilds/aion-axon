"""Live probe: prove the ADK Runner really reaches Gemini.

Requires GOOGLE_API_KEY. Makes exactly one Gemini call. Read-only:
plans a request, executes nothing.
"""
from app.agents.planner import planner_agent
from app.agents.planner_runner import planner_available, run_planner


def main() -> None:
    if not planner_available():
        print("NO KEY SET - live planner probe skipped")
        return

    print("AGENT:", planner_agent.name)
    print("MODEL:", planner_agent.model)
    print("FRAMEWORK: google.adk Runner")
    print()

    plan = run_planner("Calculate 1250 * 1.18 and tell me the total.")

    print("PLAN:")
    print(plan)
    print()

    if plan and not plan.startswith("PLANNER_ERROR"):
        print("LIVE ADK + GEMINI PLANNER: PASS")
    else:
        print("LIVE ADK + GEMINI PLANNER: FAIL")


if __name__ == "__main__":
    main()
