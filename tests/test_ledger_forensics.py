"""Forensic audit of app/beastmode/ledger_chain.py — every attack in the
directive's list, proven, not assumed.

Scope, stated the same way the module's own docstring states it: this is
TAMPER-EVIDENT, not tamper-proof. Every test below proves verify()
correctly reports MISMATCH after a given attack; none of them prove an
attacker with direct Firestore write access AND local disk write access
to ledger_seal.json cannot edit-then-reseal over their own tamper --
that is the module's documented, honest limitation, not something a test
can paper over. What these tests establish is the actual claim the
module makes: "if the events changed since the last seal in any way,
verify() will say so."
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

import app.beastmode.ledger_chain as lc


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
    monkeypatch.setattr(lc, "SEAL_PATH", tmp_path / "seal.json")
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

def test_reorder_two_events_is_detected(tmp_path, monkeypatch):
    events = _sealed(tmp_path, monkeypatch, _events(4))
    reordered = list(events)
    reordered[1], reordered[2] = reordered[2], reordered[1]
    assert lc.verify(reordered)["status"] == "MISMATCH"


# --- replay ---------------------------------------------------------------

def test_replaying_an_old_full_valid_chain_after_new_events_were_added_is_detected(tmp_path, monkeypatch):
    """The chain grew (a real 5th event was appended and re-sealed);
    presenting the OLD 4-event chain as current must not verify against
    the NEW seal."""
    monkeypatch.setattr(lc, "SEAL_PATH", tmp_path / "seal.json")
    old_events = _events(4)
    lc.seal(old_events)

    new_events = old_events + _events(1, capability="cap_new")
    lc.seal(new_events)  # legitimate re-seal after real growth

    report = lc.verify(old_events)  # attacker presents the stale chain
    assert report["status"] == "MISMATCH"


# --- edge cases: empty / single / no-seal ----------------------------------

def test_verify_an_unsealed_ledger_is_honest_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(lc, "SEAL_PATH", tmp_path / "never_sealed.json")
    report = lc.verify(_events(3))
    assert report["status"] == "NO_SEAL"


def test_verify_an_empty_ledger_after_sealing_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(lc, "SEAL_PATH", tmp_path / "seal.json")
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
