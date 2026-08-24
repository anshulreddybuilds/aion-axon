"""GET /beastmode/approval/{id}/explain — real end-to-end, not a fixture.

Creates a genuine pending approval through synapse.propose() (mocking only
the model calls, exactly like tests/test_evaluator_unscored_escalates.py),
then hits the actual endpoint through the real FastAPI app. If this ever
starts reading from a mock instead of the live approval/review pipeline,
these break.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import app
from app.synapse.engine import synapse
from app.synapse.generator import Candidate

client = TestClient(app)

_CANDIDATE = Candidate(
    name="fake_cap", description="test capability",
    code='def fake_cap(x): return {"ok": True}',
    test='assert fake_cap(1)["ok"]', entrypoint="fake_cap", risk="MEDIUM",
)
_SANDBOX = {"status": "COMPLETED", "exit_code": 0, "passed": True, "stdout": "OK\n", "stderr": ""}


def _propose_with(evaluation: dict):
    with patch("app.synapse.engine.generate_candidate", return_value=(_CANDIDATE, None)), \
         patch("app.synapse.engine.execute_in_sandbox", return_value=_SANDBOX), \
         patch("app.synapse.engine.evaluate", return_value=evaluation):
        return synapse.propose("a fake need")


def test_explain_returns_real_risk_and_contract_for_a_scored_candidate():
    record = _propose_with({
        "status": "SCORED", "model": "gemma-4-26b-a4b-it",
        "score": 92, "verdict": "PASS", "reason": "looks solid",
    })

    response = client.get(f"/beastmode/approval/{record.approval_request_id}/explain")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "OK"
    assert body["capability"] == "fake_cap"

    why = body["why_human"]
    assert why["evaluator_result"]["score"] == 92
    assert why["sandbox_result"]["passed"] is True
    assert why["risk_score"]["tier"] in ("LOW", "MODERATE", "HIGH", "CRITICAL", "PROHIBITED")
    # Never invented: the AST counts must match the real live catalog.
    from app.synapse.safety_screen import FORBIDDEN_CALLS, FORBIDDEN_IMPORTS
    static = why["declared_contract"]["static_screen"]
    assert static["imports_checked"] == len(FORBIDDEN_IMPORTS)
    assert static["calls_checked"] == len(FORBIDDEN_CALLS)


def test_explain_reflects_an_unscored_candidate_honestly():
    """The explainer must show 'no verdict', never invent a score."""
    record = _propose_with({
        "status": "UNSCORED", "model": "gemma-4-26b-a4b-it",
        "score": None, "verdict": None, "reason": "could not be parsed",
    })

    response = client.get(f"/beastmode/approval/{record.approval_request_id}/explain")
    body = response.json()

    assert body["why_human"]["evaluator_result"]["score"] is None
    assert body["why_human"]["evaluator_result"]["status"] == "UNSCORED"
    # A missing verdict must read as MORE risk than a clean pass, not less.
    assert body["why_human"]["risk_score"]["score"] > 0


def test_explain_on_unknown_request_id_returns_not_found_not_a_crash():
    response = client.get("/beastmode/approval/does-not-exist/explain")
    assert response.status_code == 200
    assert response.json()["status"] == "NOT_FOUND"
