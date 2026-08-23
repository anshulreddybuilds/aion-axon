"""app/beastmode/quarantine.py — derived from real audit-event fields.

Fixtures mirror app/synapse/engine.py._audit()'s ACTUAL write shape
(need, stage, status, reason, capability, policy_id) plus the
event_type/timestamp firestore_store.write_audit_event() adds, so a field
rename in either place breaks these loudly rather than the quarantine view
silently going blank.
"""
from app.beastmode.quarantine import compute_quarantine, to_dict


def _event(event_type, capability, status, **extra):
    return {
        "event_type": event_type, "capability": capability, "status": status,
        "stage": extra.pop("stage", "EVALUATE"),
        "reason": extra.pop("reason", "some reason"),
        "policy_id": extra.pop("policy_id", None),
        "timestamp": extra.pop("timestamp", "2026-08-23T10:00:00Z"),
    }


def test_a_rejected_capability_is_quarantined():
    events = [_event("SYNAPSE_REJECTED", "bad_cap", "REJECTED")]
    entries = compute_quarantine(events)
    assert len(entries) == 1
    assert entries[0].capability == "bad_cap"
    assert entries[0].status == "REJECTED"


def test_refused_and_blocked_are_also_quarantine_states():
    events = [
        _event("SYNAPSE_REFUSED", "cap_a", "REFUSED", timestamp="2026-08-23T10:00:00Z"),
        _event("SYNAPSE_BLOCKED", "cap_b", "BLOCKED", timestamp="2026-08-23T10:01:00Z"),
    ]
    entries = compute_quarantine(events)
    caps = {e.capability for e in entries}
    assert caps == {"cap_a", "cap_b"}


def test_a_later_successful_pass_clears_quarantine():
    """The real lifecycle this session hit: calculate_yearly_birth_stats
    failed once (evaluator returned no score) then succeeded on retry.
    A capability must NOT show as quarantined if a later, real event
    cleared it."""
    events = [
        _event("SYNAPSE_REJECTED", "flaky_cap", "REJECTED", timestamp="2026-08-23T10:00:00Z"),
        _event("SYNAPSE_AWAITING_APPROVAL", "flaky_cap", "AWAITING_APPROVAL", timestamp="2026-08-23T10:05:00Z"),
    ]
    entries = compute_quarantine(events)
    assert entries == []


def test_installed_capability_is_never_quarantined():
    events = [
        _event("SYNAPSE_AWAITING_APPROVAL", "good_cap", "AWAITING_APPROVAL", timestamp="2026-08-23T10:00:00Z"),
    ]
    assert compute_quarantine(events) == []


def test_events_out_of_order_are_still_evaluated_by_real_timestamp():
    """Same discipline as lineage: never trust caller order."""
    events = [
        _event("SYNAPSE_AWAITING_APPROVAL", "cap_a", "AWAITING_APPROVAL", timestamp="2026-08-23T10:05:00Z"),
        _event("SYNAPSE_REJECTED", "cap_a", "REJECTED", timestamp="2026-08-23T10:00:00Z"),
    ]
    # Rejection happened FIRST, approval SECOND -- should clear, not quarantine.
    assert compute_quarantine(events) == []


def test_repeated_rejections_report_the_most_recent_reason():
    events = [
        _event("SYNAPSE_REJECTED", "cap_a", "REJECTED", reason="first reason", timestamp="2026-08-23T10:00:00Z"),
        _event("SYNAPSE_REJECTED", "cap_a", "REJECTED", reason="second reason", timestamp="2026-08-23T10:05:00Z"),
    ]
    entries = compute_quarantine(events)
    assert len(entries) == 1
    assert entries[0].reason == "second reason"


def test_events_with_no_capability_name_are_ignored_not_a_crash():
    events = [{"event_type": "SYNAPSE_FAILED", "status": "FAILED", "timestamp": "t"}]
    assert compute_quarantine(events) == []


def test_to_dict_is_json_serialisable_shape():
    events = [_event("SYNAPSE_REJECTED", "cap_a", "REJECTED")]
    d = to_dict(compute_quarantine(events)[0])
    assert set(d.keys()) == {"capability", "status", "stage", "reason", "policy_id", "timestamp", "event_type"}
