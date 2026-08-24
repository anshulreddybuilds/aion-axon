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


def build_chain(events: list[dict[str, Any]]) -> list[ChainLink]:
    """Chain events in the order given. Caller supplies real event order —
    this module does not fetch or sort, so it can be tested with fixtures
    without needing Firestore.
    """
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
