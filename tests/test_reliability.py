"""Reliability — Days 9-10: cold start, idempotency, approval recovery.

The demo runs on a scale-to-zero service, on a laptop, once, in front of
judges. These tests cover the failures that only show up under those
conditions: a container that just booted, a request that arrives twice,
and an approval whose workflow no longer exists in anyone's memory.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import app  # noqa: E402
from app.capabilities.registry import registry  # noqa: E402
from app.governance.approval import approval_manager  # noqa: E402
from app.governance.guardian import RiskLevel  # noqa: E402
from app.governance.kill_switch import kill_switch  # noqa: E402
from app.memory.firestore_store import firestore_store  # noqa: E402
from app.missions.service import mission_service  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean():
    kill_switch.deactivate()
    firestore_store.missions.clear()
    firestore_store.approvals.clear()
    yield
    kill_switch.deactivate()


# --- Cold start -----------------------------------------------------------

def test_service_answers_immediately_after_boot():
    """A cold container must serve, not 500 while it warms up."""
    with TestClient(app) as cold:
        assert cold.get("/health").json() == {"status": "OK"}
        assert cold.get("/").json()["status"] == "LIVE"


def test_rehydration_runs_before_the_first_request():
    """The registry must be reconciled before traffic, not lazily."""
    with TestClient(app) as cold:
        body = cold.get("/capabilities").json()

    assert body["rehydrated"] is not None, (
        "rehydration did not run during startup"
    )


def test_cold_start_does_not_lose_the_kill_switch_state():
    """A restart must not silently re-enable a killed agent."""
    kill_switch.activate("stopped before restart")

    with TestClient(app) as cold:
        assert cold.get("/killswitch").json()["kill_switch_active"] is True

    kill_switch.deactivate()


# --- Idempotency ----------------------------------------------------------

def test_deciding_an_approval_twice_is_refused():
    """A double-click must not count as two decisions."""
    request = approval_manager.create(
        action="purchase item", risk=RiskLevel.MEDIUM, reason="needs a human",
    )

    first = client.post(f"/approvals/{request.request_id}/decide",
                        json={"approved": True, "decided_by": "anshul"})
    second = client.post(f"/approvals/{request.request_id}/decide",
                         json={"approved": False, "decided_by": "anshul"})

    assert first.json()["status"] == "APPROVED"
    assert second.json()["status"] == "ALREADY_DECIDED"

    stored = firestore_store.get_approval(request.request_id)
    assert stored["status"] == "APPROVED", (
        "a second decision overwrote the first"
    )


def test_resuming_a_completed_mission_does_not_run_it_again():
    """Replaying an EXTERNAL_EFFECT step would perform it twice."""
    created = mission_service.start(
        request="totals", tool="calculator", action="purchase item",
        risk="MEDIUM", args=["1250 * 1.18"],
    )

    mission_id = created["mission_id"]
    request_id = created["approval_request_id"]

    firestore_store.update_approval(
        request_id, approved=True, decided_by="anshul",
    )

    first = mission_service.resume(mission_id)
    assert first["result"]["status"] == "EXECUTED"

    second = mission_service.resume(mission_id)
    assert second["status"] == "FAILED"
    assert "not awaiting approval" in second["error"].lower()


def test_installing_the_same_capability_twice_is_safe():
    """A retried install must not corrupt the registry or double-count."""
    firestore_store.save_capability("twice_skill", {
        "name": "twice_skill",
        "description": "adds one",
        "risk": "LOW",
        "state": "VALIDATING",
        "implemented": False,
        "version": 0,
        "passport": {
            "need": "add one",
            "approval_request_id": "approval-twice",
            "candidate": {
                "name": "twice_skill",
                "description": "adds one",
                "risk": "LOW",
                "code": "def add_one(v):\n    return {'status': 'SUCCESS'}\n",
                "entrypoint": "add_one",
            },
        },
    })
    firestore_store.approvals["approval-twice"] = {
        "status": "APPROVED", "decided_by": "anshul",
        "action": "install", "risk": "LOW", "reason": "ok",
    }

    from app.synapse.engine import synapse

    first = synapse.install("twice_skill")
    second = synapse.install("twice_skill")

    assert first["status"] == "INSTALLED"
    assert second["status"] == "INSTALLED"

    names = [t["name"] for t in registry.list_tools()]
    assert names.count("twice_skill") == 1, "registry duplicated a capability"

    registry.unregister("twice_skill")


# --- Approval recovery ----------------------------------------------------

def test_approval_survives_a_process_restart():
    """The demo approves in one request and resumes in another.

    On Cloud Run those can land on different instances, so the decision
    has to live in Firestore rather than in anyone's memory.
    """
    created = mission_service.start(
        request="totals", tool="calculator", action="purchase item",
        risk="MEDIUM", args=["10 * 10"],
    )

    request_id = created["approval_request_id"]

    firestore_store.update_approval(
        request_id, approved=True, decided_by="anshul",
    )

    # Simulate a fresh process: the manager's local cache is empty.
    approval_manager.pending.clear()

    recovered = approval_manager.get(request_id)

    assert recovered is not None
    assert recovered.approved is True
    assert recovered.decided_by == "anshul"


def test_resume_works_after_the_local_cache_is_lost():
    created = mission_service.start(
        request="totals", tool="calculator", action="purchase item",
        risk="MEDIUM", args=["7 * 6"],
    )

    firestore_store.update_approval(
        created["approval_request_id"], approved=True, decided_by="anshul",
    )

    approval_manager.pending.clear()

    resumed = mission_service.resume(created["mission_id"])

    assert resumed["result"]["status"] == "EXECUTED"
    assert resumed["result"]["result"]["result"] == 42.0


def test_unknown_approval_does_not_crash_the_resume():
    created = mission_service.start(
        request="totals", tool="calculator", action="purchase item",
        risk="MEDIUM", args=["1 + 1"],
    )

    firestore_store.approvals.pop(created["approval_request_id"], None)
    approval_manager.pending.clear()

    resumed = mission_service.resume(created["mission_id"])

    assert resumed["result"]["status"] in ("FAILED", "APPROVAL_REQUIRED")


# --- Error paths ----------------------------------------------------------

def test_a_tool_that_raises_is_reported_not_propagated():
    """A crashing tool must fail the step, not the service."""
    def explodes(*args):
        raise RuntimeError("boom")

    registry.register("explodes", "always raises", "LOW", explodes)

    try:
        from app.governance.execution_gate import execution_gate

        result = execution_gate.execute(
            "run it", RiskLevel.LOW, explodes,
        )

        assert result["status"] == "FAILED"
        assert "boom" in result["error"]
    finally:
        registry.unregister("explodes")


def test_unknown_capability_is_a_clean_capability_gap():
    """A typo in a tool name must not 500 with a stack trace.

    "The agent crashed" and "the agent cannot do that yet" are different
    statements, and only the second is true -- it is also the one SYNAPSE
    acts on.
    """
    body = client.post("/missions", json={
        "request": "x", "tool": "does_not_exist",
        "action": "run", "risk": "LOW", "args": [],
    })

    assert body.status_code == 200

    result = body.json()["result"]

    assert result["status"] == "BLOCKED"
    assert result["missing_capability"] == "does_not_exist"


def test_declared_but_unbuilt_capability_is_also_a_gap():
    body = client.post("/missions", json={
        "request": "x", "tool": "write_brief",
        "action": "write the brief", "risk": "LOW", "args": [],
    })

    result = body.json()["result"]

    assert result["status"] == "BLOCKED"
    assert result["missing_capability"] == "write_brief"
