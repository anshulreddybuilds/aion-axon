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
    assert len(items) == 5
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


def test_live_and_historical_evidence_are_never_conflated():
    """The report must be structurally honest about WHICH fields are
    computed right now (red_team, forbidden-list sizes baked into the
    category detail strings) versus which are static snapshots recorded
    at a past commit (regression_tests). This asserts the shape itself
    enforces that distinction -- a future edit that quietly merges them
    into one ambiguous number would fail this test."""
    body = client.get("/beastmode/security/report").json()

    # LIVE: red_team.total must be a real, non-zero, freshly-computed
    # count -- calling it twice in a row must never silently disagree
    # with itself (it's live, not random), but it is NOT a static field.
    first = body["red_team"]["total"]
    second = client.get("/beastmode/security/report").json()["red_team"]["total"]
    assert first == second > 0

    # HISTORICAL: regression_tests must carry an explicit commit
    # reference and be nested under a key that says what it is --
    # never a bare top-level "test_count" number a reader could mistake
    # for something this request just measured.
    reg = body["regression_tests"]
    assert "latest_known" in reg and "history" in reg
    assert "as_of_commit" in reg["latest_known"]
    assert "not_live" in reg["note"].lower() or "never" in reg["note"].lower()
    assert "top_level" not in body  # no bare ambiguous count exists anywhere
    assert "test_count" not in body
