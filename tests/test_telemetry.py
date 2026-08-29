"""Telemetry — Stage 14.

The rule under test is that a MISSING measurement never becomes a
plausible number. An estimated token count reads exactly like a measured
one and would corrupt every cost figure downstream, so the aggregate has
to keep them apart.
"""
import os
from types import SimpleNamespace

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")
os.environ.setdefault("AXON_OWNER_TOKEN", "test-owner-token")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.capabilities.bootstrap  # noqa: E402,F401
from app.api import app  # noqa: E402
from app.governance.execution_gate import execution_gate  # noqa: E402
from app.governance.guardian import RiskLevel  # noqa: E402
from app.memory.firestore_store import firestore_store  # noqa: E402
from app.observability.telemetry import (  # noqa: E402
    summarise,
    timed,
    usage_of,
)

client = TestClient(app, headers={"X-Axon-Token": "test-owner-token"})


@pytest.fixture(autouse=True)
def clean():
    firestore_store.audit_events.clear()
    yield
    firestore_store.audit_events.clear()


# --- Measurement, not estimation -----------------------------------------

def test_usage_is_read_from_the_model_response():
    response = SimpleNamespace(usage_metadata=SimpleNamespace(
        prompt_token_count=120,
        candidates_token_count=45,
        total_token_count=165,
    ))

    usage = usage_of(response)

    assert usage["total_tokens"] == 165
    assert usage["measured"] is True


def test_missing_usage_is_none_not_zero():
    """None and 0 mean opposite things and must not be conflated."""
    usage = usage_of(SimpleNamespace())

    assert usage["total_tokens"] is None
    assert usage["measured"] is False


def test_unmeasured_calls_are_counted_separately():
    events = [
        {"event_type": "MODEL_CALL", "stage": "generate", "measured": True,
         "total_tokens": 100, "duration_ms": 500},
        {"event_type": "MODEL_CALL", "stage": "generate", "measured": False,
         "total_tokens": None, "duration_ms": 400},
    ]

    summary = summarise(events)

    assert summary["model_calls"]["count"] == 2
    assert summary["model_calls"]["measured"] == 1
    assert summary["model_calls"]["unmeasured"] == 1
    # The unmeasured call must not be silently treated as zero tokens.
    assert summary["model_calls"]["total_tokens"] == 100


def test_no_measurements_yields_none_not_a_confident_zero():
    summary = summarise([])

    assert summary["tool_executions"]["avg_ms"] is None
    assert summary["model_calls"]["total_tokens"] is None


# --- The gate is timed ----------------------------------------------------

def test_successful_execution_records_a_duration():
    result = execution_gate.execute(
        "add numbers", RiskLevel.LOW, lambda *a: {"status": "SUCCESS"},
    )

    assert result["status"] == "EXECUTED"
    assert result["duration_ms"] >= 0

    executed = [
        e for e in firestore_store.audit_events.values()
        if e["event_type"] == "ACTION_EXECUTED"
    ]

    assert executed and executed[0]["duration_ms"] is not None


def test_a_failing_tool_is_still_timed():
    """A slow failure is a cost too, and the one you most want to see."""
    def explodes(*args):
        raise RuntimeError("boom")

    result = execution_gate.execute("boom", RiskLevel.LOW, explodes)

    assert result["status"] == "FAILED"
    assert result["duration_ms"] >= 0

    failed = [
        e for e in firestore_store.audit_events.values()
        if e["event_type"] == "ACTION_FAILED"
    ]

    assert failed and failed[0]["duration_ms"] is not None


def test_timing_never_breaks_the_work():
    """An agent that crashes because its stopwatch broke is worse than one
    with no stopwatch."""
    with timed() as clock:
        pass

    assert clock["ms"] >= 0


# --- Aggregation ----------------------------------------------------------

def test_per_stage_breakdown():
    events = [
        {"event_type": "MODEL_CALL", "stage": "generate", "measured": True,
         "total_tokens": 300, "duration_ms": 900},
        {"event_type": "MODEL_CALL", "stage": "evaluate", "measured": True,
         "total_tokens": 80, "duration_ms": 300},
        {"event_type": "MODEL_CALL", "stage": "evaluate", "measured": True,
         "total_tokens": 20, "duration_ms": 100},
    ]

    by_stage = summarise(events)["by_stage"]

    assert by_stage["generate"]["tokens"] == 300
    assert by_stage["evaluate"]["calls"] == 2
    assert by_stage["evaluate"]["tokens"] == 100
    assert by_stage["evaluate"]["avg_ms"] == 200.0


def test_telemetry_endpoint_reports_real_executions():
    execution_gate.execute(
        "add numbers", RiskLevel.LOW, lambda *a: {"status": "SUCCESS"},
    )

    body = client.get("/telemetry").json()

    assert body["tool_executions"]["count"] >= 1
    assert body["tool_executions"]["avg_ms"] is not None
    assert "usage_metadata" in body["note"]
