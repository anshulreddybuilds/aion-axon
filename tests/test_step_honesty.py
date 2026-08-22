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


def test_step_output_field_can_be_reached_with_a_dot():
    """`$STEP_1.rows` must pass the records, not the whole envelope.

    The second fire drill died exactly here: read_dataset returns
    {status, rows, row_count, ...} and the analyser was handed all of it,
    then refused with "JSON input must be a list of records".
    """
    seen = {}

    registry.register(
        "emits_rows", "Returns an envelope around its rows.", "LOW",
        lambda *a: {"status": "SUCCESS", "row_count": 2,
                    "rows": [{"year": 2005}, {"year": 2006}]},
    )
    registry.register(
        "echo_arg", "Captures.", "LOW",
        lambda *a: (seen.update(arg=a[0]), {"status": "SUCCESS"})[1],
    )

    plan = MissionPlan(goal="g", steps=[
        step(1, "emits_rows", []),
        step(2, "echo_arg", ["$STEP_1.rows"]),
    ])

    summary = mission_engine.run(WorkflowState(user_request="r"), plan)

    assert summary["status"] == "COMPLETED"
    assert json.loads(seen["arg"]) == [{"year": 2005}, {"year": 2006}], (
        "the envelope was passed instead of the records"
    )


def test_a_missing_field_leaves_the_reference_visible():
    seen = {}

    registry.register(
        "emits_rows", "No such field.", "LOW",
        lambda *a: {"status": "SUCCESS", "rows": [1]},
    )
    registry.register(
        "echo_arg", "Captures.", "LOW",
        lambda *a: (seen.update(arg=a[0]), {"status": "SUCCESS"})[1],
    )

    plan = MissionPlan(goal="g", steps=[
        step(1, "emits_rows", []),
        step(2, "echo_arg", ["$STEP_1.nope"]),
    ])
    mission_engine.run(WorkflowState(user_request="r"), plan)

    assert seen["arg"] == "$STEP_1.nope"


def test_plain_args_are_untouched():
    seen = {}

    registry.register(
        "echo_arg", "Captures.", "LOW",
        lambda *a: (seen.update(arg=a[0]), {"status": "SUCCESS"})[1],
    )

    plan = MissionPlan(goal="g", steps=[step(1, "echo_arg", ["1250 * 1.18"])])
    mission_engine.run(WorkflowState(user_request="r"), plan)

    assert seen["arg"] == "1250 * 1.18"


# --- SYNAPSE must be shown the real input shape ---------------------------

def test_blocked_step_input_sample_is_the_real_data_not_a_description():
    """The 22 Aug failure: SYNAPSE built calculate_cagr for {date, value}
    records while the step actually receives {year, total} rows. Every
    check passed — safety, sandbox, Gemma 100 — because none of them was
    asking whether the candidate fits the data. Showing SYNAPSE the actual
    input is what closes that.
    """
    from app.missions.service import mission_service
    from app.memory.firestore_store import firestore_store

    registry.register(
        "emits_rows", "Returns BigQuery-shaped rows.", "LOW",
        lambda *a: {
            "status": "SUCCESS",
            "row_count": 2,
            "rows": [{"year": 2005, "total": 3304899},
                     {"year": 2006, "total": 3387211}],
        },
    )

    plan = MissionPlan(goal="g", steps=[
        step(1, "emits_rows", []),
        # The gap: no capability, but the args already say what it gets.
        step(2, None, ["$STEP_1.rows"], desc="compute CAGR"),
    ])

    workflow = WorkflowState(user_request="r")
    summary = mission_engine.run(workflow, plan)

    assert summary["status"] == "BLOCKED"

    mission_service._persist_planned("m-sample", workflow, "r", plan, summary)

    sample = mission_service.blocked_step_input("m-sample")

    assert sample is not None, "no sample was produced for the blocked step"
    # The real field names must be visible to the generator.
    assert "year" in sample and "total" in sample
    assert "3304899" in sample
    # And it must be the data, not the planner's sentence about it.
    assert "compute CAGR" not in sample

    firestore_store.missions.clear()


def test_no_sample_when_nothing_has_run_yet():
    """A mission blocked at step 1 has no upstream output. Inventing a
    sample there would be worse than sending none.
    """
    from app.missions.service import mission_service

    plan = MissionPlan(goal="g", steps=[step(1, None, [], desc="do a thing")])
    workflow = WorkflowState(user_request="r")
    summary = mission_engine.run(workflow, plan)

    mission_service._persist_planned("m-empty", workflow, "r", plan, summary)

    assert mission_service.blocked_step_input("m-empty") is None


# --- The planner must see each capability's real arguments ---------------

def test_catalog_shows_parameter_names_so_the_planner_stops_guessing():
    """Found live 22 Aug: the planner called write_brief(rows, cagr) and
    the second positional parameter is `title`, so the mission's headline
    finding was rendered as the document's title and the brief opened
    with a raw JSON blob. Every step said EXECUTED; the artifact was
    wrong. Positional arguments punish a wrong guess silently, so the
    planner has to be told the parameter names.
    """
    from app.capabilities.declarations import capability_catalog

    catalog = capability_catalog()

    assert "write_brief(findings, title=<optional>," in catalog
    assert "calculator(expression)" in catalog
    assert "read_dataset(sql)" in catalog


def test_unimplemented_capabilities_carry_no_signature():
    """A declared capability has no function to introspect, and inventing
    one would tell the planner something untrue about a gap.
    """
    from app.capabilities.declarations import capability_catalog

    line = next(
        l for l in capability_catalog().splitlines()
        if l.startswith("- extract_entities")
    )

    assert line.startswith("- extract_entities (NOT IMPLEMENTED")


def test_sandbox_proxies_are_left_bare_rather_than_shown_as_varargs():
    """An acquired capability is a proxy with signature (*args). Printing
    that would be a confident non-answer; silence is the honest form.
    """
    from app.capabilities.declarations import _signature_of

    registry.register(
        "emits_rows", "A proxy-shaped callable.", "LOW",
        lambda *args: {"status": "SUCCESS"},
    )

    assert _signature_of("emits_rows") == ""
