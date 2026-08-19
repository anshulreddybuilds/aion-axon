from dataclasses import dataclass
from enum import Enum


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


class Guardian:
    """
    AION AXON safety gate.

    The Guardian decides whether an intended action can execute,
    must wait for human approval, or must be refused.
    """

    def evaluate(self, action: str, risk: RiskLevel) -> GuardianDecision:
        if risk == RiskLevel.HIGH:
            return GuardianDecision(
                decision=Decision.REFUSE,
                risk=risk,
                reason="Guardian refused a high-risk action."
            )

        if risk == RiskLevel.MEDIUM:
            return GuardianDecision(
                decision=Decision.APPROVAL_REQUIRED,
                risk=risk,
                reason="Human approval is required before execution."
            )

        return GuardianDecision(
            decision=Decision.ALLOW,
            risk=risk,
            reason="Action is within the low-risk execution boundary."
        )


guardian = Guardian()
