"""Autonomy Ledger — earned trust, and trust that can be taken back.

Most agents treat autonomy as a setting a human chooses once. Here it is a
BALANCE the agent earns through verified outcomes and loses when reality
disagrees with its own success claims.

The direction that matters is DOWN. An agent that only ever gains autonomy
has a ratchet, not a ledger, and a ratchet cannot respond to evidence that
it is wrong.

Fields live on the existing `capabilities/{id}` documents rather than in a
new collection, per Amendment 7 P0 -- extend, do not rebuild.

Below `SUPERVISION_THRESHOLD` the Guardian requires human verification for
that capability even when the action would otherwise be permitted. That is
the whole point: demotion has a consequence, or it is just a number on a
dashboard.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from app.memory.firestore_store import firestore_store

STARTING_AUTONOMY = 32.0
PROMOTION_DELTA = 15.0
DEMOTION_DELTA = 18.0

MIN_AUTONOMY = 0.0
MAX_AUTONOMY = 95.0

# Never 100. A capability that needs no oversight ever is a claim no
# evidence can support.
SUPERVISION_THRESHOLD = 40.0

# Demotion is larger than promotion on purpose: trust should be slower to
# earn than to lose. Symmetric deltas would let a capability alternate
# between right and wrong forever while drifting upward.


@dataclass
class AutonomyChange:
    capability: str
    before: float
    after: float
    delta: float
    reason: str
    supervised_before: bool
    supervised_after: bool
    changed_at: str

    @property
    def demoted(self) -> bool:
        return self.after < self.before

    @property
    def oversight_restored(self) -> bool:
        """The demo's headline moment: autonomy fell far enough to matter."""
        return self.supervised_after and not self.supervised_before

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "autonomy_before": self.before,
            "autonomy_after": self.after,
            "delta": self.delta,
            "reason": self.reason,
            "demoted": self.demoted,
            "oversight_restored": self.oversight_restored,
            "changed_at": self.changed_at,
        }


class AutonomyLedger:

    def record(self, capability: str, data: dict[str, Any]) -> None:
        firestore_store.save_capability(capability, data)

    def tracked(self, capability: str) -> Optional[dict[str, Any]]:
        """The ledger record, or None if this capability is not tracked.

        Deliberately does NOT create a record. The ledger governs
        capabilities it has evidence about -- chiefly ones SYNAPSE
        acquired. Hand-built seed capabilities were reviewed by a human
        before they ever shipped and are trusted until evidence says
        otherwise.
        """
        return firestore_store.get_capability(capability)

    def get(self, capability: str) -> dict[str, Any]:
        record = firestore_store.get_capability(capability)

        if record is None:
            record = {
                "name": capability,
                "autonomy_pct": STARTING_AUTONOMY,
                "success_rate": 0.0,
                "intervention_rate": 0.0,
                "verified_successes": 0,
                "contradictions": 0,
                "total_outcomes": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            firestore_store.save_capability(capability, record)

        return record

    def autonomy_of(self, capability: str) -> float:
        return float(self.get(capability).get("autonomy_pct",
                                              STARTING_AUTONOMY))

    def requires_supervision(self, capability: Optional[str]) -> bool:
        """True only for a TRACKED capability that has fallen below the bar.

        An untracked capability is not supervised. Treating "no record" as
        "no trust" would have put every seed capability below the
        threshold on day one and forced an approval prompt for basic
        arithmetic -- which is how a governance feature turns into a
        governance theatre nobody reads.
        """
        if not capability:
            return False

        record = self.tracked(capability)

        if record is None:
            return False

        autonomy = float(record.get("autonomy_pct", STARTING_AUTONOMY))

        return autonomy < SUPERVISION_THRESHOLD

    def record_outcome(
        self,
        capability: str,
        verified: bool,
        reason: str,
        intervened: bool = False,
    ) -> AutonomyChange:
        """Move a capability's autonomy on the strength of real evidence.

        `verified` must come from the Evidence Engine, never from the
        agent's own status field -- that is the entire distinction this
        module exists to enforce.
        """
        record = self.get(capability)

        before = float(record.get("autonomy_pct", STARTING_AUTONOMY))
        supervised_before = before < SUPERVISION_THRESHOLD

        delta = PROMOTION_DELTA if verified else -DEMOTION_DELTA
        after = max(MIN_AUTONOMY, min(MAX_AUTONOMY, before + delta))

        total = int(record.get("total_outcomes", 0)) + 1
        successes = int(record.get("verified_successes", 0)) + int(verified)
        contradictions = (
            int(record.get("contradictions", 0)) + int(not verified)
        )
        interventions = (
            int(record.get("interventions", 0)) + int(intervened)
        )

        updated = {
            "name": capability,
            "autonomy_pct": round(after, 1),
            "total_outcomes": total,
            "verified_successes": successes,
            "contradictions": contradictions,
            "interventions": interventions,
            "success_rate": round(successes / total, 3),
            "intervention_rate": round(interventions / total, 3),
            "last_outcome_reason": reason,
            "last_outcome_verified": verified,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

        firestore_store.save_capability(capability, updated)

        change = AutonomyChange(
            capability=capability,
            before=round(before, 1),
            after=round(after, 1),
            delta=round(after - before, 1),
            reason=reason,
            supervised_before=supervised_before,
            supervised_after=after < SUPERVISION_THRESHOLD,
            changed_at=datetime.now(timezone.utc).isoformat(),
        )

        firestore_store.write_audit_event(
            "AUTONOMY_DEMOTED" if change.demoted else "AUTONOMY_PROMOTED",
            change.to_dict(),
        )

        return change


autonomy_ledger = AutonomyLedger()
