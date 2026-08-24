"""Capability lineage — a real version history, derived from real events.

Confirmed absent in docs/AXON_BEASTMODE_AUDIT.md: "one name = one live
implementation; no v1/v2/v3 history." This module does not add a new
write path to create that history -- the evolution ledger already
contains every acquisition and rollback, timestamped, per capability.
Lineage is reconstructed by grouping and ordering those REAL events; it
never invents an event that was not already written by
app/synapse/engine.py.

Kept deliberately read-only and separate from the write path for the same
reason as the rest of this package: touching app/synapse/engine.py's
tested install/rollback logic this close to a deadline is a materially
different risk than reading its output more richly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LineageStep:
    version: int
    kind: str  # "ACQUIRED" | "ROLLED_BACK"
    change: str
    reason: str
    timestamp: str
    event_id: str


def build_lineage(capability: str, events: list[dict[str, Any]]) -> list[LineageStep]:
    """Real events for ONE capability, in real chronological order.

    `events` should be everything from firestore_store.list_evolution_events()
    -- this function filters and sorts, it does not fetch, so it can be
    tested with fixtures and reused against the live store identically.
    """
    relevant = [e for e in events if e.get("capability_id") == capability]
    relevant.sort(key=lambda e: e.get("timestamp") or "")

    steps: list[LineageStep] = []
    version = 0

    for event in relevant:
        is_rollback = bool(event.get("rollback")) or "Rolled back" in str(event.get("change", ""))

        if not is_rollback:
            version += 1

        steps.append(LineageStep(
            version=version,
            kind="ROLLED_BACK" if is_rollback else "ACQUIRED",
            change=str(event.get("change", "")),
            reason=str(event.get("reason", ""))[:200],
            timestamp=str(event.get("timestamp", "")),
            event_id=str(event.get("event_id", "")),
        ))

    return steps


def current_version(capability: str, events: list[dict[str, Any]]) -> int:
    """The version number of the most recent step, or 0 if the capability
    has never been acquired or its last action was a rollback."""
    steps = build_lineage(capability, events)
    if not steps:
        return 0
    last = steps[-1]
    return 0 if last.kind == "ROLLED_BACK" else last.version


def to_dict(step: LineageStep) -> dict:
    return {
        "version": step.version,
        "kind": step.kind,
        "change": step.change,
        "reason": step.reason,
        "timestamp": step.timestamp,
        "event_id": step.event_id,
    }
