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
from app.memory.firestore_store import firestore_store  # noqa: E402
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
    assert not registry.is_implemented("summarize_text")


def test_declared_capability_cannot_be_executed():
    """A declared capability must raise, never silently do nothing."""
    with pytest.raises(CapabilityNotImplemented):
        registry.get("summarize_text")


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
    """The catalog now carries parameter names too, so an implemented
    capability reads `name(args) (AVAILABLE...)`. Asserting on the state
    marker rather than on the exact spacing keeps this test about
    availability, which is what it is named for.
    """
    catalog = capability_catalog()

    assert "calculator(expression) (AVAILABLE" in catalog
    assert "(NOT IMPLEMENTED" in catalog


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
        steps=[step(step=1, tool="summarize_text", args=[])],
    )

    summary = mission_engine.run(
        WorkflowState(user_request="brief me"), plan,
    )

    assert summary["status"] == "BLOCKED"
    assert summary["blocked_on"]["missing_capability"] == "summarize_text"
    assert "declared but has no implementation" in (
        summary["blocked_on"]["reason"]
    )


def test_gap_is_detected_before_execution_not_after():
    """A gap at step 1 must stop the mission before anything runs."""
    plan = MissionPlan(
        goal="Gap first",
        steps=[
            step(step=1, tool="summarize_text", args=[]),
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


# --- BUG-018: an existing capability with empty args is backfilled -------
#
# Mirrors resume_blocked()'s own "Found live 21 Aug" backfill, but for the
# normal first-run path: the natural-language planner left `args: []` on a
# step naming a capability that already exists (generate_nepal_crisis_image
# in the real report), so BUG-014's arity check fails the step cleanly but
# the mission never completes.

def test_step_naming_an_existing_tool_with_empty_args_is_backfilled_with_the_request():
    def echo_one(x):
        return {"status": "OK", "echo": x}

    registry.register("bug018_echo_one", "echoes its single argument", "LOW", echo_one)
    try:
        plan = MissionPlan(
            goal="echo the request",
            steps=[step(
                step=1, tool="bug018_echo_one", args=[],
                description="echo something", action="run echo tool",
            )],
        )

        workflow = WorkflowState(user_request="the mission's own free text")
        summary = mission_engine.run(workflow, plan)

        assert summary["status"] == "COMPLETED"
        assert summary["step_results"][0]["result"]["echo"] == (
            "the mission's own free text"
        )
    finally:
        registry.unregister("bug018_echo_one")


def test_step_with_explicit_args_is_never_overwritten_by_the_backfill():
    def echo_one(x):
        return {"status": "OK", "echo": x}

    registry.register("bug018_echo_one_explicit", "echoes its single argument", "LOW", echo_one)
    try:
        plan = MissionPlan(
            goal="echo an explicit value",
            steps=[step(
                step=1, tool="bug018_echo_one_explicit", args=["explicit value"],
                description="echo something", action="run echo tool",
            )],
        )

        workflow = WorkflowState(user_request="must not appear anywhere")
        summary = mission_engine.run(workflow, plan)

        assert summary["status"] == "COMPLETED"
        assert summary["step_results"][0]["result"]["echo"] == "explicit value"
    finally:
        registry.unregister("bug018_echo_one_explicit")


def test_zero_arg_capability_is_not_force_fed_the_request():
    """A capability KNOWN to take zero arguments must stay at zero -- the
    exact failure mode the arity gate exists to prevent. Without it, this
    step would receive one unwanted argument and BLOCK on BUG-014's own
    arity check (`inspect.signature(zero_arg).bind(request)` in
    orchestrator.execute_tool), trading one bug for another.
    """
    def zero_arg():
        return {"status": "OK", "called_with": "nothing"}

    registry.register("bug018_zero_arg", "takes no arguments at all", "LOW", zero_arg)
    try:
        plan = MissionPlan(
            goal="run a zero-arg capability",
            steps=[step(
                step=1, tool="bug018_zero_arg", args=[],
                description="run the zero-arg tool", action="run zero-arg tool",
            )],
        )

        workflow = WorkflowState(user_request="this must not become an argument")
        summary = mission_engine.run(workflow, plan)

        assert summary["status"] == "COMPLETED"
        assert summary["step_results"][0]["result"]["called_with"] == "nothing"
    finally:
        registry.unregister("bug018_zero_arg")


def test_backfill_reads_arity_from_the_stored_synapse_candidate_not_the_bare_proxy():
    """The real report: a SYNAPSE-acquired capability's registered function
    is always the sandbox proxy's bare `invoke(*args)` -- inspecting IT
    reveals nothing. The minimum-args check must instead read the real
    generated source Firestore holds for it (`passport.candidate`), the
    same record `rehydrate.py` already reads to restore it after a
    restart, and the same static reading `SynapseEngine._entrypoint_arity`
    already does for BUG-014's own check one layer down.
    """
    def sandbox_proxy_shape(*args):
        return {"status": "OK", "n": len(args)}

    registry.register(
        "generate_nepal_crisis_image_test", "image generator (test double)",
        "LOW", sandbox_proxy_shape,
    )
    firestore_store.save_capability("generate_nepal_crisis_image_test", {
        "name": "generate_nepal_crisis_image_test",
        # autonomy_pct is set high on purpose: saving ANY capability
        # record makes autonomy_ledger.tracked() see it, and an absent
        # autonomy_pct defaults to STARTING_AUTONOMY (32.0), which is
        # BELOW SUPERVISION_THRESHOLD (40.0) -- that would route this
        # step through G-07 approval-required instead of straight
        # execution, which is a fact about the autonomy ledger, not
        # about BUG-018's backfill this test exists to check.
        "autonomy_pct": 100.0,
        "passport": {
            "candidate": {
                "code": (
                    "def generate_image(input_str):\n"
                    "    return {'status': 'OK', 'input': input_str}\n"
                ),
                "entrypoint": "generate_image",
            },
        },
    })
    try:
        plan = MissionPlan(
            goal="generate an image",
            steps=[step(
                step=1, tool="generate_nepal_crisis_image_test", args=[],
                description="generate a crisis image",
                action="generate crisis image",
            )],
        )

        workflow = WorkflowState(user_request="a crisis image prompt")
        summary = mission_engine.run(workflow, plan)

        assert summary["status"] == "COMPLETED"
        assert summary["step_results"][0]["result"]["n"] == 1
    finally:
        registry.unregister("generate_nepal_crisis_image_test")
        firestore_store.capabilities.pop("generate_nepal_crisis_image_test", None)


def test_minimum_args_required_is_none_for_a_genuinely_variadic_seed():
    """An indeterminate minimum (a real `*args` seed function, not a
    sandbox proxy) must not be treated as "requires zero" -- BUG-018's
    backfill still applies in that case, matching resume_blocked()'s own
    unconditional backfill.
    """
    def variadic(*args):
        return {"status": "OK", "count": len(args)}

    registry.register("bug018_variadic_seed", "variadic test tool", "LOW", variadic)
    try:
        assert mission_engine._minimum_args_required("bug018_variadic_seed") is None
    finally:
        registry.unregister("bug018_variadic_seed")
