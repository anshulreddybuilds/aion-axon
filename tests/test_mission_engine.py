"""Mission engine tests.

Fully offline: plans are constructed directly rather than generated, so
the engine's routing and governance behaviour is tested without a network
call. Planner output itself is exercised by the live probe, not here.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

import pytest  # noqa: E402

import app.capabilities.bootstrap  # noqa: E402,F401
from app.agents.plan_schema import MissionPlan, MissionStep  # noqa: E402
from app.capabilities.declarations import (  # noqa: E402
    capability_catalog,
    function_declarations,
)
from app.capabilities.registry import (  # noqa: E402
    CapabilityNotImplemented,
    registry,
)
from app.capabilities.seed import SEED_COUNT  # noqa: E402
from app.governance.kill_switch import kill_switch  # noqa: E402
from app.missions.engine import mission_engine  # noqa: E402
from app.workflows.state import WorkflowState  # noqa: E402


@pytest.fixture(autouse=True)
def clean_kill_switch():
    kill_switch.deactivate()
    yield
    kill_switch.deactivate()


def step(**kwargs) -> MissionStep:
    base = {
        "step": 1,
        "description": "do a thing",
        "kind": "READ_ANALYZE",
        "tool": "calculator",
        "args": ["2 + 2"],
        "risk": "LOW",
        "action": "add numbers",
    }
    return MissionStep(**{**base, **kwargs})


def test_seed_capabilities_are_registered():
    counts = registry.counts()

    assert counts["total"] == SEED_COUNT == 12
    assert registry.is_implemented("calculator")
    assert registry.is_implemented("web_research")
    assert not registry.is_implemented("write_brief")


def test_declared_capability_cannot_be_executed():
    """A declared capability must raise, never silently do nothing."""
    with pytest.raises(CapabilityNotImplemented):
        registry.get("write_brief")


def test_declaring_never_overwrites_an_implementation():
    registry.declare("calculator", "hijacked", "LOW")

    assert registry.is_implemented("calculator")


def test_function_declarations_cover_every_capability():
    declarations = function_declarations()

    assert len(declarations) == SEED_COUNT

    unimplemented = [
        d for d in declarations if "NOT YET IMPLEMENTED" in d.description
    ]

    assert len(unimplemented) == registry.counts()["declared_only"]


def test_catalog_marks_availability():
    catalog = capability_catalog()

    assert "calculator (AVAILABLE" in catalog
    assert "write_brief (NOT IMPLEMENTED" in catalog


def test_plan_runs_all_low_risk_steps():
    plan = MissionPlan(
        goal="Add some numbers",
        steps=[
            step(step=1, args=["2 + 2"]),
            step(step=2, args=["10 * 3"], description="multiply"),
        ],
    )

    workflow = WorkflowState(user_request="add things")

    summary = mission_engine.run(workflow, plan)

    assert summary["status"] == "COMPLETED"
    assert summary["steps_completed"] == 2
    assert summary["step_results"][1]["result"]["result"] == 30.0


def test_missing_tool_blocks_the_mission_and_records_the_gap():
    plan = MissionPlan(
        goal="Write a brief",
        steps=[
            step(step=1, args=["2 + 2"]),
            step(step=2, tool=None, description="write the exec brief"),
        ],
    )

    workflow = WorkflowState(user_request="brief me")

    summary = mission_engine.run(workflow, plan)

    assert summary["status"] == "BLOCKED"
    assert summary["steps_completed"] == 1
    assert summary["next_step_index"] == 1
    assert summary["blocked_on"]["step"] == 2
    assert workflow.status == "BLOCKED"


def test_declared_but_unimplemented_tool_blocks_with_the_name():
    plan = MissionPlan(
        goal="Write a brief",
        steps=[step(step=1, tool="write_brief", args=[])],
    )

    summary = mission_engine.run(
        WorkflowState(user_request="brief me"), plan,
    )

    assert summary["status"] == "BLOCKED"
    assert summary["blocked_on"]["missing_capability"] == "write_brief"
    assert "declared but has no implementation" in (
        summary["blocked_on"]["reason"]
    )


def test_gap_is_detected_before_execution_not_after():
    """A gap at step 1 must stop the mission before anything runs."""
    plan = MissionPlan(
        goal="Gap first",
        steps=[
            step(step=1, tool="write_brief", args=[]),
            step(step=2, args=["2 + 2"]),
        ],
    )

    summary = mission_engine.run(WorkflowState(user_request="x"), plan)

    assert summary["status"] == "BLOCKED"
    assert summary["steps_completed"] == 0
    assert summary["step_results"] == []


def test_medium_risk_step_suspends_the_mission_for_approval():
    plan = MissionPlan(
        goal="Buy a thing",
        steps=[
            step(step=1, args=["2 + 2"]),
            step(
                step=2,
                risk="MEDIUM",
                kind="EXTERNAL_EFFECT",
                action="purchase item",
                args=["1250 * 1.18"],
            ),
            step(step=3, args=["1 + 1"], description="never reached yet"),
        ],
    )

    summary = mission_engine.run(WorkflowState(user_request="buy"), plan)

    assert summary["status"] == "AWAITING_APPROVAL"
    assert summary["steps_completed"] == 1
    assert summary["next_step_index"] == 1
    assert summary["approval_request_id"]


def test_high_risk_step_ends_the_mission_refused():
    plan = MissionPlan(
        goal="Read secrets",
        steps=[
            step(
                step=1,
                risk="HIGH",
                action="read runtime credentials",
                args=["1 + 1"],
            ),
        ],
    )

    summary = mission_engine.run(WorkflowState(user_request="secrets"), plan)

    assert summary["status"] == "REFUSED"
    assert summary["steps_completed"] == 0


def test_kill_switch_stops_a_running_plan_mid_flight():
    kill_switch.activate("halt mid mission")

    plan = MissionPlan(
        goal="Two steps",
        steps=[step(step=1, args=["2 + 2"]), step(step=2, args=["3 + 3"])],
    )

    summary = mission_engine.run(WorkflowState(user_request="x"), plan)

    assert summary["status"] == "BLOCKED"
    assert summary["steps_completed"] == 0


def test_capability_gaps_helper():
    plan = MissionPlan(
        goal="mixed",
        steps=[step(step=1), step(step=2, tool=None)],
    )

    assert len(plan.capability_gaps()) == 1
