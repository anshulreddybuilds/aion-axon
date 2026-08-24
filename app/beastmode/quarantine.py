"""Quarantine — a real state, derived from real audit events.

Confirmed absent in docs/AXON_BEASTMODE_AUDIT.md. Rather than add a new
write path into synapse.py's rejection branches (the same risk class as
the retry feature, and the acquisition path has already taken one such
change tonight), this reconstructs quarantine status from audit events
app/synapse/engine.py._audit() ALREADY writes on every REJECTED, REFUSED
and BLOCKED outcome -- capability, stage, status, reason, policy_id, all
real fields, confirmed by reading _audit() directly.

A capability is QUARANTINED if its most recent audit event for that name
is a rejection/refusal/block AND it has no more recent
SYNAPSE_AWAITING_APPROVAL event (which would mean a later attempt cleared
screening). This is read-only aggregation, not a new gate -- nothing here
can install, approve or block anything that the real pipeline did not
already install, approve or block.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_NEGATIVE_STATUSES = {"REJECTED", "REFUSED", "BLOCKED"}
_CLEARED_STATUSES = {"AWAITING_APPROVAL", "INSTALLED"}


@dataclass(frozen=True)
class QuarantineEntry:
    capability: str
    status: str  # the real record.status at the most recent relevant event
    stage: str
    reason: str
    policy_id: str | None
    timestamp: str
    event_type: str


def compute_quarantine(events: list[dict[str, Any]]) -> list[QuarantineEntry]:
    """Given real audit events (newest or oldest order, either is fine --
    this sorts itself), return one entry per capability whose LATEST
    relevant event was a rejection, refusal or block with nothing clearing
    it afterward.
    """
    relevant = [e for e in events if e.get("capability")]
    relevant.sort(key=lambda e: e.get("timestamp") or "")

    latest_by_capability: dict[str, dict[str, Any]] = {}
    for event in relevant:
        cap = event["capability"]
        if event.get("status") in _NEGATIVE_STATUSES or event.get("status") in _CLEARED_STATUSES:
            latest_by_capability[cap] = event

    entries = []
    for cap, event in latest_by_capability.items():
        if event.get("status") not in _NEGATIVE_STATUSES:
            continue  # most recent relevant event was a clean pass
        entries.append(QuarantineEntry(
            capability=cap,
            status=event.get("status", ""),
            stage=event.get("stage", ""),
            reason=str(event.get("reason") or "")[:300],
            policy_id=event.get("policy_id"),
            timestamp=event.get("timestamp", ""),
            event_type=event.get("event_type", ""),
        ))

    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return entries


def to_dict(entry: QuarantineEntry) -> dict:
    return {
        "capability": entry.capability,
        "status": entry.status,
        "stage": entry.stage,
        "reason": entry.reason,
        "policy_id": entry.policy_id,
        "timestamp": entry.timestamp,
        "event_type": entry.event_type,
    }
