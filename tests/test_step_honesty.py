"""A mission must not report success it did not achieve.

Both properties here were found live on 22 Aug, in the first Phase 8 fire
drill. The mission returned COMPLETED and produced a clean-looking
Business Action Brief. Underneath, the BigQuery step had failed on a byte
cap, the analysis step had failed on the resulting empty input, and the
brief had been written from the planner's own description of what step 3
was supposed to do.

Nothing crashed. Every step was "EXECUTED". The output looked like an
answer. That is the failure mode this project's README singles out as
worse than crashing, and it had shipped.
"""
import json
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

import pytest  # noqa: E402

import app.capabilities.bootstrap  # noqa: E402,F401
from app.agents.plan_schema import MissionPlan, MissionStep  # noqa: E402
from app.capabilities.registry import registry  # noqa: E402
from app.missions.engine import mission_engine  # noqa: E402
from app.workflows.state import WorkflowState  # noqa: E402


@pytest.fixture(autouse=True)
def clean():
    for name in ("always_fails", "echo_arg", "emits_rows"):
        registry.unregister(name)
    yield
    for name in ("always_fails", "echo_arg", "emits_rows"):
        registry.unregister(name)


def step(n, tool, args, desc="d"):
    return MissionStep(
        step=n, description=desc, kind="READ_ANALYZE", tool=tool,
        args=args, risk="LOW", action="a",
    )


# --- A tool that "runs" but reports failure must fail the mission --------

def test_a_step_whose_tool_reports_error_fails_the_mission():
    """EXECUTED means the GATE ran it, not that it worked."""
    registry.register(
        "always_fails", "Always reports an error.", "LOW",
        lambda *a: {"status": "ERROR", "error": "byte cap exceeded"},
    )

    plan = MissionPlan(goal="g", steps=[step(1, "always_fails", [])])
    workflow = WorkflowState(user_request="r")

    summary = mission_engine.run(workflow, plan)

    assert summary["status"] == "FAILED", (
        "a step whose tool reported ERROR was treated as success"
    )
    assert "byte cap exceeded" in summary["step_results"][0]["reason"]


def test_a_failed_step_stops_the_steps_after_it():
    """The live bug: step 1 and 2 failed and step 3 wrote a brief anyway."""
    ran = []

    registry.register(
        "always_fails", "Always errors.", "LOW",
        lambda *a: {"status": "ERROR", "error": "no data"},
    )
    registry.register(
        "echo_arg", "Records that it ran.", "LOW",
        lambda *a: (ran.append(a), {"status": "SUCCESS"})[1],
    )

    plan = MissionPlan(goal="g", steps=[
        step(1, "always_fails", []),
        step(2, "echo_arg", ["should never run"]),
    ])

    summary = mission_engine.run(WorkflowState(user_request="r"), plan)

    assert summary["status"] == "FAILED"
    assert ran == [], "a later step ran after an earlier one had failed"
    assert summary["steps_completed"] == 0


def test_a_genuinely_successful_mission_still_completes():
    """The guard must not make every mission fail."""
    registry.register(
        "echo_arg", "Succeeds.", "LOW",
        lambda *a: {"status": "SUCCESS", "value": 1},
    )

    plan = MissionPlan(goal="g", steps=[step(1, "echo_arg", ["x"])])
    summary = mission_engine.run(WorkflowState(user_request="r"), plan)

    assert summary["status"] == "COMPLETED"


# --- Data must actually flow between steps -------------------------------

def test_step_output_flows_into_the_next_step():
    """$STEP_1 must arrive as step 1's real output, not as the literal."""
    seen = {}

    registry.register(
        "emits_rows", "Emits data.", "LOW",
        lambda *a: {"status": "SUCCESS", "rows": [1, 2, 3]},
    )
    registry.register(
        "echo_arg", "Captures what it was given.", "LOW",
        lambda *a: (seen.update(arg=a[0]), {"status": "SUCCESS"})[1],
    )

    plan = MissionPlan(goal="g", steps=[
        step(1, "emits_rows", []),
        step(2, "echo_arg", ["$STEP_1"]),
    ])

    summary = mission_engine.run(WorkflowState(user_request="r"), plan)

    assert summary["status"] == "COMPLETED"
    assert "$STEP_1" not in seen["arg"], "the placeholder was never resolved"
    assert json.loads(seen["arg"])["rows"] == [1, 2, 3]


def test_an_unresolvable_reference_is_left_visible_not_blanked():
    """A silently empty argument produces a confident answer about
    nothing — exactly the live failure. Leaving the token in place makes
    the mistake obvious instead.
    """
    seen = {}

    registry.register(
        "echo_arg", "Captures.", "LOW",
        lambda *a: (seen.update(arg=a[0]), {"status": "SUCCESS"})[1],
    )

    plan = MissionPlan(goal="g", steps=[step(1, "echo_arg", ["$STEP_9"])])
    mission_engine.run(WorkflowState(user_request="r"), plan)

    assert seen["arg"] == "$STEP_9"


def test_plain_args_are_untouched():
    seen = {}

    registry.register(
        "echo_arg", "Captures.", "LOW",
        lambda *a: (seen.update(arg=a[0]), {"status": "SUCCESS"})[1],
    )

    plan = MissionPlan(goal="g", steps=[step(1, "echo_arg", ["1250 * 1.18"])])
    mission_engine.run(WorkflowState(user_request="r"), plan)

    assert seen["arg"] == "1250 * 1.18"
