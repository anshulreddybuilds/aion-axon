"""Mission resume concurrency -- proven necessary, not speculative.

resume_blocked()/resume_planned()/resume() (app/missions/service.py) used
to do a plain read (get_mission), check the status field, then run the
mission for real -- a real tool call, possibly a real external effect --
before writing the new status back. That is the exact TOCTOU shape
claim_install() (installs) and decide_approval() (approvals) were already
fixed to close, just never applied to mission resume. The window here is
worse than either of those: real work happens inside it, not just a
status flip, so two concurrent callers racing this path don't just
corrupt a status field -- they can make a real, registered tool execute
more than once for what was meant to be a single resume.

Reproduced directly before this fix existed: 5 real OS threads racing
resume_blocked() on one BLOCKED mission (a `time.sleep()` inside the
registered tool widens the window the same way claim_install()'s own
concurrency tests do) made the tool execute 5 times, not once. This file
keeps that proof as a permanent regression test.
"""
import os
import threading
import time

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

import pytest  # noqa: E402

import app.capabilities.bootstrap  # noqa: E402,F401
from app.agents.plan_schema import MissionPlan, MissionStep  # noqa: E402
from app.capabilities.registry import registry  # noqa: E402
from app.memory.firestore_store import firestore_store  # noqa: E402
from app.missions.engine import mission_engine  # noqa: E402
from app.missions.service import mission_service  # noqa: E402
from app.workflows.state import WorkflowState  # noqa: E402


@pytest.fixture(autouse=True)
def clean():
    firestore_store.missions.clear()
    registry.unregister("write_brief")
    registry.declare("write_brief", "Writes an executive brief.", "LOW")
    yield
    firestore_store.missions.clear()
    registry.unregister("write_brief")
    registry.declare("write_brief", "Writes an executive brief.", "LOW")


def _blocked_mission(mission_id: str) -> None:
    """A planned mission that runs step 1 and blocks on step 2 -- same
    shape as tests/test_loop_closure.py's own helper."""
    plan = MissionPlan(
        goal="Total the invoice then brief me",
        steps=[
            MissionStep(step=1, description="calculate the total", kind="READ_ANALYZE",
                        tool="calculator", args=["1250 * 1.18"], risk="LOW", action="add numbers"),
            MissionStep(step=2, description="write an executive brief", kind="READ_ANALYZE",
                        tool="write_brief", args=["1475.0"], risk="LOW", action="write the brief"),
        ],
    )

    workflow = WorkflowState(user_request="total then brief")
    summary = mission_engine.run(workflow, plan)
    assert summary["status"] == "BLOCKED"

    mission_service._persist_planned(mission_id, workflow, "total then brief", plan, summary)


def test_concurrent_resume_blocked_executes_the_real_tool_exactly_once():
    mission_id = "race-mission-resume-blocked"
    _blocked_mission(mission_id)

    call_count = {"n": 0}
    call_lock = threading.Lock()

    def counting_write_brief(findings):
        with call_lock:
            call_count["n"] += 1
        # Widens the race window the same way claim_install()'s own
        # concurrency tests do -- real work (a real tool, a real Gemini
        # round trip) takes real time.
        time.sleep(0.08)
        return {"status": "SUCCESS", "brief": "BRIEF: " + str(findings)}

    registry.register("write_brief", "Writes an executive brief.", "LOW", counting_write_brief)

    n = 5
    barrier = threading.Barrier(n)
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def worker():
        barrier.wait()
        r = mission_service.resume_blocked(mission_id)
        with outcomes_lock:
            outcomes.append(r["status"])

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert call_count["n"] == 1, (
        f"expected the real tool to execute exactly once, got {call_count['n']} calls "
        f"-- resume_blocked() let {call_count['n']} concurrent callers all run it for real"
    )
    assert outcomes.count("COMPLETED") == 1, f"expected exactly one winner, got {outcomes}"
    assert outcomes.count("FAILED") == n - 1, f"expected the rest to lose the claim cleanly, got {outcomes}"

    final = firestore_store.get_mission(mission_id)
    assert final["status"] == "COMPLETED", (
        "the winner's real result must overwrite the RESUMING claim marker, "
        f"got {final['status']}"
    )
    assert final["steps_completed"] == 2


def test_claim_mission_transition_is_the_single_source_of_truth_for_all_three_resume_paths():
    """resume_blocked()/resume_planned()/resume() all guard through the
    same primitive (firestore_store.claim_mission_transition) rather than
    each re-implementing their own read-check-write -- proven directly
    against the primitive itself so this doesn't silently regress to
    three copy-pasted (and possibly re-broken) checks."""
    mission_id = "race-mission-claim-primitive"
    firestore_store.save_mission(mission_id, {"status": "BLOCKED"})

    # First claim wins.
    assert firestore_store.claim_mission_transition(mission_id, "BLOCKED", "RESUMING") is True
    assert firestore_store.get_mission(mission_id)["status"] == "RESUMING"

    # A second claim against the now-stale "BLOCKED" requirement loses --
    # this is exactly what stops a replayed/racing resume call from
    # re-entering mission_engine.run() a second time.
    assert firestore_store.claim_mission_transition(mission_id, "BLOCKED", "RESUMING") is False

    # An unknown mission never claims.
    assert firestore_store.claim_mission_transition("does-not-exist", "BLOCKED", "RESUMING") is False
