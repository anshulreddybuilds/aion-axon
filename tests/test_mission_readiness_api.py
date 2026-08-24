"""GET /beastmode/mission/readiness -- real end-to-end, zero side effects."""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")
os.environ.setdefault("AXON_OWNER_TOKEN", "test-owner-token")

from fastapi.testclient import TestClient

from app.api import app
from app.memory.firestore_store import firestore_store

client = TestClient(app)  # no token -- this must be a public read


def test_reachable_without_an_owner_token():
    response = client.get("/beastmode/mission/readiness")
    assert response.status_code == 200


def test_overall_status_is_one_of_the_three_defined_values():
    body = client.get("/beastmode/mission/readiness").json()
    assert body["overall"] in ("READY", "READY_WITH_LIMITATIONS", "NOT_READY")


def test_real_mission_execution_is_always_reported_as_not_run():
    body = client.get("/beastmode/mission/readiness").json()
    assert body["real_mission_execution"] == "NOT_RUN"


def test_owner_auth_check_passes_when_a_token_is_configured():
    body = client.get("/beastmode/mission/readiness").json()
    check = next(c for c in body["checks"] if c["name"] == "owner_auth_configured")
    assert check["ready"] is True
    assert "test-owner-token" not in check["detail"]  # value never leaks into the response


def test_every_check_has_a_kind_of_live_or_structural():
    body = client.get("/beastmode/mission/readiness").json()
    for check in body["checks"]:
        assert check["kind"] in ("LIVE", "STRUCTURAL")


def test_not_a_numeric_percentage_score():
    """The directive is explicit: no manufactured '98% ready' score."""
    body = client.get("/beastmode/mission/readiness").json()
    assert "percent" not in str(body).lower()
    assert "score" not in body


def test_endpoint_has_zero_side_effects():
    before_caps = dict(firestore_store.capabilities)
    before_audit = dict(firestore_store.audit_events)
    before_approvals = dict(firestore_store.approvals)
    before_evolution = dict(firestore_store.evolution_events)

    response = client.get("/beastmode/mission/readiness")
    assert response.status_code == 200

    assert firestore_store.capabilities == before_caps
    assert firestore_store.audit_events == before_audit
    assert firestore_store.approvals == before_approvals
    assert firestore_store.evolution_events == before_evolution


def test_no_owner_token_configured_yields_not_ready(monkeypatch):
    monkeypatch.delenv("AXON_OWNER_TOKEN", raising=False)
    body = client.get("/beastmode/mission/readiness").json()
    assert body["overall"] == "NOT_READY"
    check = next(c for c in body["checks"] if c["name"] == "owner_auth_configured")
    assert check["ready"] is False
