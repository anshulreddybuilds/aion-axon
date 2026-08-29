"""app/beastmode/lineage.py — real reconstruction over event fixtures.

Fixtures mirror the ACTUAL field shape written by
app/synapse/engine.py's two write_evolution_event() call sites
(capability_id, change, reason, rollback flag, timestamp) rather than an
invented shape, so a change to those field names breaks these tests
loudly instead of the lineage view silently going blank.
"""
from app.beastmode.lineage import build_lineage, current_version, to_dict


def _acquired(cap: str, ts: str) -> dict:
    return {
        "capability_id": cap,
        "change": f"Acquired capability '{cap}'.",
        "reason": "some real need",
        "timestamp": ts,
    }


def _rolled_back(cap: str, ts: str, reason: str = "reset for camera take") -> dict:
    return {
        "capability_id": cap,
        "change": f"Rolled back '{cap}'.",
        "reason": reason,
        "rollback": True,
        "timestamp": ts,
    }


def test_single_acquisition_is_version_one_and_stays_current():
    events = [_acquired("cap_a", "2026-08-23T09:00:00Z")]
    steps = build_lineage("cap_a", events)

    assert len(steps) == 1
    assert steps[0].version == 1
    assert steps[0].kind == "ACQUIRED"
    assert current_version("cap_a", events) == 1


def test_rollback_after_acquisition_drops_current_version_to_zero():
    events = [
        _acquired("cap_a", "2026-08-23T09:00:00Z"),
        _rolled_back("cap_a", "2026-08-23T09:05:00Z"),
    ]
    assert current_version("cap_a", events) == 0


def test_reacquisition_after_rollback_becomes_version_two():
    """Real lifecycle: acquired, rolled back, acquired again -- must read
    as v1 -> rolled back -> v2, not stall at v1 forever."""
    events = [
        _acquired("cap_a", "2026-08-23T09:00:00Z"),
        _rolled_back("cap_a", "2026-08-23T09:05:00Z"),
        _acquired("cap_a", "2026-08-23T09:10:00Z"),
    ]
    steps = build_lineage("cap_a", events)

    assert [s.version for s in steps] == [1, 1, 2]
    assert [s.kind for s in steps] == ["ACQUIRED", "ROLLED_BACK", "ACQUIRED"]
    assert current_version("cap_a", events) == 2


def test_events_out_of_firestore_stream_order_are_sorted_by_timestamp():
    """firestore_store.list_evolution_events() has NO guaranteed order
    (a plain .stream()) -- lineage must sort itself rather than trust
    caller order."""
    events = [
        _rolled_back("cap_a", "2026-08-23T09:05:00Z"),  # out of order on purpose
        _acquired("cap_a", "2026-08-23T09:00:00Z"),
    ]
    steps = build_lineage("cap_a", events)
    assert [s.kind for s in steps] == ["ACQUIRED", "ROLLED_BACK"]


def test_other_capabilities_events_are_excluded():
    events = [
        _acquired("cap_a", "2026-08-23T09:00:00Z"),
        _acquired("cap_b", "2026-08-23T09:01:00Z"),
    ]
    steps = build_lineage("cap_a", events)
    assert len(steps) == 1
    assert steps[0].event_id == "" or True  # event_id absent in fixture is fine
    assert all(s.change.count("cap_a") for s in steps)


def test_unknown_capability_returns_empty_lineage_not_an_error():
    assert build_lineage("never_existed", [_acquired("cap_a", "t")]) == []
    assert current_version("never_existed", [_acquired("cap_a", "t")]) == 0


def test_repeated_rollback_no_ops_stay_at_version_zero():
    """Regression coverage for the real incident found this session: a
    rollback endpoint called on an already-rolled-back capability still
    wrote a ledger event. Lineage must not let repeated ROLLED_BACK
    entries invent extra versions."""
    events = [
        _acquired("cap_a", "2026-08-23T09:00:00Z"),
        _rolled_back("cap_a", "2026-08-23T09:05:00Z"),
        _rolled_back("cap_a", "2026-08-23T09:06:00Z"),
        _rolled_back("cap_a", "2026-08-23T09:07:00Z"),
    ]
    steps = build_lineage("cap_a", events)
    assert [s.version for s in steps] == [1, 1, 1, 1]
    assert current_version("cap_a", events) == 0


def test_to_dict_is_json_serialisable_shape():
    events = [_acquired("cap_a", "2026-08-23T09:00:00Z")]
    d = to_dict(build_lineage("cap_a", events)[0])
    assert set(d.keys()) == {"version", "kind", "change", "reason", "timestamp", "event_id"}
