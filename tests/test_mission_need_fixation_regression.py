"""Regression tests for the calculate_birth_cagr fixation bug.

ROOT CAUSE (found 2026-08-26):
  AppV4.jsx send() was a pure UI toggle:
    const send = () => { setExpanded(true); setRevealed(0); }
  It made NO API call, so the user's typed prompt was silently discarded.
  The canvas loaded whatever `selected` was initialised to, which was
  hardcoded to "calculate_birth_cagr", regardless of what the user typed.

These backend tests verify the backend side of the contract:
1. POST /synapse/propose forwards the body 'need' field to the engine.
2. GET /synapse/propose/stream forwards the 'need' query param.
3. Different needs reach the engine as different strings.
4. Neither CSV nor Celsius mission produces calculate_birth_cagr.
5. AcquisitionRecord preserves the need it was constructed with.
"""
import json
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")
os.environ.setdefault("AXON_OWNER_TOKEN", "test-owner-token")

import pytest
from fastapi.testclient import TestClient
from app.api import app
from app.governance.rate_limit import propose_limiter

TOKEN = {"X-Axon-Token": "test-owner-token"}
owner = TestClient(app, headers=TOKEN)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the sliding-window limiter before every test so tests don't bleed."""
    propose_limiter.reset()
    yield
    propose_limiter.reset()


# ---------------------------------------------------------------------------
# Helper: a spy that returns a minimal BLOCKED record
# ---------------------------------------------------------------------------

def _spy_propose(captured: list):
    """Return a propose() spy that appends the received need and returns a BLOCKED record."""
    def spy(need, mission_id=None, allow_retry=False):
        captured.append(need)
        from app.synapse.engine import AcquisitionRecord
        r = AcquisitionRecord(need=need)
        r.stage = "GUARDIAN_PRESCREEN"
        r.status = "BLOCKED"
        r.reason = "Test interception — no real Gemini call"
        return r
    return spy


# ---------------------------------------------------------------------------
# Test 1: POST /synapse/propose passes the EXACT need to propose()
# ---------------------------------------------------------------------------

def test_csv_need_reaches_engine(monkeypatch):
    """MISSION A: CSV range check need must reach the engine unchanged."""
    captured = []
    import app.api as api_mod
    monkeypatch.setattr(api_mod.synapse, "propose", _spy_propose(captured))

    csv_need = "Detect when a CSV column contains values outside a configurable range."
    resp = owner.post("/synapse/propose", json={"need": csv_need})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert len(captured) == 1, f"propose() called {len(captured)} times, expected 1"
    assert captured[0] == csv_need, (
        f"Engine received wrong need: {captured[0]!r}\n"
        f"Expected: {csv_need!r}"
    )


def test_celsius_need_reaches_engine(monkeypatch):
    """MISSION B: Celsius/Fahrenheit need must reach the engine unchanged."""
    captured = []
    import app.api as api_mod
    monkeypatch.setattr(api_mod.synapse, "propose", _spy_propose(captured))

    celsius_need = "Convert Celsius temperatures to Fahrenheit."
    resp = owner.post("/synapse/propose", json={"need": celsius_need})
    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0] == celsius_need


def test_two_different_needs_reach_engine_as_different_strings(monkeypatch):
    """Two sequential missions must produce two distinct need strings at the engine."""
    captured = []
    import app.api as api_mod
    monkeypatch.setattr(api_mod.synapse, "propose", _spy_propose(captured))

    need_a = "Detect when a CSV column contains values outside a configurable range."
    need_b = "Convert Celsius temperatures to Fahrenheit."

    owner.post("/synapse/propose", json={"need": need_a})
    owner.post("/synapse/propose", json={"need": need_b})

    assert len(captured) == 2
    assert captured[0] == need_a
    assert captured[1] == need_b
    assert captured[0] != captured[1], (
        "Two different requests must arrive at the engine as two different need strings"
    )


def test_engine_does_not_return_calculate_birth_cagr(monkeypatch):
    """The engine's returned record must carry the actual need, not calculate_birth_cagr."""
    from app.synapse.engine import AcquisitionRecord

    def spy(need, mission_id=None, allow_retry=False):
        r = AcquisitionRecord(need=need)
        r.stage = "AWAITING_APPROVAL"
        r.status = "AWAITING_APPROVAL"
        # Derive a capability name from the actual need string
        if "CSV" in need or "range" in need.lower():
            r.candidate_name = "detect_csv_range_outliers"
        elif "Celsius" in need or "Fahrenheit" in need:
            r.candidate_name = "convert_celsius_to_fahrenheit"
        else:
            r.candidate_name = "unknown_capability"
        # Store on record without setting candidate (avoids pydantic serialisation issue)
        return r

    import app.api as api_mod
    monkeypatch.setattr(api_mod.synapse, "propose", spy)

    for need in [
        "Detect when a CSV column contains values outside a configurable range.",
        "Convert Celsius temperatures to Fahrenheit.",
    ]:
        resp = owner.post("/synapse/propose", json={"need": need})
        assert resp.status_code == 200
        body = resp.json()
        # The returned record carries the actual need
        assert body.get("need") == need, (
            f"Response 'need' field mismatch. Got: {body.get('need')!r}"
        )
        assert body.get("need") != "calculate_birth_cagr", (
            f"Bug regressed: mission '{need}' returned need='calculate_birth_cagr'"
        )


# ---------------------------------------------------------------------------
# Test 2: AcquisitionRecord preserves the need at construction
# ---------------------------------------------------------------------------

def test_acquisition_record_preserves_need():
    """AcquisitionRecord must store the exact need passed at construction."""
    from app.synapse.engine import AcquisitionRecord

    for need in [
        "Detect when a CSV column contains values outside a configurable range.",
        "Convert Celsius temperatures to Fahrenheit.",
        "Validate an email address.",
    ]:
        r = AcquisitionRecord(need=need)
        assert r.need == need, f"Expected {need!r}, got {r.need!r}"
        assert r.need != "calculate_birth_cagr", (
            "AcquisitionRecord.need returned 'calculate_birth_cagr' — fixation bug"
        )


def test_streaming_tracked_record_preserves_need():
    """_TrackedRecord (streaming wrapper) must preserve the need unchanged."""
    import queue
    from app.synapse.streaming import _TrackedRecord

    q = queue.Queue()
    need = "Detect when a CSV column contains values outside a configurable range."
    record = _TrackedRecord(event_queue=q, need=need)
    assert record.need == need
    assert record.need != "calculate_birth_cagr"


# ---------------------------------------------------------------------------
# Test 3: Blank need is rejected before reaching the engine
# ---------------------------------------------------------------------------

def test_blank_need_rejected_422():
    """A whitespace-only need must be rejected with 422, not reach the engine."""
    resp = owner.post("/synapse/propose", json={"need": "   "})
    assert resp.status_code == 422, (
        f"Blank need must be rejected with 422, got {resp.status_code}: {resp.text}"
    )


def test_empty_need_rejected_422():
    resp = owner.post("/synapse/propose", json={"need": ""})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test 4: SSE stream endpoint forwards the query param 'need' verbatim
# ---------------------------------------------------------------------------

def test_stream_endpoint_forwards_need_query_param(monkeypatch):
    """GET /synapse/propose/stream must forward the 'need' query param to stream_propose()."""
    captured = []

    def spy_stream(need, mission_id, allow_retry, owner_token):
        captured.append(need)
        yield f'data: {json.dumps({"type": "connected"})}\n\n'
        yield (
            f'data: {json.dumps({"type": "done", "record": {"need": need, "stage": "BLOCKED", "status": "BLOCKED", "candidate": None, "reason": "spy", "attempts": [], "approval_request_id": None}})}\n\n'
        )

    # Patch at the point of import in api.py, not in the streaming module itself
    import app.api as api_mod
    # The route imports stream_propose lazily inside the function, so we patch the module
    import app.synapse.streaming as streaming_mod
    monkeypatch.setattr(streaming_mod, "stream_propose", spy_stream)

    import urllib.parse
    csv_need = "Detect when a CSV column contains values outside a configurable range."
    resp = owner.get(f"/synapse/propose/stream?need={urllib.parse.quote(csv_need)}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert len(captured) == 1, f"stream_propose called {len(captured)} times, expected 1"
    assert captured[0] == csv_need, (
        f"SSE stream received wrong need.\nExpected: {csv_need!r}\nGot: {captured[0]!r}"
    )


def test_stream_does_not_use_hardcoded_birth_cagr(monkeypatch):
    """The SSE stream must use the query param need, not a hardcoded birth_cagr string."""
    captured = []

    def spy_stream(need, mission_id, allow_retry, owner_token):
        captured.append(need)
        yield f'data: {json.dumps({"type": "done", "record": {"need": need, "stage": "BLOCKED", "status": "BLOCKED", "candidate": None, "reason": "spy", "attempts": [], "approval_request_id": None}})}\n\n'

    import app.synapse.streaming as streaming_mod
    monkeypatch.setattr(streaming_mod, "stream_propose", spy_stream)

    import urllib.parse
    email_need = "Validate an email address format."
    owner.get(f"/synapse/propose/stream?need={urllib.parse.quote(email_need)}")

    assert len(captured) == 1, f"stream_propose called {len(captured)} times, expected 1"
    assert captured[0] == email_need
    assert captured[0] != "calculate_birth_cagr", (
        "SSE stream used hardcoded 'calculate_birth_cagr' instead of the query param"
    )
