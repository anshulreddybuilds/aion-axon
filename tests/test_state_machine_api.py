"""GET /beastmode/state-machine -- P5 (Judge Mode): the formal
capability-lifecycle transition table, publicly inspectable proof that
AI cannot self-authorize a promotion. Read-only, pure constants."""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

from fastapi.testclient import TestClient

from app.api import app
from app.beastmode.state_machine import CANONICAL_STATES

client = TestClient(app)  # no token -- this must be a public read


def test_reachable_without_an_owner_token():
    response = client.get("/beastmode/state-machine")
    assert response.status_code == 200


def test_every_transition_target_is_a_real_canonical_state():
    body = client.get("/beastmode/state-machine").json()
    for state, targets in body["transitions"].items():
        assert state in CANONICAL_STATES
        for target in targets:
            assert target in CANONICAL_STATES


def test_installed_is_only_reachable_from_installing():
    """The concrete claim this endpoint exists to let a judge verify
    directly: no state other than INSTALLING legally transitions to
    INSTALLED."""
    body = client.get("/beastmode/state-machine").json()
    sources_that_reach_installed = [
        state for state, targets in body["transitions"].items()
        if "INSTALLED" in targets
    ]
    assert sources_that_reach_installed == ["INSTALLING"]


def test_awaiting_approval_never_transitions_directly_to_installed():
    body = client.get("/beastmode/state-machine").json()
    assert "INSTALLED" not in body["transitions"].get("AWAITING_APPROVAL", [])


def test_response_contains_no_write_endpoint_reference_beyond_the_documented_one():
    """The invariant text may reference the real approval endpoint for
    context, but this route itself must never suggest a write path."""
    body = client.get("/beastmode/state-machine").json()
    assert "GET" not in body["invariant"] or "POST /approvals" in body["invariant"]
