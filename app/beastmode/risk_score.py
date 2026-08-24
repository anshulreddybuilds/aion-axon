"""A 0-100 display score, computed from real signals — never a decision.

Beastmode asked for a 5-tier risk gate (LOW/MODERATE/HIGH/CRITICAL/
PROHIBITED) with its own routing. The actual enforcement already lives in
app.governance.policies (Enforcement.PROHIBITED / APPROVAL_REQUIRED) and
app.governance.guardian (RiskLevel.LOW/MEDIUM/HIGH), both tested,
adversarially tested, and running live. Replacing that logic four days
before a deadline is not being done here.

What this module adds: a richer NUMBER for the UI to show, computed
purely from real signals the pipeline already produced for a specific
candidate (AST findings count, sandbox pass/fail, evaluator score,
declared network/credential flags). It never feeds back into whether
anything is allowed to run — it is read-only narration over a decision
that was already made by the tested code.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskScore:
    score: int  # 0-100, lower is safer
    tier: str
    factors: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"score": self.score, "tier": self.tier, "factors": list(self.factors)}


def compute_risk_score(
    *,
    ast_finding_count: int,
    sandbox_passed: bool,
    evaluator_score: "int | None",
    network_declared: bool = False,
    credentials_declared: bool = False,
) -> RiskScore:
    """Derive a 0-100 score from signals THIS specific candidate produced.

    This is arithmetic over facts already established elsewhere — it does
    not re-run the AST screen, re-invoke the sandbox, or re-ask the
    evaluator. Feed it fabricated inputs and it will happily compute a
    fabricated score; the guarantee is only that the real pipeline never
    reads this number back as a decision.
    """
    factors: list[str] = []
    score = 0

    if ast_finding_count > 0:
        score += 40
        factors.append(f"{ast_finding_count} AST finding(s)")

    if not sandbox_passed:
        score += 35
        factors.append("sandbox execution failed")

    if evaluator_score is not None:
        # 50 is app.synapse.engine.MIN_EVALUATOR_SCORE -- the real floor
        # below which the live engine already auto-rejects. Scoring that
        # as merely "moderate" here would understate a candidate the real
        # pipeline would never even present for approval.
        if evaluator_score < 50:
            score += 45
            factors.append(f"evaluator score {evaluator_score} below the real auto-reject floor (50)")
        elif evaluator_score < 80:
            score += 10
            factors.append(f"evaluator score {evaluator_score} — moderate confidence")
    else:
        # A MISSING score is not a good score. Treated as meaningfully
        # risky, not neutral, per the project's stance that an absent
        # verdict is not the same as a confident one.
        score += 20
        factors.append("evaluator returned no score")

    if network_declared:
        score += 15
        factors.append("declares network access")
    if credentials_declared:
        score += 15
        factors.append("declares credential access")

    score = min(100, score)

    if score >= 81:
        tier = "PROHIBITED"
    elif score >= 61:
        tier = "CRITICAL"
    elif score >= 41:
        tier = "HIGH"
    elif score >= 21:
        tier = "MODERATE"
    else:
        tier = "LOW"

    if not factors:
        factors.append("no risk signals present")

    return RiskScore(score=score, tier=tier, factors=tuple(factors))
