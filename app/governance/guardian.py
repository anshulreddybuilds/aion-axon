from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.governance.policies import (
    Enforcement,
    Policy,
    citation,
    find_policy,
)


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Decision(str, Enum):
    ALLOW = "ALLOW"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    REFUSE = "REFUSE"


@dataclass
class GuardianDecision:
    decision: Decision
    risk: RiskLevel
    reason: str
    policy_id: Optional[str] = None
    policy_title: Optional[str] = None
    rationale: Optional[str] = None


class Guardian:
    """AION Axon safety gate — deny-by-default, with citable policy IDs.

    Order of evaluation matters:

    1. The policy catalog is consulted FIRST. A PROHIBITED policy refuses
       outright, and no risk level, argument, or approval can unlock it.
    2. HIGH risk refuses by default. Deny-by-default means an action must
       earn its way to execution, not merely fail to look dangerous.
    3. Everything else falls back to the risk tiers.

    A refusal always carries a citation, so it can be audited and appealed
    rather than merely obeyed.
    """

    def evaluate(
        self,
        action: str,
        risk: RiskLevel,
        description: Optional[str] = None,
        capability: Optional[str] = None,
    ) -> GuardianDecision:

        policy = find_policy(action, description, capability)

        if policy is not None:
            return self._from_policy(policy, risk)

        if risk == RiskLevel.HIGH:
            return GuardianDecision(
                decision=Decision.REFUSE,
                risk=risk,
                reason=(
                    "Guardian refused a high-risk action. Deny-by-default "
                    "applies when no policy explicitly permits it."
                ),
            )

        if risk == RiskLevel.MEDIUM:
            return GuardianDecision(
                decision=Decision.APPROVAL_REQUIRED,
                risk=risk,
                reason="Human approval is required before execution.",
            )

        return GuardianDecision(
            decision=Decision.ALLOW,
            risk=risk,
            reason="Action is within the low-risk execution boundary.",
        )

    def _from_policy(
        self,
        policy: Policy,
        risk: RiskLevel,
    ) -> GuardianDecision:

        if policy.enforcement == Enforcement.PROHIBITED:
            return GuardianDecision(
                decision=Decision.REFUSE,
                risk=risk,
                reason=(
                    f"Guardian refused under policy {citation(policy)}. "
                    f"{policy.rationale}"
                ),
                policy_id=policy.policy_id,
                policy_title=policy.title,
                rationale=policy.rationale,
            )

        # An APPROVAL_REQUIRED policy can raise the bar but never lower it:
        # a LOW-risk label on a payment does not make it allowed.
        return GuardianDecision(
            decision=Decision.APPROVAL_REQUIRED,
            risk=risk,
            reason=(
                f"Human approval is required under policy "
                f"{citation(policy)}. {policy.rationale}"
            ),
            policy_id=policy.policy_id,
            policy_title=policy.title,
            rationale=policy.rationale,
        )


guardian = Guardian()
