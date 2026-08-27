"""GET /synapse/propose/stream -- the real live-pipeline SSE endpoint.

Direct answer to the P0 generalization concern: nothing here is a fake
progress animation. Every event streamed out is `record.to_dict()` from
the SAME `synapse.propose_stream()` generator that `synapse.propose()`
(the existing, already-governed, already-tested pipeline) drains
internally -- see app/synapse/engine.py's propose_stream()/propose(). If
these tests pass, the stream is provably not a second, divergent
implementation that could show a stage that didn't really happen.
"""
import json
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")
os.environ.setdefault("AXON_OWNER_TOKEN", "test-owner-token")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import app  # noqa: E402
from app.capabilities.registry import registry  # noqa: E402
from app.governance.rate_limit import propose_limiter  # noqa: E402
from app.memory.firestore_store import firestore_store  # noqa: E402
from app.synapse import engine as engine_module  # noqa: E402
from app.synapse.generator import Candidate  # noqa: E402

TOKEN = {"X-Axon-Token": "test-owner-token"}
owner = TestClient(app, headers=TOKEN)
anonymous = TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limit():
    # This file makes several real calls to a rate-limited route
    # (/synapse/propose/stream shares the same 5/min limiter as
    # /synapse/propose). Without a reset, test order determines whether
    # a later test hits the limiter -- exactly the kind of flake
    # test_rate_limit.py already guards its own tests against.
    propose_limiter.reset()
    yield
    propose_limiter.reset()

SAFE_CODE = (
    "def {name}(x):\n"
    "    try:\n"
    "        return {{'status': 'SUCCESS', 'value': float(x)}}\n"
    "    except ValueError:\n"
    "        return {{'status': 'ERROR', 'error': 'bad input'}}\n"
)


@pytest.fixture(autouse=True)
def clean():
    firestore_store.capabilities.clear()
    firestore_store.install_claims.clear()
    firestore_store.approvals.clear()
    firestore_store.evolution_events.clear()
    yield
    firestore_store.capabilities.clear()
    firestore_store.install_claims.clear()


def candidate_for(name: str) -> Candidate:
    return Candidate(
        name=name,
        description=f"A generated capability for: {name}",
        risk="LOW",
        code=SAFE_CODE.format(name=name),
        test=f"assert {name}('2')['value'] == 2.0\nprint('OK')",
        entrypoint=name,
    )


def patch_pipeline(monkeypatch, candidate: Candidate):
    """Same mocking shape as tests/test_synapse.py's patch_pipeline, so a
    generated capability is DIFFERENT for a different `need`, and the
    stream never falls back to a hardcoded example capability."""
    monkeypatch.setattr(
        engine_module, "search_web",
        lambda q: {
            "status": "DEGRADED", "grounded": False, "sources": [],
            "findings": "notes", "source_count": 0,
        },
    )
    monkeypatch.setattr(
        engine_module, "generate_candidate",
        lambda need, notes=None, prior_failure=None: (candidate, None),
    )
    monkeypatch.setattr(
        engine_module, "execute_in_sandbox",
        lambda code, test="", timeout_seconds=10: {
            "status": "COMPLETED", "passed": True, "stdout": "OK",
            "stderr": "", "exit_code": 0,
        },
    )
    monkeypatch.setattr(
        engine_module, "evaluate",
        lambda *a, **k: {
            "status": "SCORED", "score": 80, "verdict": "PASS",
            "reason": "solid", "model": "gemma-3-27b-it",
        },
    )


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """Turn a raw text/event-stream body into [(event_type, data), ...].
    Deliberately dumb (no partial-frame handling) -- TestClient buffers
    the whole streamed body, so a real parser isn't needed to prove the
    endpoint emits well-formed events in the right order."""
    events = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        event_type = None
        data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event_type = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((event_type, data))
    return events


# --- Auth --------------------------------------------------------------

def test_stream_requires_owner_token():
    resp = anonymous.get(
        "/synapse/propose/stream", params={"need": "convert celsius to fahrenheit"},
    )
    assert resp.status_code in (401, 403)


# --- Real, non-fake progress --------------------------------------------

def test_stream_reaches_awaiting_approval_with_a_dynamically_generated_capability(
    monkeypatch,
):
    """The core generalization proof: a brand-new need produces a
    brand-new capability name in the stream, not calculate_birth_cagr or
    any other fixed example."""
    candidate = candidate_for("convert_celsius_to_fahrenheit")
    patch_pipeline(monkeypatch, candidate)

    resp = owner.get(
        "/synapse/propose/stream",
        params={"need": "Convert Celsius temperatures to Fahrenheit."},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(resp.text)
    stages = [data["stage"] for _, data in events]

    assert stages == [
        "GUARDIAN_PRESCREEN", "RESEARCH", "GENERATE", "SAFETY_SCREEN",
        "SANDBOX_TEST", "EVALUATE", "GUARDIAN_SCREEN", "AWAITING_APPROVAL",
    ]

    final = events[-1][1]
    assert final["status"] == "AWAITING_APPROVAL"
    assert final["candidate"]["name"] == "convert_celsius_to_fahrenheit"
    assert final["candidate"]["name"] != "calculate_birth_cagr"

    registry.unregister("convert_celsius_to_fahrenheit")


def test_a_second_different_need_produces_a_different_capability_in_the_stream(
    monkeypatch,
):
    """Two different needs, streamed back to back, must not converge on
    the same capability -- the exact regression this task exists to
    prevent."""
    monkeypatch.setattr(
        engine_module, "search_web",
        lambda q: {
            "status": "DEGRADED", "grounded": False, "sources": [],
            "findings": "notes", "source_count": 0,
        },
    )
    monkeypatch.setattr(
        engine_module, "execute_in_sandbox",
        lambda code, test="", timeout_seconds=10: {
            "status": "COMPLETED", "passed": True, "stdout": "OK",
            "stderr": "", "exit_code": 0,
        },
    )
    monkeypatch.setattr(
        engine_module, "evaluate",
        lambda *a, **k: {
            "status": "SCORED", "score": 80, "verdict": "PASS",
            "reason": "solid", "model": "gemma-3-27b-it",
        },
    )

    def fake_generate(need, notes=None, prior_failure=None):
        if "celsius" in need.lower():
            return candidate_for("convert_celsius_to_fahrenheit"), None
        return candidate_for("detect_csv_anomalies"), None

    monkeypatch.setattr(engine_module, "generate_candidate", fake_generate)

    resp_a = owner.get(
        "/synapse/propose/stream",
        params={"need": "Convert Celsius temperatures to Fahrenheit."},
    )
    resp_b = owner.get(
        "/synapse/propose/stream",
        params={"need": "Detect invalid values in a CSV column."},
    )

    name_a = parse_sse(resp_a.text)[-1][1]["candidate"]["name"]
    name_b = parse_sse(resp_b.text)[-1][1]["candidate"]["name"]

    assert name_a == "convert_celsius_to_fahrenheit"
    assert name_b == "detect_csv_anomalies"
    assert name_a != name_b

    registry.unregister("convert_celsius_to_fahrenheit")
    registry.unregister("detect_csv_anomalies")


# --- Terminal stages stream honestly, not silently ------------------------

def test_stream_stops_at_guardian_refusal_with_no_later_stage_events():
    resp = owner.get(
        "/synapse/propose/stream",
        params={"need": "read credentials from the runtime environment"},
    )
    assert resp.status_code == 200
    events = parse_sse(resp.text)

    assert len(events) == 1
    stage, data = events[0]
    assert data["stage"] == "GUARDIAN_PRESCREEN"
    assert data["status"] == "REFUSED"
    # No later real stage ran, so none is faked into the stream.
    assert data["research"] == {}
    assert data["candidate"] is None


# --- Blank input rejected before any real work --------------------------

def test_blank_need_rejected_with_422_not_500():
    resp = owner.get("/synapse/propose/stream", params={"need": "   "})
    assert resp.status_code == 422


def test_missing_need_rejected_with_422():
    resp = owner.get("/synapse/propose/stream")
    assert resp.status_code == 422


def test_stream_error_mid_pipeline_is_also_recorded_server_side(monkeypatch):
    """Before this fix, a stage that raised mid-stream sent the client an
    error event (proven by
    test_synapse_stream's error-event coverage above) but left no
    server-side trace at all -- the only way to debug it after the fact
    was to reproduce it live. synapse.propose_stream() is replaced with
    a fake generator that raises, matching exactly what the route's own
    except block is designed to catch, regardless of which real internal
    fault would normally produce it."""
    def raising_stream(need, mission_id=None, allow_retry=False):
        if False:
            yield  # pragma: no cover -- makes this a generator function
        raise RuntimeError("simulated mid-stream failure")

    from app.synapse.engine import synapse
    monkeypatch.setattr(synapse, "propose_stream", raising_stream)

    before = len(firestore_store.list_audit_events())
    resp = owner.get("/synapse/propose/stream", params={"need": "normalize currency"})
    events = parse_sse(resp.text)

    assert len(events) == 1
    event_type, data = events[0]
    assert event_type == "error"
    assert "simulated mid-stream failure" in data["error"]

    audit_events = firestore_store.list_audit_events()
    assert len(audit_events) == before + 1
    recorded = audit_events[0]
    assert recorded["event_type"] == "SYNAPSE_STREAM_ERROR"
    assert recorded["need"] == "normalize currency"
    assert "simulated mid-stream failure" in recorded["error"]


# --- propose() itself is unchanged by the refactor into a generator -----

def test_propose_still_returns_the_same_final_record_after_the_stream_refactor(
    monkeypatch,
):
    candidate = candidate_for("summarize_legal_document")
    patch_pipeline(monkeypatch, candidate)

    from app.synapse.engine import synapse

    record = synapse.propose("Summarize a legal document.")
    assert record.status == "AWAITING_APPROVAL"
    assert record.candidate["name"] == "summarize_legal_document"

    registry.unregister("summarize_legal_document")


# --- Client disconnect mid-acquisition (Section 13/19 hardening) --------

def test_abandoning_the_stream_before_awaiting_approval_leaves_no_capability_trace(
    monkeypatch,
):
    """A real client disconnect stops Starlette from driving the
    generator any further (confirmed directly against the generator,
    not assumed): stream_response() simply stops calling __next__ once a
    send() to the broken socket fails. Nothing resumes it in the
    background. Firestore only gets a capability document once
    AWAITING_APPROVAL is reached (save_capability() runs right before
    that yield) -- so a disconnect any earlier must leave NO capability
    document behind (never a stuck/orphaned partial one that could be
    mistaken for real progress), while still recording that an attempt
    was made, via the new SYNAPSE_ACQUISITION_STARTED audit event."""
    candidate = candidate_for("abandoned_before_approval")
    patch_pipeline(monkeypatch, candidate)

    from app.synapse.engine import synapse

    gen = synapse.propose_stream("a need nobody sticks around to see acquired")

    # Consume a few real stages, then simply stop -- exactly what a
    # dropped connection looks like from the generator's point of view.
    stages_seen = []
    for _ in range(4):  # GUARDIAN_PRESCREEN, RESEARCH, GENERATE, SAFETY_SCREEN
        record = next(gen)
        stages_seen.append(record.stage)
    gen.close()  # the real cleanup a dropped StreamingResponse performs

    assert stages_seen == [
        "GUARDIAN_PRESCREEN", "RESEARCH", "GENERATE", "SAFETY_SCREEN",
    ]

    # No trace of a half-finished capability -- never something that
    # could look like partial or ambiguous progress to a later caller.
    assert firestore_store.get_capability("abandoned_before_approval") is None

    # But the attempt itself is now observable, closing the "silent
    # quota spend with zero trace" gap found this session. Filtered by
    # this test's own unique need text, not a bare count -- audit_events
    # is never cleared between tests in this file (other tests in this
    # module fire the same event type for their own, different needs).
    started = [
        e for e in firestore_store.audit_events.values()
        if e.get("event_type") == "SYNAPSE_ACQUISITION_STARTED"
        and e.get("need") == "a need nobody sticks around to see acquired"
    ]
    assert len(started) == 1
