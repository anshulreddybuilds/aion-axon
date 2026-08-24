"""The memory-informed planner -- the bridge between historical evidence
and what SYNAPSE is about to attempt.

Reads app.beastmode.memory.recommend() and turns it into an explicit,
inspectable plan: what AION intends to do and why, before anything is
generated, screened, sandboxed, evaluated or approved.

INVARIANT (tested in tests/test_planner.py): this module is a pure
function of its inputs. It calls nothing, writes nothing, approves
nothing, installs nothing. A plan is a recommendation for the caller to
act on -- typically by calling synapse.propose(), which runs its own
full, unshortened pipeline regardless of what the plan says. Memory
informed the plan; the plan does not authorize anything the tested
pipeline wouldn't already require.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.beastmode.memory import Recommendation, recommend

# The checks every FRESH acquisition still goes through, regardless of
# what memory recommends -- named here so a plan can state them
# explicitly rather than a judge having to trust that they still apply.
_FRESH_ACQUISITION_CHECKS = (
    "GUARDIAN_PRESCREEN", "AST_SCREEN", "SANDBOX", "EVALUATOR",
    "GUARDIAN_SCREEN", "HUMAN_APPROVAL",
)

# Reusing an installed capability still means re-confirming it against
# the CURRENT state of these -- never a bare "it worked before".
_REUSE_CHECKS = (
    "CURRENT_CONTRACT_CHECK", "CURRENT_QUARANTINE_STATUS",
)


@dataclass
class Plan:
    decision: str  # REUSE_EXISTING_CAPABILITY | ACQUIRE_NEW | ESCALATE
    reason: str
    memory: Recommendation
    required_checks: tuple[str, ...]
    capability: str | None = None
    strategy: str | None = None          # GENERATE_WITH_RETRY | GENERATE_SINGLE_ATTEMPT
    planned_attempts: int | None = None
    previous_failure: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "capability": self.capability,
            "strategy": self.strategy,
            "planned_attempts": self.planned_attempts,
            "previous_failure": self.previous_failure,
            "required_checks": list(self.required_checks),
            "memory": self.memory.to_dict(),
            "authorization_note": (
                "This plan is advisory. It selects a STRATEGY, not a "
                "decision to install anything. Every required check "
                "listed above still runs for real; approving or "
                "rejecting the resulting proposal remains a separate, "
                "human action at /approvals/{id}/decide."
            ),
        }


def _detect_retry_recovery(history) -> str | None:
    """Real evidence, not a guess: did this exact capability name fail a
    sandbox test at some point and LATER reach AWAITING_APPROVAL? If so,
    that is direct proof retry-with-feedback recovered it before -- the
    plan should say so and propose the same bounded strategy again.
    Returns the failure reason if found, else None.
    """
    failure_reason = None
    for attempt in history:
        if attempt.status in ("REJECTED", "FAILED", "BLOCKED") and attempt.stage == "SANDBOX_TEST":
            failure_reason = attempt.reason
        elif attempt.status == "AWAITING_APPROVAL" and failure_reason:
            return failure_reason
    return None


def plan(
    need: str,
    capabilities: list[dict[str, Any]],
    audit_events: list[dict[str, Any]],
) -> Plan:
    """Produce an explicit plan for `need`, informed by real memory."""
    memory = recommend(need, capabilities, audit_events)

    if memory.recommendation == "REUSE_EXISTING_CAPABILITY":
        top = memory.matches[0]
        return Plan(
            decision="REUSE_EXISTING_CAPABILITY",
            reason=memory.reason,
            memory=memory,
            capability=top.name,
            required_checks=_REUSE_CHECKS,
        )

    if memory.recommendation in ("DO_NOT_REUSE", "ESCALATE"):
        return Plan(
            decision="ESCALATE",
            reason=memory.reason,
            memory=memory,
            required_checks=(),
        )

    # ACQUIRE_NEW: decide the generation strategy from real history.
    prior_failure = _detect_retry_recovery(memory.history)

    if prior_failure:
        return Plan(
            decision="ACQUIRE_NEW",
            reason=(
                f"{memory.reason} A prior sandbox failure for this exact "
                f"capability name was later followed by a successful "
                f"AWAITING_APPROVAL outcome -- retry-with-feedback "
                f"recovered it before, so the same bounded strategy is "
                f"planned again."
            ),
            memory=memory,
            strategy="GENERATE_WITH_RETRY",
            planned_attempts=2,
            previous_failure=prior_failure,
            required_checks=_FRESH_ACQUISITION_CHECKS,
        )

    return Plan(
        decision="ACQUIRE_NEW",
        reason=memory.reason,
        memory=memory,
        strategy="GENERATE_SINGLE_ATTEMPT",
        planned_attempts=1,
        required_checks=_FRESH_ACQUISITION_CHECKS,
    )
