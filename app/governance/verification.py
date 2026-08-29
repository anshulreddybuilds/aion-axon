"""The single point where a tool's claim is checked and scored.

Placed on its own so there is exactly ONE place this happens. It sits in
the orchestrator, which every mission path passes through -- when it lived
in the planned-mission engine, the direct mission path executed research
and moved no autonomy at all.

Scoped to web_research per Amendment 7 P0.
"""
from typing import Any, Optional

from app.governance.autonomy_ledger import autonomy_ledger
from app.governance.evidence_engine import VERIFIED_VERDICT, verify_research
from app.governance.ground_truth import lookup

VERIFIABLE_CAPABILITIES = ("web_research",)


def verify_outcome(
    tool_name: Optional[str],
    result: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Check an executed step's claim, score it, attach the evidence.

    Mutates `result` to carry an "evidence" block so callers downstream
    render the same verdict rather than recomputing it -- recomputing
    would record the outcome twice and move autonomy twice for one action.

    Returns None when the step is not verifiable. Never raises: a
    verification failure must not fail a step that genuinely ran. What
    changes is how much the agent is trusted next time, not whether the
    work happened.
    """
    if tool_name not in VERIFIABLE_CAPABILITIES:
        return None

    if not isinstance(result, dict) or result.get("status") != "EXECUTED":
        return None

    payload = result.get("result")

    if not isinstance(payload, dict):
        return None

    # Check the claim against an INDEPENDENTLY RECORDED fact when one
    # clearly applies. Without this the Evidence Engine can only ask "does
    # this answer look well-formed", which a confident wrong answer passes
    # easily. lookup() returns None on a weak match on purpose: a
    # loosely-related fact would manufacture a contradiction and demote a
    # capability that was actually right.
    fact = lookup(payload.get("query") or "")

    try:
        report = verify_research(
            payload,
            ground_truth=fact.value if fact and not fact.stale else None,
        )

        change = autonomy_ledger.record_outcome(
            tool_name,
            verified=report.verdict == VERIFIED_VERDICT,
            reason=(
                report.contradiction_detail
                or f"Evidence verdict: {report.verdict}"
            ),
        )

        evidence = {
            "verdict": report.verdict,
            "ground_truth": (
                {
                    "key": fact.key,
                    "value": fact.value,
                    "source": fact.source,
                    "recorded_by": fact.recorded_by,
                    "age_days": fact.age_days,
                    "stale": fact.stale,
                }
                if fact else None
            ),
            "confidence": report.confidence,
            "checklist": report.checklist,
            "grounded": report.grounded,
            "source_count": report.source_count,
            "autonomy_before": change.before,
            "autonomy_after": change.after,
            "demoted": change.demoted,
            "oversight_restored": change.oversight_restored,
        }
    except Exception as error:  # noqa: BLE001 - never fail a real step
        evidence = {"verdict": "UNVERIFIED", "error": str(error)}

    result["evidence"] = evidence

    return evidence
