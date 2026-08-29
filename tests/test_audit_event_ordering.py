"""list_audit_events() must return a total order, newest first.

Sorting on the ISO timestamp alone is not a total order: events written
inside the same clock tick get byte-identical strings, and Python's sort
is stable, so under reverse=True the OLDEST of a tie landed at index 0.
`list_audit_events()[0]` was therefore not reliably the newest event.

That is the same bug class as the non-deterministic ledger chain
ordering fixed earlier in this project -- fixed for the ledger, missed
for audit events. It surfaced as an intermittent failure in
test_stream_error_mid_pipeline_is_also_recorded_server_side, which reads
index 0 expecting the event it just wrote.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

from app.memory.firestore_store import MemoryFirestore  # noqa: E402


def test_same_tick_writes_are_returned_newest_first():
    """Writes forced onto an identical timestamp -- the exact tie the
    real clock produces occasionally and this reproduces every run."""
    store = MemoryFirestore()

    fixed = "2026-08-29T00:00:00.000000+00:00"

    for index in range(50):
        store.write_audit_event(f"EVENT_{index}", {})

    for event in store.audit_events.values():
        event["timestamp"] = fixed

    events = store.list_audit_events()

    assert [e["event_type"] for e in events] == [
        f"EVENT_{i}" for i in reversed(range(50))
    ]
    assert events[0]["event_type"] == "EVENT_49"


def test_the_newest_event_is_index_zero_under_a_tie():
    """The precise read the flaky test performs."""
    store = MemoryFirestore()

    store.write_audit_event("GUARDIAN_DECISION", {})
    store.write_audit_event("ACQUIRE_STREAM_ERROR", {})

    for event in store.audit_events.values():
        event["timestamp"] = "2026-08-29T00:00:00+00:00"

    assert store.list_audit_events()[0]["event_type"] == "ACQUIRE_STREAM_ERROR"


def test_real_timestamps_still_dominate_the_sequence_number():
    """The sequence number breaks ties; it must never outrank a genuinely
    later timestamp, or a replayed/backfilled event would masquerade as
    the newest."""
    store = MemoryFirestore()

    store.write_audit_event("OLDER", {})
    store.write_audit_event("NEWER", {})

    events = {e["event_type"]: e for e in store.list_audit_events()}
    events["OLDER"]["timestamp"] = "2026-08-29T10:00:00+00:00"
    events["NEWER"]["timestamp"] = "2026-08-29T09:00:00+00:00"

    assert store.list_audit_events()[0]["event_type"] == "OLDER"


def test_limit_returns_the_newest_page_not_an_arbitrary_one():
    store = MemoryFirestore()

    for index in range(10):
        store.write_audit_event(f"EVENT_{index}", {})

    for event in store.audit_events.values():
        event["timestamp"] = "2026-08-29T00:00:00+00:00"

    events = store.list_audit_events(limit=3)

    assert [e["event_type"] for e in events] == [
        "EVENT_9", "EVENT_8", "EVENT_7",
    ]
