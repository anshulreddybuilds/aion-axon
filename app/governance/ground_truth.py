"""Independently recorded facts the agent's claims are checked against.

The Evidence Engine can detect a contradiction, but only if something
independent says what the truth is. That "something" must not come from
the agent, or the check is the agent grading its own homework.

So ground truth is **recorded by a human, with provenance**: who recorded
it, when, and the source they took it from. That is how an evaluation set
works, and it is auditable after the fact — a demotion can always be
traced back to the specific recorded fact that caused it.

Two properties this module is careful about:

1. **Silence beats a guess.** A fact is only applied when it clearly
   matches the query. A loose match would produce FALSE contradictions and
   demote a capability that was right, which is worse than missing a real
   contradiction — an agent punished for being correct learns nothing
   useful, and the ledger stops meaning anything.

2. **Ground truth can go stale.** A recorded fact carries its date, and a
   stale fact is reported as stale rather than silently trusted. "The rate
   was 83.2 in August" is not evidence about December.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.memory.firestore_store import firestore_store

# A fact is applied only when the query covers BOTH a minimum number of
# its keywords AND a minimum PROPORTION of them.
#
# Absolute overlap alone is not enough: "exchange students in August"
# shares two words with "USD to INR exchange rate August 2026" and would
# have been checked against the exchange rate. Proportion is what
# distinguishes a query that is about the fact from one that merely brushes
# past it -- that phrase covers 2 of 5 keywords (40%), while "USD to INR
# exchange rate" covers 3 of 5 (60%).
#
# Tuned to fail SILENT rather than fail LOUD: a false contradiction demotes
# a capability that was right, and an agent punished for being correct
# makes the whole ledger meaningless.
MIN_KEYWORD_OVERLAP = 2
MIN_KEYWORD_COVERAGE = 0.6

STALE_AFTER_DAYS = 90

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "in", "on",
    "for", "and", "or", "what", "how", "much", "many", "current", "today",
    "now", "value", "rate", "price",
}


@dataclass
class GroundTruth:
    key: str
    statement: str
    value: str
    source: str
    recorded_by: str
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "statement": self.statement,
            "value": self.value,
            "source": self.source,
            "recorded_by": self.recorded_by,
            "recorded_at": self.recorded_at,
        }

    @property
    def age_days(self) -> float:
        try:
            recorded = datetime.fromisoformat(self.recorded_at)
        except (TypeError, ValueError):
            return 0.0

        if recorded.tzinfo is None:
            recorded = recorded.replace(tzinfo=timezone.utc)

        return (datetime.now(timezone.utc) - recorded).days

    @property
    def stale(self) -> bool:
        return self.age_days > STALE_AFTER_DAYS


def _keywords(text: str) -> set[str]:
    return {
        word.strip(".,?!:;()").lower()
        for word in (text or "").split()
        if len(word) > 2 and word.strip(".,?!:;()").lower() not in STOPWORDS
    }


def record_fact(
    key: str,
    statement: str,
    value: str,
    source: str,
    recorded_by: str,
) -> dict[str, Any]:
    """Record a fact. Requires a source -- provenance is not optional.

    A fact with no source is an opinion, and an opinion that can demote a
    capability is just an unaccountable veto.
    """
    if not source or not source.strip():
        return {
            "status": "REJECTED",
            "error": (
                "Ground truth requires a source. A fact with no provenance "
                "cannot be audited, and an unauditable fact must not be "
                "able to demote a capability."
            ),
        }

    fact = GroundTruth(
        key=key,
        statement=statement,
        value=value,
        source=source.strip(),
        recorded_by=recorded_by,
    )

    firestore_store.save_ground_truth(key, fact.to_dict())

    firestore_store.write_audit_event("GROUND_TRUTH_RECORDED", {
        "key": key,
        "value": value,
        "source": fact.source,
        "recorded_by": recorded_by,
    })

    return {"status": "RECORDED", "fact": fact.to_dict()}


def all_facts() -> list[GroundTruth]:
    return [GroundTruth(**f) for f in firestore_store.list_ground_truth()]


def lookup(query: str) -> Optional[GroundTruth]:
    """Find the fact that applies to this query, or None.

    Returns None on a weak match on purpose. Applying a loosely-related
    fact would manufacture a contradiction and demote a capability that
    was actually right.
    """
    query_words = _keywords(query)

    if not query_words:
        return None

    best: Optional[GroundTruth] = None
    best_score = 0.0

    for fact in all_facts():
        fact_words = _keywords(fact.statement)

        if not fact_words:
            continue

        overlap = len(query_words & fact_words)
        coverage = overlap / len(fact_words)

        if overlap < MIN_KEYWORD_OVERLAP or coverage < MIN_KEYWORD_COVERAGE:
            continue

        if coverage > best_score:
            best, best_score = fact, coverage

    return best
