"""POST /beastmode/plan -- real end-to-end, through the actual FastAPI
app and the actual firestore_store."""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")
os.environ.setdefault("AXON_OWNER_TOKEN", "test-owner-token")

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import app
from app.memory.firestore_store import firestore_store
from app.synapse.engine import synapse
from app.synapse.generator import Candidate

client = TestClient(app, headers={"X-Axon-Token": "test-owner-token"})

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
    firestore_store.approvals.clear()


def test_plan_with_no_history_recommends_a_fresh_single_attempt():
    response = client.post("/beastmode/plan", json={"need": "something never attempted before"})
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "ACQUIRE_NEW"
    assert body["strategy"] == "GENERATE_SINGLE_ATTEMPT"
    assert "advisory" in body["authorization_note"].lower()


def test_plan_after_a_real_install_recommends_reuse():
    with patch("app.synapse.engine.generate_candidate", return_value=(_CANDIDATE, None)), \
         patch("app.synapse.engine.execute_in_sandbox", return_value=_SANDBOX), \
         patch("app.synapse.engine.evaluate", return_value={
             "status": "SCORED", "model": "gemma-4-26b-a4b-it",
             "score": 90, "verdict": "PASS", "reason": "fine",
         }):
        record = synapse.propose("convert currency amount")

    firestore_store.update_approval(record.approval_request_id, approved=True, decided_by="test")
    client.post(f"/synapse/install/{_CANDIDATE.name}")

    response = client.post("/beastmode/plan", json={"need": "convert currency amount"})
    body = response.json()

    assert body["decision"] == "REUSE_EXISTING_CAPABILITY"
    assert body["capability"] == "convert_currency_amount"
    assert "CURRENT_CONTRACT_CHECK" in body["required_checks"]


def test_plan_endpoint_has_zero_side_effects():
    """Same structural proof as the memory endpoint's equivalent test:
    calling /beastmode/plan for a need that recommends reuse must not
    create, approve, or install anything."""
    with patch("app.synapse.engine.generate_candidate", return_value=(_CANDIDATE, None)), \
         patch("app.synapse.engine.execute_in_sandbox", return_value=_SANDBOX), \
         patch("app.synapse.engine.evaluate", return_value={
             "status": "SCORED", "model": "gemma-4-26b-a4b-it",
             "score": 90, "verdict": "PASS", "reason": "fine",
         }):
        record = synapse.propose("convert currency amount")
    firestore_store.update_approval(record.approval_request_id, approved=True, decided_by="test")
    client.post(f"/synapse/install/{_CANDIDATE.name}")

    before_caps = dict(firestore_store.capabilities)
    before_audit = dict(firestore_store.audit_events)
    before_approvals = dict(firestore_store.approvals)

    response = client.post("/beastmode/plan", json={"need": "convert currency amount"})
    assert response.status_code == 200

    assert firestore_store.capabilities == before_caps
    assert firestore_store.audit_events == before_audit
    assert firestore_store.approvals == before_approvals
