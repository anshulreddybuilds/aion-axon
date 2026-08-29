"""Telemetry — what the work actually cost.

Audit Stage 14 was genuinely zero code: timestamps existed, so duration was
derivable, but nothing ever computed it. "It works" and "here is what it
cost" are different claims, and only the second survives the question
"would this be affordable at scale?".

Two rules this module holds to:

1. **Measure, never estimate.** A token count that came from the model's
   own `usage_metadata` is evidence. A token count inferred from string
   length is a guess wearing the same clothes, and would quietly corrupt
   every cost number downstream. When usage is unavailable, the record
   says so rather than filling in a plausible figure.

2. **Telemetry must never change behaviour.** Every function here is
   wrapped so a measurement failure cannot fail the thing being measured.
   An agent that crashes because its stopwatch broke is worse than an
   agent with no stopwatch.
"""
import time
from contextlib import contextmanager
from typing import Any, Optional

from app.memory.firestore_store import firestore_store


def usage_of(response: Any) -> dict[str, Optional[int]]:
    """Pull real token counts off a Gemini response.

    Returns None values when the model did not report usage. Callers must
    treat None as "unknown", never as zero -- a missing measurement and a
    measurement of zero mean opposite things.
    """
    usage = getattr(response, "usage_metadata", None)

    if usage is None:
        return {
            "prompt_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "measured": False,
        }

    return {
        "prompt_tokens": getattr(usage, "prompt_token_count", None),
        "output_tokens": getattr(usage, "candidates_token_count", None),
        "total_tokens": getattr(usage, "total_token_count", None),
        "measured": True,
    }


def record_model_call(
    stage: str,
    model: str,
    response: Any,
    duration_ms: float,
    ok: bool = True,
) -> None:
    """Write one model call's cost to the audit trail. Never raises."""
    try:
        firestore_store.write_audit_event("MODEL_CALL", {
            "stage": stage,
            "model": model,
            "duration_ms": round(duration_ms, 1),
            "ok": ok,
            **usage_of(response),
        })
    except Exception:  # noqa: BLE001 - a broken stopwatch must not break work
        pass


@contextmanager
def timed():
    """Monotonic stopwatch. Immune to wall-clock adjustments."""
    started = time.perf_counter()
    box = {"ms": 0.0}

    try:
        yield box
    finally:
        box["ms"] = (time.perf_counter() - started) * 1000


def summarise(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate audit events into a cost and latency picture.

    Only events that actually carry a measurement are counted. Averaging
    over records that never had a number would produce a confident figure
    describing nothing.
    """
    executions = [
        e for e in events
        if e.get("event_type") == "ACTION_EXECUTED"
        and e.get("duration_ms") is not None
    ]

    model_calls = [e for e in events if e.get("event_type") == "MODEL_CALL"]

    measured_calls = [e for e in model_calls if e.get("measured")]

    durations = sorted(e["duration_ms"] for e in executions)

    tokens = sum(
        e.get("total_tokens") or 0 for e in measured_calls
    )

    by_stage: dict[str, dict[str, Any]] = {}

    for call in model_calls:
        stage = call.get("stage", "unknown")
        entry = by_stage.setdefault(
            stage, {"calls": 0, "tokens": 0, "measured_calls": 0,
                    "total_ms": 0.0},
        )
        entry["calls"] += 1
        entry["total_ms"] += call.get("duration_ms") or 0

        if call.get("measured"):
            entry["measured_calls"] += 1
            entry["tokens"] += call.get("total_tokens") or 0

    for entry in by_stage.values():
        entry["avg_ms"] = (
            round(entry["total_ms"] / entry["calls"], 1)
            if entry["calls"] else None
        )
        entry.pop("total_ms")

    return {
        "tool_executions": {
            "count": len(executions),
            "avg_ms": round(sum(durations) / len(durations), 1)
            if durations else None,
            "p50_ms": durations[len(durations) // 2] if durations else None,
            "max_ms": durations[-1] if durations else None,
        },
        "model_calls": {
            "count": len(model_calls),
            "measured": len(measured_calls),
            "unmeasured": len(model_calls) - len(measured_calls),
            "total_tokens": tokens if measured_calls else None,
        },
        "by_stage": by_stage,
        "note": (
            "Token counts come from the model's own usage_metadata. Calls "
            "without it are counted as unmeasured rather than estimated."
        ),
    }
