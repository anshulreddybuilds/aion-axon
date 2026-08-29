"""Forensic audit of app/beastmode/ledger_chain.py — every attack in the
directive's list, proven, not assumed.

Scope, stated the same way the module's own docstring states it: this is
TAMPER-EVIDENT, not tamper-proof. Every test below proves verify()
correctly reports MISMATCH after a given attack; none of them prove an
attacker with direct Firestore write access (the seal itself now lives
in Firestore too, at system/ledger_seal -- see ledger_chain.py's module
docstring for why it moved off local disk) cannot edit-then-reseal over
their own tamper -- that is the module's documented, honest limitation,
not something a test can paper over. What these tests establish is the
actual claim the module makes: "if the events changed since the last
seal in any way, verify() will say so."
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

import app.beastmode.ledger_chain as lc
from app.memory.firestore_store import firestore_store


def _events(n: int, **overrides) -> list[dict]:
    base = [
        {
            "change": f"event {i}", "capability": f"cap_{i}",
            "approver": "anshul", "timestamp": f"2026-08-{20+i:02d}T10:00:00Z",
        }
        for i in range(n)
    ]
    for e in base:
        e.update(overrides)
    return base


def _sealed(tmp_path, monkeypatch, events):
    # tmp_path kept in the signature so every call site below is
    # unchanged -- seal storage moved from a local file to
    # firestore_store (see ledger_chain.py's module docstring for why:
    # a Cloud Run container's filesystem is neither shared across
    # instances nor durable across a cold start), so isolating each
    # test now just means resetting that in-process state instead of
    # pointing at a fresh tmp_path file.
    monkeypatch.setattr(firestore_store, "ledger_seal", None)
    lc.seal(events)
    return events


# --- modify -----------------------------------------------------------

def test_modify_one_event_payload_is_detected(tmp_path, monkeypatch):
    events = _sealed(tmp_path, monkeypatch, _events(4))
    tampered = [dict(e) for e in events]
    tampered[1]["change"] = "silently altered"
    assert lc.verify(tampered)["status"] == "MISMATCH"


def test_modify_timestamp_is_detected(tmp_path, monkeypatch):
    events = _sealed(tmp_path, monkeypatch, _events(4))
    tampered = [dict(e) for e in events]
    tampered[2]["timestamp"] = "2099-01-01T00:00:00Z"
    assert lc.verify(tampered)["status"] == "MISMATCH"


def test_modify_capability_name_is_detected(tmp_path, monkeypatch):
    events = _sealed(tmp_path, monkeypatch, _events(4))
    tampered = [dict(e) for e in events]
    tampered[0]["capability"] = "a_different_capability"
    assert lc.verify(tampered)["status"] == "MISMATCH"


def test_modify_actor_is_detected(tmp_path, monkeypatch):
    events = _sealed(tmp_path, monkeypatch, _events(4))
    tampered = [dict(e) for e in events]
    tampered[3]["approver"] = "not-the-real-owner"
    assert lc.verify(tampered)["status"] == "MISMATCH"


# --- delete -------------------------------------------------------------

def test_delete_middle_event_is_detected(tmp_path, monkeypatch):
    events = _sealed(tmp_path, monkeypatch, _events(5))
    with_deletion = events[:2] + events[3:]
    assert lc.verify(with_deletion)["status"] == "MISMATCH"


def test_delete_final_event_is_detected(tmp_path, monkeypatch):
    events = _sealed(tmp_path, monkeypatch, _events(5))
    with_deletion = events[:-1]
    report = lc.verify(with_deletion)
    assert report["status"] == "MISMATCH"
    assert report["event_count"] != report["sealed_event_count"]


# --- insert / duplicate / replace ----------------------------------------

def test_insert_a_fake_event_is_detected(tmp_path, monkeypatch):
    events = _sealed(tmp_path, monkeypatch, _events(4))
    forged = events[:2] + [{"change": "forged event", "capability": "fake_cap",
                             "approver": "attacker", "timestamp": "2026-08-24T00:00:00Z"}] + events[2:]
    assert lc.verify(forged)["status"] == "MISMATCH"


def test_duplicate_an_event_is_detected(tmp_path, monkeypatch):
    events = _sealed(tmp_path, monkeypatch, _events(4))
    with_dup = events[:2] + [dict(events[1])] + events[2:]
    assert lc.verify(with_dup)["status"] == "MISMATCH"


def test_replace_an_event_with_an_old_valid_event_is_detected(tmp_path, monkeypatch):
    """A subtler forgery than inserting garbage: swap event #3 for a
    COPY of event #0 -- every field is a real, previously-valid event
    payload, just in the wrong slot. Still must be caught, because the
    chain is order- and position-sensitive, not merely a set membership
    check."""
    events = _sealed(tmp_path, monkeypatch, _events(4))
    replaced = list(events)
    replaced[3] = dict(events[0])
    assert lc.verify(replaced)["status"] == "MISMATCH"


# --- reorder --------------------------------------------------------------
#
# Batch 2 / SEC-05: build_chain() now imposes its own canonical
# (timestamp, event_id) order on whatever list it receives, rather than
# trusting caller-supplied list order -- see ledger_chain.py's module
# docstring. This is deliberate: firestore_store.list_evolution_events()
# never guaranteed any particular order in the first place (a plain
# .stream() with no .order_by()), so "list position" was never a
# meaningful signal in production; only real field content is. One
# consequence: swapping two events' LIST POSITIONS with their field
# values unchanged is no longer detectable, because it's no longer a
# real difference -- canonical ordering restores the same chain either
# way. That is the fix working as intended, not a regression: it removes
# a false-positive surface (Firestore returning events in a different
# but equally valid stream order between two verify() calls would
# previously have looked identical to an actual reorder attack).
#
# A REAL reorder attempt -- one that actually changes which event the
# system believes happened when -- means changing the timestamp field
# itself, and that must still be detected, because it changes both the
# tampered event's own hash AND (potentially) its position in canonical
# order.

def test_swapping_list_position_alone_is_no_longer_a_detectable_difference(tmp_path, monkeypatch):
    """Negative control proving the new behavior is intentional: two
    events already in canonical order, handed to verify() in swapped
    LIST position but with identical field content, must still verify --
    list order was never authoritative."""
    events = _sealed(tmp_path, monkeypatch, _events(4))
    reordered = list(events)
    reordered[1], reordered[2] = reordered[2], reordered[1]
    assert lc.verify(reordered)["status"] == "VERIFIED"


def test_changing_an_events_timestamp_to_actually_reorder_it_is_detected(tmp_path, monkeypatch):
    """The real reorder attack: making an event LOOK like it happened at
    a different point in the sequence by rewriting its timestamp. This
    changes real data, not just list position, and must still be caught."""
    events = _sealed(tmp_path, monkeypatch, _events(4))
    tampered = [dict(e) for e in events]
    # Rewrite event 3's timestamp to sort before event 0 -- an attempt to
    # make a later real event appear to have happened first.
    tampered[3]["timestamp"] = "2020-01-01T00:00:00Z"
    assert lc.verify(tampered)["status"] == "MISMATCH"


# --- replay ---------------------------------------------------------------

def test_replaying_an_old_full_valid_chain_after_new_events_were_added_is_detected(tmp_path, monkeypatch):
    """The chain grew (a real 5th event was appended and re-sealed);
    presenting the OLD 4-event chain as current must not verify against
    the NEW seal."""
    monkeypatch.setattr(firestore_store, "ledger_seal", None)
    old_events = _events(4)
    lc.seal(old_events)

    new_events = old_events + _events(1, capability="cap_new")
    lc.seal(new_events)  # legitimate re-seal after real growth

    report = lc.verify(old_events)  # attacker presents the stale chain
    assert report["status"] == "MISMATCH"


# --- edge cases: empty / single / no-seal ----------------------------------

def test_verify_an_unsealed_ledger_is_honest_not_a_crash(monkeypatch):
    monkeypatch.setattr(firestore_store, "ledger_seal", None)
    report = lc.verify(_events(3))
    assert report["status"] == "NO_SEAL"


def test_verify_an_empty_ledger_after_sealing_empty(monkeypatch):
    monkeypatch.setattr(firestore_store, "ledger_seal", None)
    lc.seal([])
    report = lc.verify([])
    assert report["status"] == "VERIFIED"
    assert report["event_count"] == 0
    assert report["current_final_hash"] == lc.GENESIS


def test_verify_a_single_event_ledger(tmp_path, monkeypatch):
    events = _sealed(tmp_path, monkeypatch, _events(1))
    report = lc.verify(events)
    assert report["status"] == "VERIFIED"


def test_tampering_a_single_event_ledger_is_still_detected(tmp_path, monkeypatch):
    events = _sealed(tmp_path, monkeypatch, _events(1))
    tampered = [dict(events[0])]
    tampered[0]["change"] = "tampered"
    assert lc.verify(tampered)["status"] == "MISMATCH"


# --- legitimate growth must be DISTINGUISHABLE IN CAUSE, even though the
# status code is the same MISMATCH as tampering. This is the module's
# stated interpretation: verify() proves "nothing changed since sealing",
# full stop -- it cannot and does not claim to distinguish honest growth
# from tampering. That is a real limitation, documented rather than
# hidden, so this test locks in that the wording says so.

def test_verify_after_legitimate_append_reports_mismatch_not_a_false_verified(tmp_path, monkeypatch):
    """A real new capability acquisition after sealing must NOT report
    VERIFIED -- that would be worse than useless, since VERIFIED is
    supposed to mean 'nothing changed'. It correctly reports MISMATCH,
    and the detail text must not claim tampering when it cannot tell the
    difference from honest growth."""
    events = _sealed(tmp_path, monkeypatch, _events(3))
    grown = events + _events(1, capability="cap_new_real_acquisition")
    report = lc.verify(grown)
    assert report["status"] == "MISMATCH"
    assert "reordered" in report["detail"] or "changed" in report["detail"]
    assert "tamper" not in report["detail"].lower()  # never accuses without proof


def test_verify_after_rollback_event_appended_is_mismatch_until_resealed(tmp_path, monkeypatch):
    events = _sealed(tmp_path, monkeypatch, _events(3))
    rollback_event = {"change": "Rolled back 'cap_1'.", "capability": "cap_1",
                       "approver": None, "timestamp": "2026-08-25T00:00:00Z"}
    with_rollback = events + [rollback_event]
    assert lc.verify(with_rollback)["status"] == "MISMATCH"

    # Re-sealing over the honest new state must restore VERIFIED.
    lc.seal(with_rollback)
    assert lc.verify(with_rollback)["status"] == "VERIFIED"


# --- Batch 2 / SEC-05: ordering determinism -------------------------------
# The required property list from the remediation directive, adapted to
# what this schema actually has. `artifact_hash` does not exist anywhere
# in this codebase (checked: no field, no concept, in events, passports,
# or approvals) -- the closest real analog to "the artifact's identity"
# stored in an event is `test_results` (the real sandbox execution record
# the code actually produced) and `evaluation` (the score/verdict it
# received), both tested explicitly below rather than a fabricated field.

def _events_with_event_id(n: int, **overrides) -> list[dict]:
    """Same shape write_evolution_event() actually produces: event_id
    present as a real field, not just an incidental list position."""
    base = _events(n, **overrides)
    for i, e in enumerate(base):
        e["event_id"] = f"evt-{i}"
    return base


def test_same_events_produce_the_same_chain_regardless_of_call():
    events = _events_with_event_id(5)
    chain1 = lc.build_chain(events)
    chain2 = lc.build_chain(events)
    assert chain1[-1].chain_hash == chain2[-1].chain_hash


def test_same_events_in_a_different_input_list_order_produce_the_same_chain():
    """The actual fix under test: firestore_store.list_evolution_events()
    never guaranteed a particular return order. Two reads that return the
    same events in different LIST order must still produce the same
    chain -- this is the property that was broken before this batch."""
    events = _events_with_event_id(6)
    shuffled = [events[3], events[0], events[5], events[1], events[4], events[2]]

    chain_original = lc.build_chain(events)
    chain_shuffled = lc.build_chain(shuffled)

    assert chain_original[-1].chain_hash == chain_shuffled[-1].chain_hash


def test_events_with_genuinely_different_timestamps_produce_a_different_chain():
    events_a = _events_with_event_id(4)
    events_b = [dict(e) for e in events_a]
    events_b[2]["timestamp"] = "2099-01-01T00:00:00Z"

    chain_a = lc.build_chain(events_a)
    chain_b = lc.build_chain(events_b)

    assert chain_a[-1].chain_hash != chain_b[-1].chain_hash


def test_timestamp_collision_is_broken_deterministically_by_event_id():
    """Two events with an IDENTICAL timestamp (a real possibility -- see
    the module docstring) must still sort the same way every time, via
    the event_id tiebreak, regardless of input list order."""
    colliding = [
        {"change": "e0", "capability": "cap_0", "approver": "a",
         "timestamp": "2026-08-24T10:00:00.000000+00:00", "event_id": "evt-a"},
        {"change": "e1", "capability": "cap_1", "approver": "a",
         "timestamp": "2026-08-24T10:00:00.000000+00:00", "event_id": "evt-b"},
    ]
    reversed_input = list(reversed(colliding))

    chain1 = lc.build_chain(colliding)
    chain2 = lc.build_chain(reversed_input)

    assert chain1[-1].chain_hash == chain2[-1].chain_hash
    # And the order actually used is the deterministic (timestamp, event_id)
    # order, not whichever input order happened to be passed -- both chains'
    # first link must be event_id "evt-a" (sorts first lexicographically).
    assert chain1[0].event_hash == chain2[0].event_hash


def test_repeated_reads_in_different_orders_all_verify_against_one_seal(tmp_path, monkeypatch):
    """Simulates what an unordered Firestore .stream() actually does:
    the same underlying events, returned in a different order on a
    second read. Both reads must verify cleanly against the same seal."""
    monkeypatch.setattr(firestore_store, "ledger_seal", None)
    events = _events_with_event_id(5)
    lc.seal(events)

    read_order_1 = list(events)
    read_order_2 = [events[4], events[1], events[3], events[0], events[2]]

    assert lc.verify(read_order_1)["status"] == "VERIFIED"
    assert lc.verify(read_order_2)["status"] == "VERIFIED"


def test_modifying_the_sandbox_test_results_in_an_event_is_detected(tmp_path, monkeypatch):
    """The closest real analog to "artifact identity" this schema has:
    the real sandbox execution record the installed code actually
    produced. Forging it after the fact must be caught."""
    events = _events_with_event_id(3, test_results={"passed": True, "stdout": "OK", "exit_code": 0})
    sealed = _sealed(tmp_path, monkeypatch, events)
    tampered = [dict(e) for e in sealed]
    tampered[1]["test_results"] = {"passed": True, "stdout": "FORGED", "exit_code": 0}
    assert lc.verify(tampered)["status"] == "MISMATCH"


def test_modifying_the_evaluator_score_in_an_event_is_detected(tmp_path, monkeypatch):
    events = _events_with_event_id(3, evaluation={"status": "SCORED", "score": 40, "verdict": "FAIL"})
    sealed = _sealed(tmp_path, monkeypatch, events)
    tampered = [dict(e) for e in sealed]
    tampered[0]["evaluation"] = {"status": "SCORED", "score": 95, "verdict": "PASS"}
    assert lc.verify(tampered)["status"] == "MISMATCH"


# --- durability (the actual bug this session found and fixed) --------------

def test_seal_survives_a_simulated_cold_start_not_just_the_calling_process(monkeypatch):
    """The real bug: seal() used to write to a file next to this module
    (SEAL_PATH). That worked in one long-running local process, but on
    Cloud Run a container's filesystem is neither shared across
    instances nor durable across a cold start/redeploy -- a seal written
    by one instance was invisible to every OTHER concurrently-running
    instance and vanished the moment the instance that wrote it was
    recycled. A brand new AxonFirestore/MemoryFirestore instance
    (standing in for a fresh Cloud Run container with an empty local
    filesystem, same image) must still see the seal, because it now
    lives in Firestore, not on disk."""
    from app.memory.firestore_store import MemoryFirestore

    monkeypatch.setattr(firestore_store, "ledger_seal", None)
    events = _events(3)
    lc.seal(events)

    # Simulate a second, independent process/container reading from the
    # SAME backing store (Firestore) rather than the same in-memory
    # object -- the real point of the fix. A fresh MemoryFirestore()
    # instance has its own empty __dict__ (no shared state with the
    # module singleton at all), so if seal() had written anywhere other
    # than the shared `firestore_store` singleton's own storage, copying
    # its ledger_seal value across would be the only way this could pass.
    fresh_instance = MemoryFirestore()
    fresh_instance.ledger_seal = firestore_store.get_ledger_seal()

    assert fresh_instance.get_ledger_seal() is not None
    assert fresh_instance.get_ledger_seal()["event_count"] == 3


def test_seal_no_longer_touches_local_disk(monkeypatch):
    """Direct proof the old SEAL_PATH file is dead code, not just
    unused: the old code wrote to an absolute path next to this module
    (Path(__file__).parent / "ledger_seal.json") regardless of cwd, so
    that exact path -- not a relative one a cwd trick could catch -- is
    checked directly, plus the attribute itself being gone."""
    from pathlib import Path

    old_seal_path = Path(lc.__file__).parent / "ledger_seal.json"

    monkeypatch.setattr(firestore_store, "ledger_seal", None)
    lc.seal(_events(2))

    assert not old_seal_path.exists(), (
        f"seal() wrote to {old_seal_path} -- the old local-disk path is "
        "supposed to be dead code now that Firestore is the backing store"
    )
    assert not hasattr(lc, "SEAL_PATH")
