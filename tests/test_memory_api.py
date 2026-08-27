"""POST /beastmode/memory/query and GET /beastmode/memory/{capability} —
real end-to-end, through the actual FastAPI app and the actual
firestore_store, not a fixture over app/beastmode/memory.py's functions.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import app
from app.memory.firestore_store import firestore_store
from app.synapse.engine import synapse
from app.synapse.generator import Candidate

client = TestClient(app)

_CANDIDATE = Candidate(
    name="convert_currency_amount",
    description="Converts a monetary amount using an exchange rate",
    code='def convert_currency_amount(x): return {"ok": True}',
    test='assert convert_currency_amount(1)["ok"]',
    entrypoint="convert_currency_amount", risk="LOW",
)
_SANDBOX = {"status": "COMPLETED", "exit_code": 0, "passed": True, "stdout": "OK\n", "stderr": ""}


def setup_function():
    firestore_store.capabilities.clear()
    firestore_store.install_claims.clear()
    firestore_store.audit_events.clear()


def test_query_with_no_history_recommends_acquire_new():
    response = client.post("/beastmode/memory/query", json={"need": "something never attempted before"})
    assert response.status_code == 200
    body = response.json()
    assert body["recommendation"] == "ACQUIRE_NEW"
    assert body["matches"] == []
    assert "authorization" not in body["security_note"] or "does not skip" in body["security_note"]


def test_query_after_a_real_rejection_surfaces_it():
    """Propose a candidate that fails its own sandbox test through the
    REAL pipeline, then check that memory/query surfaces the real
    rejection it wrote to audit_events -- not a fabricated one."""
    with patch("app.synapse.engine.generate_candidate", return_value=(_CANDIDATE, None)), \
         patch("app.synapse.engine.execute_in_sandbox", return_value={
             "status": "COMPLETED", "exit_code": 1, "passed": False,
             "stdout": "", "stderr": "AssertionError: bad rate",
         }):
        synapse.propose("convert currency amount using exchange rate")

    response = client.post(
        "/beastmode/memory/query",
        json={"need": "convert currency amount using exchange rate"},
    )
    body = response.json()

    assert body["recommendation"] in ("DO_NOT_REUSE", "ACQUIRE_NEW")
    assert len(body["matches"]) == 1
    assert body["matches"][0]["name"] == "convert_currency_amount"
    assert any(h["status"] == "REJECTED" for h in body["history"])


def test_history_endpoint_reflects_real_audit_events():
    with patch("app.synapse.engine.generate_candidate", return_value=(_CANDIDATE, None)), \
         patch("app.synapse.engine.execute_in_sandbox", return_value=_SANDBOX), \
         patch("app.synapse.engine.evaluate", return_value={
             "status": "SCORED", "model": "gemma-4-26b-a4b-it",
             "score": 90, "verdict": "PASS", "reason": "fine",
         }):
        synapse.propose("convert currency amount")

    response = client.get("/beastmode/memory/convert_currency_amount")
    body = response.json()

    assert body["capability"] == "convert_currency_amount"
    assert body["known"] is True
    assert body["attempts"] >= 1
    assert body["history"][-1]["status"] == "AWAITING_APPROVAL"


def test_history_for_unknown_capability_is_honest_not_a_crash():
    response = client.get("/beastmode/memory/never_seen_this_before")
    assert response.status_code == 200
    body = response.json()
    assert body["known"] is False


def test_memory_query_has_zero_side_effects_even_for_a_strong_reuse_match():
    """The security invariant from app/beastmode/memory.py's docstring,
    proven structurally rather than by reading a note string: calling
    /beastmode/memory/query for a need that WOULD recommend reuse must
    not create, approve, or install anything. No new capabilities doc,
    no new audit event, no new approval -- state before and after must
    be byte-identical."""
    with patch("app.synapse.engine.generate_candidate", return_value=(_CANDIDATE, None)), \
         patch("app.synapse.engine.execute_in_sandbox", return_value=_SANDBOX), \
         patch("app.synapse.engine.evaluate", return_value={
             "status": "SCORED", "model": "gemma-4-26b-a4b-it",
             "score": 90, "verdict": "PASS", "reason": "fine",
         }):
        record = synapse.propose("convert currency amount")
        client.post(f"/synapse/install/{record.candidate['name']}",
                     headers={"X-Axon-Token": "does-not-matter-for-this-check"})
        # Approve for real so the capability is genuinely REUSE-eligible.
        firestore_store.update_approval(record.approval_request_id, approved=True, decided_by="test")

    before_caps = dict(firestore_store.capabilities)
    before_audit = dict(firestore_store.audit_events)
    before_approvals = dict(firestore_store.approvals)

    response = client.post("/beastmode/memory/query", json={"need": "convert currency amount"})
    assert response.status_code == 200

    assert firestore_store.capabilities == before_caps
    assert firestore_store.audit_events == before_audit
    assert firestore_store.approvals == before_approvals
