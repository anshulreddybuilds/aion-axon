"""SHA-256 hash-chained ledger — additive over the REAL evolution events.

This did not exist before this pass (confirmed in
docs/AXON_BEASTMODE_AUDIT.md). Evolution events were stored, ordered, and
readable, but never hash-chained.

Scope, stated precisely because it matters for what this can and cannot
prove:

  - Hashes are computed at VERIFICATION time from events already recorded
    by the existing, unmodified write path (app.memory.firestore_store).
    Nothing about how or when an event is written has changed.
  - A SEAL is a snapshot: the final chain hash at a point in time, saved
    to disk. Re-verifying later and getting the SAME final hash proves
    nothing in the ledger was altered or reordered between seal and
    verification. Getting a DIFFERENT hash proves something was.
  - This is tamper-EVIDENT, not tamper-PROOF: nothing here stops someone
    with direct Firestore write access from editing an event AND
    re-sealing over the edit. Detecting that would need the seal to live
    somewhere the same actor cannot write to (out of scope for this pass,
    and stated here rather than implied away).

Batch 2 / SEC-05 (ordering determinism): `firestore_store.list_evolution_events()`
reads via a plain Firestore `.stream()` with no `.order_by()` clause --
Firestore does not guarantee stream order without one, and adding a
multi-field `.order_by()` to the live query risks requiring a composite
index that may not exist in production (a real deployment risk, not
something to introduce blindly from this environment). Since the hash
chain is order-dependent by construction, an order-agnostic caller feeding
it meant `final_hash` was not reliably reproducible across separate reads
independent of any tampering -- found live 24 Aug when a real ledger
re-verification did not reproduce the production seal's hash even though
the only real change was one legitimate new event.

The fix lives HERE rather than in the Firestore query: `build_chain()` now
imposes its own canonical order on whatever list it's given, rather than
trusting caller-supplied order (the opposite of this module's previous
design). Ordering key is `(timestamp, event_id)`: `timestamp` is the real
chronological signal, `event_id` is a guaranteed-unique field written into
every event by BOTH firestore_store backends (not just the Firestore
document ID -- see write_evolution_event()) and breaks a timestamp
collision deterministically. It does not need to preserve "true" order
under a collision, only PRODUCE THE SAME order every time given the same
events -- which is the actual property tamper-evidence depends on.

This changes nothing about existing events, does not reorder or rewrite
any historical record, and does not touch the existing seal file. It only
changes how `build_chain()`/`seal()`/`verify()` compute a hash from
whatever event list they're handed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GENESIS = "0" * 64

SEAL_PATH = Path(__file__).parent / "ledger_seal.json"


def _canonical(event: dict[str, Any]) -> str:
    """A stable string for one event, independent of key order."""
    return json.dumps(event, sort_keys=True, default=str)


def _event_hash(event: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(event).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChainLink:
    index: int
    event_hash: str
    chain_hash: str
    change: str


def _canonical_order(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic, reproducible order: (timestamp, event_id).

    Both fields are always present -- written by every code path that
    creates an evolution event, in both the memory and real Firestore
    backends (see firestore_store.write_evolution_event()). Sorting here,
    rather than trusting whatever order the caller's query happened to
    return, is what makes seal()/verify() reproducible across separate
    reads regardless of Firestore's own unordered `.stream()`.
    """
    return sorted(
        events,
        key=lambda e: (str(e.get("timestamp") or ""), str(e.get("event_id") or "")),
    )


def build_chain(events: list[dict[str, Any]]) -> list[ChainLink]:
    """Chain events in canonical (timestamp, event_id) order, regardless
    of the order the caller passed them in -- see _canonical_order().
    Still testable with plain fixtures; it just no longer trusts the
    fixture's own list order either, which is deliberate: a test that
    only passes because its fixture happened to already be sorted would
    hide exactly the bug this fixes.
    """
    events = _canonical_order(events)
    chain: list[ChainLink] = []
    previous = GENESIS

    for i, event in enumerate(events):
        e_hash = _event_hash(event)
        c_hash = hashlib.sha256((previous + e_hash).encode("utf-8")).hexdigest()
        chain.append(ChainLink(
            index=i,
            event_hash=e_hash,
            chain_hash=c_hash,
            change=str(event.get("change", ""))[:80],
        ))
        previous = c_hash

    return chain


def seal(events: list[dict[str, Any]]) -> dict:
    """Write the current final chain hash to disk. This IS the claim
    "the ledger looked like this at this moment" — nothing more."""
    chain = build_chain(events)
    final = chain[-1].chain_hash if chain else GENESIS

    record = {"event_count": len(events), "final_hash": final}
    SEAL_PATH.write_text(json.dumps(record, indent=2))
    return record


def verify(events: list[dict[str, Any]]) -> dict:
    """Recompute the chain now and compare against the last seal.

    Returns a report rather than a bare bool, because "VERIFIED" with no
    detail is exactly the kind of unearned confidence this project argues
    against.
    """
    chain = build_chain(events)
    current_final = chain[-1].chain_hash if chain else GENESIS

    if not SEAL_PATH.exists():
        return {
            "status": "NO_SEAL",
            "event_count": len(events),
            "current_final_hash": current_final,
            "detail": "No prior seal on disk — nothing to compare against yet. "
                      "Run seal() to create a baseline.",
        }

    sealed = json.loads(SEAL_PATH.read_text())
    intact = (
        sealed.get("final_hash") == current_final
        and sealed.get("event_count") == len(events)
    )

    return {
        "status": "VERIFIED" if intact else "MISMATCH",
        "event_count": len(events),
        "sealed_event_count": sealed.get("event_count"),
        "current_final_hash": current_final,
        "sealed_final_hash": sealed.get("final_hash"),
        "detail": (
            f"{len(events)}/{len(events)} events chain-verified against the last seal."
            if intact
            else "Chain hash or event count no longer matches the last seal — "
                 "the ledger has changed since sealing, or events were reordered."
        ),
    }
