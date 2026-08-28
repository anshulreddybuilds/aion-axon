"""Reliability — Days 9-10: cold start, idempotency, approval recovery.

The demo runs on a scale-to-zero service, on a laptop, once, in front of
judges. These tests cover the failures that only show up under those
conditions: a container that just booted, a request that arrives twice,
and an approval whose workflow no longer exists in anyone's memory.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")
os.environ.setdefault("AXON_OWNER_TOKEN", "test-owner-token")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import app  # noqa: E402
from app.capabilities.registry import registry  # noqa: E402
from app.governance.approval import approval_manager  # noqa: E402
from app.governance.guardian import RiskLevel  # noqa: E402
from app.governance.kill_switch import kill_switch  # noqa: E402
from app.memory.firestore_store import firestore_store  # noqa: E402
from app.missions.service import mission_service  # noqa: E402

client = TestClient(app, headers={"X-Axon-Token": "test-owner-token"})


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
    with TestClient(app, headers={"X-Axon-Token": "test-owner-token"}) as cold:
        assert cold.get("/health").json() == {"status": "OK"}
        assert cold.get("/").json()["status"] == "LIVE"


def test_rehydration_runs_before_the_first_request():
    """The registry must be reconciled before traffic, not lazily."""
    with TestClient(app, headers={"X-Axon-Token": "test-owner-token"}) as cold:
        body = cold.get("/capabilities").json()

    assert body["rehydrated"] is not None, (
        "rehydration did not run during startup"
    )


def test_cold_start_does_not_lose_the_kill_switch_state():
    """A restart must not silently re-enable a killed agent."""
    kill_switch.activate("stopped before restart")

    with TestClient(app, headers={"X-Axon-Token": "test-owner-token"}) as cold:
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
    """A retried/replayed install must not corrupt the registry, double-
    count the version, or duplicate the ledger event.

    Batch 2 (state integrity): this test originally only checked that the
    registry didn't grow a duplicate entry, which registry.register()
    already made trivially true (it overwrites, not appends) even before
    a real bug was found and fixed here -- registry non-duplication was
    never actually the broken invariant. The real bug, confirmed live: a
    second install() call on an already-installed capability with the
    same still-APPROVED approval silently re-ran the entire install path,
    bumping `version` 1->2 and writing a SECOND evolution event for the
    same real-world action. install() now recognises a replay of the
    SAME approval_request_id against an already-READY capability and
    returns ALREADY_INSTALLED without touching the registry, version, or
    ledger again -- distinguishable from a fresh INSTALLED on purpose, so
    a caller (or the frontend) can tell a genuine new install from a
    no-op replay.
    """
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

    events_before = len(firestore_store.list_evolution_events())

    first = synapse.install("twice_skill")
    second = synapse.install("twice_skill")
    third = synapse.install("twice_skill")

    assert first["status"] == "INSTALLED"
    assert second["status"] == "ALREADY_INSTALLED"
    assert third["status"] == "ALREADY_INSTALLED"

    names = [t["name"] for t in registry.list_tools()]
    assert names.count("twice_skill") == 1, "registry duplicated a capability"

    assert firestore_store.get_capability("twice_skill")["version"] == 1, (
        "a replayed install must not bump the version again"
    )
    assert len(firestore_store.list_evolution_events()) == events_before + 1, (
        "a replayed install must not write a second evolution event"
    )

    registry.unregister("twice_skill")


def test_approving_one_capability_cannot_install_a_different_one():
    """Phase 28C forensics: PROPOSAL != APPROVAL != INSTALL, and an old or
    unrelated approval can never authorize a DIFFERENT capability.

    Sets up two real, independently-proposed capabilities (A and B), each
    with its own real approval_request_id -- exactly how synapse.propose()
    actually produces them, never reusing an ID across proposals. Approves
    ONLY A's request. install(B) must find B's OWN passport's OWN
    approval_request_id (still pending) and refuse -- there is no code
    path by which A's APPROVED status could leak into B's install check,
    but this proves it structurally rather than by reading the source."""
    firestore_store.save_capability("capability_a", {
        "name": "capability_a", "description": "does a", "risk": "LOW",
        "state": "VALIDATING", "implemented": False, "version": 0,
        "passport": {
            "need": "do a", "approval_request_id": "approval-for-a",
            "candidate": {
                "name": "capability_a", "description": "does a", "risk": "LOW",
                "code": "def capability_a(): return 'a'\n", "entrypoint": "capability_a",
            },
        },
    })
    firestore_store.save_capability("capability_b", {
        "name": "capability_b", "description": "does b", "risk": "LOW",
        "state": "VALIDATING", "implemented": False, "version": 0,
        "passport": {
            "need": "do b", "approval_request_id": "approval-for-b",
            "candidate": {
                "name": "capability_b", "description": "does b", "risk": "LOW",
                "code": "def capability_b(): return 'b'\n", "entrypoint": "capability_b",
            },
        },
    })
    # Only A's request is approved. B's stays PENDING (the Firestore
    # default -- get_approval() on an unset id returns None, matching
    # what a real never-decided request looks like).
    firestore_store.approvals["approval-for-a"] = {
        "status": "APPROVED", "decided_by": "anshul",
        "action": "install", "risk": "LOW", "reason": "ok",
    }

    from app.synapse.engine import synapse

    result_a = synapse.install("capability_a")
    result_b = synapse.install("capability_b")

    assert result_a["status"] == "INSTALLED"
    assert result_b["status"] == "APPROVAL_REQUIRED", (
        "capability_b was installed using capability_a's approval -- "
        "a real cross-capability authorization bypass"
    )

    names = [t["name"] for t in registry.list_tools()]
    assert "capability_a" in names
    assert "capability_b" not in names

    registry.unregister("capability_a")


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
    """Real bug, not a flake, found and fixed this pass: this test
    hardcoded "write_brief" as an example of an unimplemented capability,
    but write_brief has genuinely been implemented for a while (real
    function registered in app/capabilities/bootstrap.py,
    `implemented=True` in app/capabilities/seed.py) -- confirmed by
    source inspection. The test failed honestly when run in a way that
    left the shared registry in its natural default state, and only
    "passed" as part of a larger ordered run by accident. Anchoring to
    "whatever is still unbuilt" (same fix already applied to
    tests/test_adversarial.py and tests/test_monitors.py for this exact
    class of problem) keeps the property covered as capabilities get
    implemented, instead of decaying as the code improves."""
    declared_only = [
        tool["name"] for tool in registry.list_tools()
        if not tool["implemented"]
    ]

    assert declared_only, (
        "Every capability is implemented, so there is nothing left to "
        "prove this property against."
    )

    tool_name = declared_only[0]

    body = client.post("/missions", json={
        "request": "x", "tool": tool_name,
        "action": "run it", "risk": "LOW", "args": [],
    })

    result = body.json()["result"]

    assert result["status"] == "BLOCKED"
    assert result["missing_capability"] == tool_name


# --- Phase 28I: the real mission path must not trust an empty need --------

def test_empty_need_is_refused_before_spending_a_real_gemini_or_sandbox_call():
    response = client.post("/synapse/propose", json={"need": ""})
    assert response.status_code == 422


def test_too_short_a_need_is_refused_the_same_way():
    response = client.post("/synapse/propose", json={"need": "ab"})
    assert response.status_code == 422
