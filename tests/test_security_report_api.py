"""GET /beastmode/security/report -- real end-to-end, through the actual
FastAPI app, and a structural proof it has zero side effects."""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

from fastapi.testclient import TestClient

from app.api import app
from app.beastmode.security_report import BYPASSES_FOUND_AND_FIXED
from app.memory.firestore_store import firestore_store

client = TestClient(app)  # no owner token -- this must be a public read


def test_report_is_reachable_without_an_owner_token():
    response = client.get("/beastmode/security/report")
    assert response.status_code == 200


def test_report_contains_a_live_red_team_result():
    body = client.get("/beastmode/security/report").json()
    assert body["red_team"]["total"] > 0
    assert 0 <= body["red_team"]["contained"] <= body["red_team"]["total"]


def test_report_lists_every_real_bypass_with_a_real_commit():
    body = client.get("/beastmode/security/report").json()
    items = body["bypasses_found_and_fixed"]["items"]
    assert body["bypasses_found_and_fixed"]["count"] == len(BYPASSES_FOUND_AND_FIXED)
    assert len(items) == 4
    for item in items:
        assert item["fixed_in_commit"]  # never an empty/fake reference
        assert item["before"] and item["after"]


def test_report_never_claims_100_percent_secure():
    body = client.get("/beastmode/security/report").json()
    import json
    text = json.dumps(body).lower()
    assert "100% secure" not in text
    assert "fully secure" not in text
    assert "impossible to bypass" not in text


def test_report_status_values_are_only_the_defined_set():
    body = client.get("/beastmode/security/report").json()
    allowed = {"BLOCKED", "TESTED", "PARTIAL", "UNVERIFIED", "KNOWN_LIMITATION", "NOT_APPLICABLE"}
    for category in body["categories"]:
        assert category["status"] in allowed, category


def test_report_includes_known_limitations_not_hidden():
    body = client.get("/beastmode/security/report").json()
    assert len(body["known_limitations"]) >= 4
    joined = " ".join(body["known_limitations"]).lower()
    assert "network egress" in joined or "network" in joined


def test_report_has_zero_side_effects():
    """Same structural proof pattern as memory/plan: snapshot every real
    collection, call the endpoint, assert byte-identical state after."""
    before_caps = dict(firestore_store.capabilities)
    before_audit = dict(firestore_store.audit_events)
    before_approvals = dict(firestore_store.approvals)
    before_evolution = dict(firestore_store.evolution_events)

    response = client.get("/beastmode/security/report")
    assert response.status_code == 200

    assert firestore_store.capabilities == before_caps
    assert firestore_store.audit_events == before_audit
    assert firestore_store.approvals == before_approvals
    assert firestore_store.evolution_events == before_evolution
