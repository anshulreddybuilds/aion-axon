"""GET /missions/{mission_id}/acquire/stream -- the streaming variant of
the existing mission-acquire endpoint, added so a voice/text mission
that BLOCKS on a real capability gap can show the SAME live SYNAPSE
stages (research -> generate -> safety -> sandbox -> evaluate ->
guardian -> approval) that a standalone acquisition already streams via
GET /synapse/propose/stream.

Not a second pipeline: this route and POST /missions/{id}/acquire share
_need_for_blocked_mission() (the gap-derivation logic) and both drive
synapse.propose_stream()/propose() -- the exact same generator engine.py
already exposes. These tests exist to prove that sharing holds, not to
re-test propose_stream() itself (already covered by
tests/test_synapse_stream.py).
"""
import json
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")
os.environ.setdefault("AXON_OWNER_TOKEN", "test-owner-token")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.agents.plan_schema import MissionPlan, MissionStep  # noqa: E402
from app.api import app  # noqa: E402
from app.capabilities.bootstrap import register_default_capabilities  # noqa: E402
from app.capabilities.registry import registry  # noqa: E402
from app.governance.rate_limit import propose_limiter  # noqa: E402
from app.memory.firestore_store import firestore_store  # noqa: E402
from app.missions.engine import mission_engine  # noqa: E402
from app.missions.service import mission_service  # noqa: E402
from app.synapse import engine as engine_module  # noqa: E402
from app.synapse.generator import Candidate  # noqa: E402
from app.workflows.state import WorkflowState  # noqa: E402

TOKEN = {"X-Axon-Token": "test-owner-token"}
owner = TestClient(app, headers=TOKEN)
anonymous = TestClient(app)

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
    # Un-implement write_brief so blocked_mission()'s step 2 is a genuine
    # gap (mission_engine.run() only blocks on a capability that really
    # isn't registered). declare() alone would leave it that way forever
    # after unregister() -- it only backfills a MISSING entry, it never
    # restores a real implementation -- so teardown below must actively
    # re-run the real bootstrap registration, not just declare() again.
    # Found by running this file ahead of tests/test_brief_writer.py in
    # the full suite: declare()-only teardown left write_brief looking
    # unimplemented for every test after this file, alphabetical
    # collection order be damned.
    registry.unregister("write_brief")
    registry.declare("write_brief", "Writes an executive brief.", "LOW")
    propose_limiter.reset()
    yield
    firestore_store.missions.clear()
    firestore_store.capabilities.clear()
    registry.unregister("write_brief")
    register_default_capabilities()
    propose_limiter.reset()


def blocked_mission(mission_id: str = "mission-under-test") -> str:
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
    workflow = WorkflowState(user_request="total then brief")
    summary = mission_engine.run(workflow, plan)
    assert summary["status"] == "BLOCKED"
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
        lambda need, notes=None, prior_failure=None: (Candidate(
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


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        event_type, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event_type = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((event_type, data))
    return events


def test_stream_requires_owner_token():
    mission_id = blocked_mission()
    resp = anonymous.get(f"/missions/{mission_id}/acquire/stream")
    assert resp.status_code in (401, 403)


def test_stream_reaches_awaiting_approval_for_the_real_gap(monkeypatch):
    mission_id = blocked_mission()
    patch_synapse(monkeypatch)

    resp = owner.get(f"/missions/{mission_id}/acquire/stream")
    assert resp.status_code == 200
    events = parse_sse(resp.text)
    stages = [data["stage"] for _, data in events]

    assert stages == [
        "GUARDIAN_PRESCREEN", "RESEARCH", "GENERATE", "SAFETY_SCREEN",
        "SANDBOX_TEST", "EVALUATE", "GUARDIAN_SCREEN", "AWAITING_APPROVAL",
    ]

    final = events[-1][1]
    assert final["status"] == "AWAITING_APPROVAL"
    assert final["candidate"]["name"] == "write_brief"
    # The mission link is real, not cosmetic: this is what lets a later
    # install() resume the ORIGINAL mission automatically.
    assert final["mission_id"] == mission_id

    registry.unregister("write_brief")


def test_stream_on_unknown_mission_is_a_real_error_not_an_empty_stream():
    resp = owner.get("/missions/does-not-exist/acquire/stream")
    assert resp.status_code == 200  # a stream always opens 200; the error is IN the stream
    events = parse_sse(resp.text)
    assert len(events) == 1
    event_type, data = events[0]
    assert event_type == "error"
    assert data["status"] == "NOT_FOUND"


def test_stream_on_a_mission_that_is_not_blocked_is_a_real_error():
    mission_id = "not-blocked-mission"
    workflow = WorkflowState(user_request="already done")
    mission_service._persist_planned(
        mission_id, workflow, "already done",
        MissionPlan(goal="x", steps=[]),
        {"status": "COMPLETED", "steps_completed": 0, "steps_total": 0,
         "step_results": [], "next_step_index": 0},
    )
    resp = owner.get(f"/missions/{mission_id}/acquire/stream")
    events = parse_sse(resp.text)
    assert len(events) == 1
    event_type, data = events[0]
    assert event_type == "error"
    assert data["status"] == "FAILED"
    assert "not BLOCKED" in data["error"]


def test_stream_error_mid_pipeline_is_also_recorded_server_side(monkeypatch):
    """Before this fix, a stage that raised mid-stream sent the client an
    error event (the previous two tests) but left no server-side trace
    at all -- the only way to debug it after the fact was to reproduce
    it live. synapse.propose_stream() is replaced with a fake generator
    that raises, matching exactly what the route's own except block is
    designed to catch, regardless of which real internal fault would
    normally produce it."""
    mission_id = blocked_mission()

    def raising_stream(need, mission_id=None):
        if False:
            yield  # pragma: no cover -- makes this a generator function
        raise RuntimeError("simulated mid-stream failure")

    from app.synapse.engine import synapse
    monkeypatch.setattr(synapse, "propose_stream", raising_stream)

    before = len(firestore_store.list_audit_events())
    resp = owner.get(f"/missions/{mission_id}/acquire/stream")
    events = parse_sse(resp.text)

    assert len(events) == 1
    event_type, data = events[0]
    assert event_type == "error"
    assert "simulated mid-stream failure" in data["error"]

    audit_events = firestore_store.list_audit_events()
    assert len(audit_events) == before + 1
    recorded = audit_events[0]
    assert recorded["event_type"] == "ACQUIRE_STREAM_ERROR"
    assert recorded["mission_id"] == mission_id
    assert "simulated mid-stream failure" in recorded["error"]


def test_sync_and_streaming_acquire_derive_the_identical_need(monkeypatch):
    """Proves the shared _need_for_blocked_mission() helper actually
    keeps both routes in sync -- the exact regression a hand-duplicated
    second copy of this logic would eventually drift into."""
    mission_id_a = blocked_mission("mission-a")
    mission_id_b = blocked_mission("mission-b")
    patch_synapse(monkeypatch)

    sync_result = owner.post(f"/missions/{mission_id_a}/acquire", json={}).json()
    registry.unregister("write_brief")

    stream_events = parse_sse(
        owner.get(f"/missions/{mission_id_b}/acquire/stream").text
    )
    stream_result = stream_events[-1][1]

    assert sync_result["candidate"]["name"] == stream_result["candidate"]["name"]
    assert sync_result["research"] == stream_result["research"]

    registry.unregister("write_brief")
