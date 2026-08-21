"""Owner authentication on the routes that change something.

This is the test that would have caught the hole. It was found by curling
the deployed service, not by the suite -- every mutating endpoint was
publicly callable, so a stranger could approve a capability, record a
false fact to demote one, or flip the kill switch mid-demo.

An earlier note in this project claimed the CORS allowlist protected these
routes. It does not: CORS is a browser mechanism and does nothing against
curl. These tests send no Origin header at all, exactly as curl would.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")
os.environ.setdefault("AXON_OWNER_TOKEN", "test-owner-token")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import app  # noqa: E402
from app.governance import owner_auth  # noqa: E402

TOKEN = {"X-Axon-Token": "test-owner-token"}

# No Origin header anywhere: CORS is irrelevant to this threat.
anonymous = TestClient(app)
owner = TestClient(app, headers=TOKEN)

WRITES = [
    ("/killswitch", {"active": False}),
    ("/missions", {"request": "x", "tool": "calculator",
                   "action": "run", "risk": "LOW", "args": ["1+1"]}),
    ("/missions/planned", {"request": "x"}),
    ("/synapse/propose", {"need": "something"}),
    ("/synapse/install/anything", {}),
    ("/approvals/some-id/decide", {"approved": True}),
    ("/ground-truth", {"key": "k", "statement": "s", "value": "v",
                       "source": "https://example.com"}),
    ("/monitors", {"name": "m", "capability": "calculator",
                   "args": ["1+1"], "interval_minutes": 60}),
    ("/monitors/run-due", {}),
]


@pytest.mark.parametrize("path,body", WRITES)
def test_writes_are_refused_without_the_token(path, body):
    response = anonymous.post(path, json=body)

    assert response.status_code == 401, (
        f"{path} accepted an unauthenticated write"
    )


@pytest.mark.parametrize("path,body", WRITES)
def test_writes_are_refused_with_a_wrong_token(path, body):
    response = TestClient(app, headers={"X-Axon-Token": "wrong"}).post(
        path, json=body,
    )

    assert response.status_code == 401


def test_the_kill_switch_specifically_cannot_be_flipped_anonymously():
    """The demo-day nightmare: a stranger un-halts the agent mid-record."""
    assert anonymous.post(
        "/killswitch", json={"active": True},
    ).status_code == 401


def test_approvals_cannot_be_granted_anonymously():
    """Worse than the kill switch: silently approving a capability."""
    assert anonymous.post(
        "/approvals/anything/decide", json={"approved": True},
    ).status_code == 401


READS = [
    "/", "/health", "/capabilities", "/autonomy", "/evolution",
    "/telemetry", "/approvals/pending", "/monitors", "/ground-truth",
]


@pytest.mark.parametrize("path", READS)
def test_reads_stay_public(path):
    """Transparency is the point. Only CHANGING things is gated."""
    assert anonymous.get(path).status_code == 200


def test_the_owner_can_still_write():
    assert owner.post("/killswitch", json={"active": False}).status_code == 200


def test_an_unconfigured_deployment_fails_CLOSED(monkeypatch):
    """A control whose absence silently disables it is not a control.

    This hole existed precisely because "no auth" was the quiet default.
    """
    monkeypatch.delenv(owner_auth.TOKEN_ENV, raising=False)

    response = anonymous.post("/killswitch", json={"active": False})

    assert response.status_code == 503
    assert "no owner token configured" in response.json()["detail"]


def test_the_token_is_compared_in_constant_time():
    """Guards against recovering the token a character at a time."""
    import inspect

    source = inspect.getsource(owner_auth.require_owner)

    assert "compare_digest" in source
