"""Stage 12 — the loop actually closes.

The demo says: "it hit a gap, acquired the capability, and then finished
the job." Until now that last clause was performed by a human re-running
the mission. These tests are about that clause being code.

The property that matters most is NOT that resume works — it is that
resume cannot be used to skip a step that is still genuinely blocked.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

import pytest  # noqa: E402

import app.capabilities.bootstrap  # noqa: E402,F401
from app.agents.plan_schema import MissionPlan, MissionStep  # noqa: E402
from app.capabilities.registry import registry  # noqa: E402
from app.memory.firestore_store import firestore_store  # noqa: E402
from app.missions.service import mission_service  # noqa: E402
from app.synapse import engine as engine_module  # noqa: E402
from app.synapse.engine import synapse  # noqa: E402
from app.synapse.generator import Candidate  # noqa: E402

BRIEF_CODE = (
    "def write_brief(findings):\n"
    "    return {'status': 'SUCCESS', 'brief': 'BRIEF: ' + str(findings)}\n"
)


@pytest.fixture(autouse=True)
def clean():
    firestore_store.missions.clear()
    firestore_store.capabilities.clear()
    firestore_store.approvals.clear()
    firestore_store.evolution_events.clear()
    # declare() deliberately never overwrites a real implementation, so an
    # install from a previous test would survive into this one.
    registry.unregister("write_brief")
    registry.declare("write_brief", "Writes an executive brief.", "LOW")
    registry.unregister("summarize_notes_v1")
    yield
    firestore_store.missions.clear()
    firestore_store.capabilities.clear()
    registry.unregister("write_brief")
    registry.declare("write_brief", "Writes an executive brief.", "LOW")
    registry.unregister("summarize_notes_v1")


def blocked_mission() -> str:
    """A planned mission that runs step 1 and blocks on step 2."""
    plan = MissionPlan(
        goal="Total the invoice then brief me",
        steps=[
            MissionStep(
                step=1, description="calculate the total", kind="READ_ANALYZE",
                tool="calculator", args=["1250 * 1.18"], risk="LOW",
                action="add numbers",
            ),
            MissionStep(
                step=2, description="write an executive brief",
                kind="READ_ANALYZE", tool="write_brief", args=["1475.0"],
                risk="LOW", action="write the brief",
            ),
        ],
    )

    from app.workflows.state import WorkflowState
    from app.missions.engine import mission_engine

    workflow = WorkflowState(user_request="total then brief")
    summary = mission_engine.run(workflow, plan)

    assert summary["status"] == "BLOCKED"

    mission_id = "mission-under-test"
    mission_service._persist_planned(
        mission_id, workflow, "total then brief", plan, summary,
    )

    return mission_id


def patch_synapse(monkeypatch):
    monkeypatch.setattr(
        engine_module, "search_web",
        lambda q: {"status": "DEGRADED", "grounded": False, "sources": [],
                   "findings": "n", "source_count": 0},
    )
    monkeypatch.setattr(
        engine_module, "generate_candidate",
        lambda need, notes=None: (Candidate(
            name="write_brief", description="Writes an executive brief.",
            risk="LOW", code=BRIEF_CODE, test="print('OK')",
            entrypoint="write_brief",
        ), None),
    )
    monkeypatch.setattr(
        engine_module, "execute_in_sandbox",
        lambda code, test="", timeout_seconds=10: {
            "status": "COMPLETED", "passed": True,
            "stdout": '{"status": "SUCCESS", "brief": "BRIEF: 1475.0"}',
            "stderr": "",
        },
    )
    monkeypatch.setattr(
        engine_module, "evaluate",
        lambda *a, **k: {"status": "SCORED", "score": 90, "verdict": "PASS",
                         "reason": "fine"},
    )


# --- The gap is real ------------------------------------------------------

def test_mission_blocks_on_the_missing_capability():
    mission_id = blocked_mission()
    mission = firestore_store.get_mission(mission_id)

    assert mission["status"] == "BLOCKED"
    assert mission["steps_completed"] == 1
    assert mission["blocked_on"]["missing_capability"] == "write_brief"


# --- Resume cannot skip a still-missing capability ------------------------

def test_resume_before_acquisition_blocks_again():
    """The important one: resume must not paper over an unfilled gap."""
    mission_id = blocked_mission()

    result = mission_service.resume_blocked(mission_id)

    assert result["status"] == "BLOCKED"
    assert result["steps_completed"] == 1


def test_resume_refuses_a_mission_that_is_not_blocked():
    mission_id = blocked_mission()

    firestore_store.save_mission(mission_id, {"status": "COMPLETED"})

    result = mission_service.resume_blocked(mission_id)

    assert result["status"] == "FAILED"
    assert "not blocked" in result["error"].lower()


def test_resume_refuses_an_unknown_mission():
    assert mission_service.resume_blocked("nope")["status"] == "FAILED"


# --- The loop closes ------------------------------------------------------

def test_install_finishes_the_mission_it_unblocked(monkeypatch):
    """gap -> acquire -> approve -> install -> the ORIGINAL job completes."""
    patch_synapse(monkeypatch)

    mission_id = blocked_mission()

    record = synapse.propose(
        "Writes an executive brief.", mission_id=mission_id,
    )

    assert record.status == "AWAITING_APPROVAL"
    assert record.mission_id == mission_id

    firestore_store.update_approval(
        record.approval_request_id, approved=True, decided_by="anshul",
    )

    result = synapse.install("write_brief")

    assert result["status"] == "INSTALLED"

    resumed = result.get("mission_resumed")

    assert resumed is not None, "install did not resume the mission"
    assert resumed["status"] == "COMPLETED"
    assert resumed["steps_completed"] == 2

    mission = firestore_store.get_mission(mission_id)
    assert mission["status"] == "COMPLETED"


def test_completed_step_one_is_not_re_executed(monkeypatch):
    """Resuming must continue, not replay.

    Replaying an EXTERNAL_EFFECT step would perform it twice.
    """
    patch_synapse(monkeypatch)

    mission_id = blocked_mission()

    before = firestore_store.get_mission(mission_id)["step_results"][0]

    record = synapse.propose("Writes an executive brief.", mission_id)
    firestore_store.update_approval(
        record.approval_request_id, approved=True, decided_by="anshul",
    )
    synapse.install("write_brief")

    after = firestore_store.get_mission(mission_id)["step_results"][0]

    assert after["at"] == before["at"], "step 1 was executed a second time"


def test_acquisition_without_a_mission_installs_normally(monkeypatch):
    """Not every acquisition unblocks a mission."""
    patch_synapse(monkeypatch)

    record = synapse.propose("Writes an executive brief.")

    assert record.mission_id is None

    firestore_store.update_approval(
        record.approval_request_id, approved=True, decided_by="anshul",
    )

    result = synapse.install("write_brief")

    assert result["status"] == "INSTALLED"
    assert "mission_resumed" not in result


def blocked_mission_with_unnamed_gap() -> str:
    """A planned mission whose blocked step has tool=None.

    This is a DIFFERENT gap shape than `blocked_mission()` above: the
    planner found no registered capability at all for the step, not an
    unimplemented one it could name. Found live 21 Aug: install() never
    backfilled this null with the name of what it just installed, so the
    mission stayed BLOCKED forever even after a successful acquisition.
    """
    plan = MissionPlan(
        goal="Summarize the notes",
        steps=[
            MissionStep(
                step=1, description="summarize the notes",
                kind="READ_ANALYZE", tool=None, args=[], risk="LOW",
                action="summarize_notes",
            ),
        ],
    )

    from app.workflows.state import WorkflowState
    from app.missions.engine import mission_engine

    workflow = WorkflowState(user_request="summarize the notes")
    summary = mission_engine.run(workflow, plan)

    assert summary["status"] == "BLOCKED"
    assert summary["blocked_on"]["missing_capability"] is None

    mission_id = "mission-under-test-null-tool"
    mission_service._persist_planned(
        mission_id, workflow, "summarize the notes", plan, summary,
    )

    return mission_id


def patch_synapse_for_unnamed_gap(monkeypatch):
    """Candidate name has no relation to anything in the plan -- there
    was no name for the planner to give it.
    """
    monkeypatch.setattr(
        engine_module, "search_web",
        lambda q: {"status": "DEGRADED", "grounded": False, "sources": [],
                   "findings": "n", "source_count": 0},
    )
    monkeypatch.setattr(
        engine_module, "generate_candidate",
        lambda need, notes=None: (Candidate(
            name="summarize_notes_v1", description="Summarizes notes.",
            risk="LOW", code=(
                "def summarize_notes_v1(text):\n"
                "    return {'status': 'SUCCESS', 'summary': text[:10]}\n"
            ),
            test="print('OK')", entrypoint="summarize_notes_v1",
        ), None),
    )
    monkeypatch.setattr(
        engine_module, "execute_in_sandbox",
        lambda code, test="", timeout_seconds=10: {
            "status": "COMPLETED", "passed": True,
            "stdout": '{"status": "SUCCESS", "summary": "hi"}',
            "stderr": "",
        },
    )
    monkeypatch.setattr(
        engine_module, "evaluate",
        lambda *a, **k: {"status": "SCORED", "score": 90, "verdict": "PASS",
                         "reason": "fine"},
    )


def test_install_finishes_a_mission_whose_gap_had_no_tool_name(monkeypatch):
    """The bug found live 21 Aug: a `tool: null` step never got backfilled
    with the name of the capability that was just installed for it, so
    the mission stayed BLOCKED forever -- even though `mission_resumed`
    was present in the install response, proving resume_blocked DID run.
    install() must pass its capability_name into resume_blocked so the
    step can name what will actually run it.
    """
    patch_synapse_for_unnamed_gap(monkeypatch)

    mission_id = blocked_mission_with_unnamed_gap()

    record = synapse.propose("Summarizes notes.", mission_id=mission_id)

    assert record.status == "AWAITING_APPROVAL"

    firestore_store.update_approval(
        record.approval_request_id, approved=True, decided_by="anshul",
    )

    result = synapse.install("summarize_notes_v1")

    assert result["status"] == "INSTALLED"

    resumed = result.get("mission_resumed")

    assert resumed is not None, "install did not resume the mission"
    assert resumed["status"] == "COMPLETED", (
        "mission stayed BLOCKED even though a matching capability was "
        "just installed -- the blocked step's tool was never backfilled"
    )

    mission = firestore_store.get_mission(mission_id)
    assert mission["status"] == "COMPLETED"
    assert (
        mission["plan_document"]["steps"][0]["tool"]
        == "summarize_notes_v1"
    )


def test_rejected_approval_leaves_the_mission_blocked(monkeypatch):
    """A refused acquisition must not quietly finish the job anyway."""
    patch_synapse(monkeypatch)

    mission_id = blocked_mission()

    record = synapse.propose("Writes an executive brief.", mission_id)

    firestore_store.update_approval(
        record.approval_request_id, approved=False, decided_by="anshul",
    )

    result = synapse.install("write_brief")

    assert result["status"] == "APPROVAL_REQUIRED"
    assert firestore_store.get_mission(mission_id)["status"] == "BLOCKED"
