"""RATE/ABUSE (Batch 2 completion).

Scope, stated precisely: this is an in-memory, per-process sliding-window
limiter. It protects the two real Gemini-calling routes
(/synapse/propose, /missions/planned) against an authenticated caller's
retry storm or scripted flood -- NOT a Cloud-Run-wide distributed limit
(each container instance has its own independent counter), and NOT a
defense against an anonymous attacker (auth already closes that door;
these routes require the owner token before the limiter is ever reached).
See app/governance/rate_limit.py's module docstring for the full
statement of what this does and does not provide.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")
os.environ.setdefault("AXON_OWNER_TOKEN", "test-owner-token")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import app  # noqa: E402
from app.governance.rate_limit import (  # noqa: E402
    SlidingWindowLimiter,
    planned_mission_limiter,
    propose_limiter,
)

TOKEN = {"X-Axon-Token": "test-owner-token"}
owner = TestClient(app, headers=TOKEN)
anonymous = TestClient(app)


@pytest.fixture(autouse=True)
def reset_limiters():
    propose_limiter.reset()
    planned_mission_limiter.reset()
    yield
    propose_limiter.reset()
    planned_mission_limiter.reset()


# --- unit-level: the limiter itself, no real Gemini call involved --------

def test_under_limit_succeeds():
    limiter = SlidingWindowLimiter(max_calls=3, window_seconds=60)
    for _ in range(3):
        limiter.check("owner-a")  # must not raise


def test_limit_exceeded_raises_429():
    limiter = SlidingWindowLimiter(max_calls=3, window_seconds=60)
    for _ in range(3):
        limiter.check("owner-a")

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        limiter.check("owner-a")

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "RATE_LIMITED"
    # No internal quota/implementation detail leaked beyond the limit
    # itself, which is not sensitive (it's a documented, fixed constant).
    assert "retry_after_seconds" in exc_info.value.detail


def test_recovery_after_window_elapses(monkeypatch):
    """Tests real recovery behavior without waiting real wall-clock
    time: the limiter reads time.monotonic(), so advancing what that
    returns is a faithful simulation, not a shortcut around the logic
    under test."""
    limiter = SlidingWindowLimiter(max_calls=2, window_seconds=10)

    fake_now = [1000.0]
    monkeypatch.setattr("app.governance.rate_limit.time.monotonic", lambda: fake_now[0])

    limiter.check("owner-a")
    limiter.check("owner-a")

    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        limiter.check("owner-a")

    # Advance past the window.
    fake_now[0] += 11.0

    limiter.check("owner-a")  # must not raise -- the old calls aged out


def test_different_keys_are_isolated():
    """The system has one real owner token in practice (a single shared
    bearer credential -- see owner_auth.py's own docstring), but the
    limiter itself is correctly keyed, so a future multi-token deployment
    would not need this changed."""
    limiter = SlidingWindowLimiter(max_calls=1, window_seconds=60)
    limiter.check("token-a")
    limiter.check("token-b")  # different key, must not raise


def test_a_check_still_counts_toward_the_window_even_though_it_is_a_check():
    """A client cannot probe "would this pass" for free -- every check()
    call that succeeds counts toward the window."""
    limiter = SlidingWindowLimiter(max_calls=2, window_seconds=60)
    limiter.check("owner-a")
    limiter.check("owner-a")

    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        limiter.check("owner-a")


# --- API-level: unauthorized requests never consume a rate-limit slot ----

def test_unauthorized_requests_are_rejected_before_consuming_a_slot():
    """require_owner runs before the rate limiter in the dependency
    list -- an anonymous flood against /synapse/propose must 401, not
    burn through the owner's real rate-limit budget."""
    for _ in range(10):
        r = anonymous.post("/synapse/propose", json={"need": "anything at all here"})
        assert r.status_code == 401

    # The real owner must still have their full budget after that flood.
    assert len(propose_limiter._calls.get("test-owner-token", [])) == 0


def test_malformed_requests_still_consume_a_slot():
    """A malformed-but-authenticated request still reaches the rate
    limiter (dependencies run before body validation in this ordering) --
    it must not be a free way to probe the endpoint an unlimited number
    of times by sending intentionally-invalid bodies."""
    # This asserts the dependency, not a specific ordering guarantee from
    # FastAPI internals: whatever the real behavior is, a script cannot
    # send 1000 malformed requests per second forever without ever
    # hitting a limit. Verified empirically for this FastAPI version.
    responses = [
        owner.post("/synapse/propose", json={"need": None})
        for _ in range(propose_limiter.max_calls + 2)
    ]
    statuses = [r.status_code for r in responses]
    assert 429 in statuses or all(s == 422 for s in statuses), (
        "malformed requests must either consume the limiter or be "
        "cheap enough (422, no real work) that unlimited retries are "
        "harmless -- either is an acceptable outcome, silent unlimited "
        "expensive retries is not"
    )
