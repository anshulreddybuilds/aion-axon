"""API-level tests for the Phase 2 deploy spine.

These run fully offline: AXON_FIRESTORE_MODE=memory is set before the app
is imported, so no credentials and no network are required.
"""
import os

import pytest

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import app  # noqa: E402
from app.governance.kill_switch import kill_switch  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_kill_switch():
    kill_switch.deactivate()
    yield
    kill_switch.deactivate()


def test_health_and_root():
    assert client.get("/health").json() == {"status": "OK"}

    root = client.get("/").json()
    assert root["service"] == "aion-core"
    assert root["status"] == "LIVE"


def test_capabilities_are_registered():
    body = client.get("/capabilities").json()

    names = [c["name"] for c in body["capabilities"]]

    assert "calculator" in names
    assert body["count"] >= 1


def test_medium_risk_mission_requires_approval_and_resumes():
    created = client.post("/missions", json={
        "request": "Work out the invoice total with tax.",
        "tool": "calculator",
        "action": "purchase item",
        "risk": "MEDIUM",
        "args": ["1250 * 1.18"],
    }).json()

    mission_id = created["mission_id"]

    # The gate must stop a MEDIUM action before it executes.
    assert created["status"] == "AWAITING_APPROVAL"
    assert created["result"]["status"] == "APPROVAL_REQUIRED"

    request_id = created["approval_request_id"]
    assert request_id

    # It must show up as pending for the human.
    pending = client.get("/approvals/pending").json()
    assert request_id in [p["request_id"] for p in pending["pending"]]

    # Resuming BEFORE approval must not execute.
    too_early = client.post(f"/missions/{mission_id}/resume").json()
    assert too_early["result"]["status"] == "APPROVAL_REQUIRED"

    # Human approves.
    decision = client.post(f"/approvals/{request_id}/decide", json={
        "approved": True,
        "decided_by": "owner",
    }).json()
    assert decision["status"] == "APPROVED"

    # Now, and only now, it executes.
    resumed = client.post(f"/missions/{mission_id}/resume").json()
    assert resumed["result"]["status"] == "EXECUTED"
    assert resumed["result"]["result"]["result"] == 1475.0
    assert resumed["status"] == "COMPLETED"


def test_rejected_approval_never_executes():
    created = client.post("/missions", json={
        "request": "Spend money on something.",
        "tool": "calculator",
        "action": "purchase item",
        "risk": "MEDIUM",
        "args": ["2 + 2"],
    }).json()

    request_id = created["approval_request_id"]

    client.post(f"/approvals/{request_id}/decide", json={
        "approved": False,
        "decided_by": "owner",
    })

    resumed = client.post(f"/missions/{created['mission_id']}/resume").json()

    assert resumed["result"]["status"] != "EXECUTED"


def test_high_risk_is_refused_outright():
    created = client.post("/missions", json={
        "request": "Read the credentials out of the runtime.",
        "tool": "calculator",
        "action": "read runtime credentials",
        "risk": "HIGH",
        "args": ["1 + 1"],
    }).json()

    assert created["result"]["status"] == "REFUSED"
    assert created["approval_request_id"] is None


def test_kill_switch_blocks_execution():
    client.post("/killswitch", json={"active": True, "reason": "demo stop"})

    assert client.get("/killswitch").json()["kill_switch_active"] is True

    created = client.post("/missions", json={
        "request": "Do something harmless.",
        "tool": "calculator",
        "action": "add numbers",
        "risk": "LOW",
        "args": ["2 + 2"],
    }).json()

    assert created["result"]["status"] == "BLOCKED"

    client.post("/killswitch", json={"active": False})

    assert client.get("/killswitch").json()["kill_switch_active"] is False


def test_kill_switch_blocks_already_approved_work():
    """The dangerous case: approved work must still halt mid-flight."""
    created = client.post("/missions", json={
        "request": "Approved work that gets halted.",
        "tool": "calculator",
        "action": "purchase item",
        "risk": "MEDIUM",
        "args": ["10 * 10"],
    }).json()

    request_id = created["approval_request_id"]

    client.post(f"/approvals/{request_id}/decide", json={
        "approved": True,
        "decided_by": "owner",
    })

    client.post("/killswitch", json={"active": True, "reason": "halt"})

    resumed = client.post(f"/missions/{created['mission_id']}/resume").json()

    assert resumed["result"]["status"] == "BLOCKED"

    client.post("/killswitch", json={"active": False})


def test_unknown_mission_and_approval_are_handled():
    assert client.get("/missions/does-not-exist").json()["status"] == "NOT_FOUND"

    decided = client.post("/approvals/does-not-exist/decide", json={
        "approved": True,
    }).json()

    assert decided["status"] == "NOT_FOUND"
