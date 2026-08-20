"""The Guardian policy catalog — deny-by-default, with citable IDs.

Every refusal AION Axon issues cites a policy by ID. "The agent said no"
is an opinion; "the agent refused under G-04" is a decision a human can
audit, appeal, and hold the system to.

Two properties matter more than the rule list itself:

1. PROHIBITED policies cannot be satisfied by approval. There is no
   argument, no override, and no risk level that converts a PROHIBITED
   action into an allowed one. If approval could unlock it, it would not
   be a prohibition -- it would be a permission.

2. G-06 makes the override attempt itself a refusal. A guardrail that can
   be talked out of is a suggestion.

KNOWN LIMITATION: matching is LEXICAL, not semantic. It matches phrasing,
not intent, so a sufficiently novel wording of a prohibited request can
miss. This is why the policy catalog is a layer on top of the gate and
not a replacement for it -- the gate still requires approval for anything
with an external effect, so a missed match degrades to "a human is asked"
rather than "anything runs". Semantic classification is §12 backlog.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Enforcement(str, Enum):
    PROHIBITED = "PROHIBITED"
    """Never allowed. Approval cannot unlock it."""

    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    """Allowed only with explicit human approval."""


@dataclass(frozen=True)
class Policy:
    policy_id: str
    title: str
    enforcement: Enforcement
    rationale: str
    triggers: tuple[str, ...] = field(default_factory=tuple)

    def matches(self, text: str) -> bool:
        lowered = text.lower()
        return any(trigger in lowered for trigger in self.triggers)


# Ordered by precedence. The FIRST match wins, so prohibitions are listed
# before approval rules -- otherwise "send the credentials by email" could
# match the email rule and be downgraded to merely needing approval.
POLICY_CATALOG: tuple[Policy, ...] = (
    Policy(
        policy_id="G-06",
        title="guardian-override-prohibited",
        enforcement=Enforcement.PROHIBITED,
        rationale=(
            "The Guardian cannot be disabled, bypassed, or overridden by "
            "instruction. A control that can be argued away is not a "
            "control."
        ),
        triggers=(
            "override the guardian",
            "override guardian",
            "bypass the guardian",
            "bypass guardian",
            "disable the guardian",
            "disable guardian",
            "ignore the policy",
            "ignore policy",
            "ignore your rules",
            "disable the kill switch",
            "disable kill switch",
            "turn off the kill switch",
            "skip approval",
            "without approval",
            "bypass approval",
        ),
    ),
    Policy(
        policy_id="G-04",
        title="credential-access-prohibited",
        enforcement=Enforcement.PROHIBITED,
        rationale=(
            "AION Axon must never read, print, exfiltrate, or acquire a "
            "capability that accesses credentials, secrets, API keys, or "
            "tokens. Troubleshooting is not a justification: a capability "
            "that can read secrets can leak them, and the sandbox holds "
            "no credentials precisely so that generated code cannot."
        ),
        triggers=(
            "credential",
            "secret",
            "api key",
            "api_key",
            "access token",
            "auth token",
            "password",
            "private key",
            "service account key",
            "environment variable",
            "env var",
            ".env",
        ),
    ),
    Policy(
        policy_id="G-05",
        title="security-control-modification-prohibited",
        enforcement=Enforcement.PROHIBITED,
        rationale=(
            "IAM roles, firewall rules, audit logging, and the policy "
            "catalog itself are outside the agent's reach. An agent that "
            "can widen its own permissions has no permissions boundary."
        ),
        triggers=(
            "iam policy",
            "iam role",
            "grant myself",
            "grant itself",
            "escalate privilege",
            "firewall rule",
            "disable audit",
            "delete audit",
            "modify the policy catalog",
            "edit the policy catalog",
        ),
    ),
    Policy(
        policy_id="G-01",
        title="destructive-operations-prohibited",
        enforcement=Enforcement.PROHIBITED,
        rationale=(
            "Irreversible destruction is never delegated. Deletion is "
            "the one action no audit trail can undo."
        ),
        triggers=(
            "delete the database",
            "drop table",
            "drop the table",
            "rm -rf",
            "format the disk",
            "wipe the",
            "destroy the",
            "purge all",
            "delete all records",
        ),
    ),
    Policy(
        policy_id="G-02",
        title="financial-transactions-require-approval",
        enforcement=Enforcement.APPROVAL_REQUIRED,
        rationale=(
            "Anything that spends money requires a named human decision "
            "recorded against it."
        ),
        # Triggers are VERB PHRASES, not nouns. A bare "invoice" matched
        # "calculate the invoice total with tax" -- step 1 of the demo
        # mission -- and would have interrupted a harmless calculation
        # with an approval prompt. Reading a financial document is not a
        # financial transaction; paying one is.
        triggers=(
            "purchase",
            "buy ",
            "pay the",
            "make a payment",
            "process the payment",
            "transfer funds",
            "issue a refund",
            "charge the card",
            "checkout",
        ),
    ),
    Policy(
        policy_id="G-03",
        title="external-communication-requires-approval",
        enforcement=Enforcement.APPROVAL_REQUIRED,
        rationale=(
            "Messages sent on the owner's behalf cannot be unsent, so "
            "they need approval before they leave."
        ),
        triggers=(
            "send an email",
            "send email",
            "send a message",
            "post to",
            "publish to",
            "tweet",
            "notify the customer",
            "reply to",
        ),
    ),
)

# Applied programmatically by the Guardian from the Autonomy Ledger, not
# by text matching, so it carries no triggers and is not in POLICY_CATALOG.
# It still lives here so that every citable ID has exactly one definition —
# a citation pointing at a policy nobody can look up is not accountability.
AUTONOMY_SUPERVISION_POLICY = Policy(
    policy_id="G-07",
    title="autonomy-below-supervision-threshold",
    enforcement=Enforcement.APPROVAL_REQUIRED,
    rationale=(
        "A capability whose autonomy has fallen below the supervision "
        "threshold requires human verification, including for work it was "
        "previously trusted to do alone. Demotion without consequence is "
        "decoration."
    ),
)

POLICY_BY_ID = {
    **{policy.policy_id: policy for policy in POLICY_CATALOG},
    AUTONOMY_SUPERVISION_POLICY.policy_id: AUTONOMY_SUPERVISION_POLICY,
}


def find_policy(*texts: Optional[str]) -> Optional[Policy]:
    """Return the highest-precedence policy matching any given text.

    Several fields are checked together -- the action label, the step
    description, the capability name -- because a request often hides its
    real intent in the description rather than the action label.
    """
    candidates = [text for text in texts if text]

    for policy in POLICY_CATALOG:
        for text in candidates:
            if policy.matches(text):
                return policy

    return None


def citation(policy: Policy) -> str:
    return f"{policy.policy_id}: {policy.title}"
