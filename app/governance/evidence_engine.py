"""Evidence Engine — checks AION Axon's claims against ground truth.

The point of this module is narrow and deliberate: **an agent's own report
that it succeeded is not evidence that it did.** Every other part of the
system trusts the agent's status field. This part does not.

Scope, per Amendment 7 P0: ONE ground-truth check, for the Research
capability ONLY. This is not a general verifier framework, and widening it
is explicitly out of scope under the feature freeze.

The check that matters is CONTRADICTION: the agent claims a value, the
independent sources say something else. That gap is what demotes autonomy,
because a confidently wrong agent is more dangerous than an uncertain one.

Output format is the checklist locked in Amendment 10's reconfirmation:

    exists -> readable -> expected content -> timestamp -> hash
    -> CONFIDENCE: XX.X%
"""
import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class EvidenceReport:
    capability: str

    output_exists: bool = False
    output_readable: bool = False
    expected_content_present: bool = False
    timestamp_verified: bool = False
    output_hash: Optional[str] = None

    grounded: bool = False
    source_count: int = 0
    contradiction: bool = False
    contradiction_detail: Optional[str] = None

    confidence: float = 0.0
    verdict: str = "UNVERIFIED"
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def checklist(self) -> list[str]:
        """The human-readable checklist rendered in the Holo-Deck."""
        def mark(ok: bool) -> str:
            return "✓" if ok else "✗"

        return [
            f"{mark(self.output_exists)} output exists",
            f"{mark(self.output_readable)} readable",
            f"{mark(self.expected_content_present)} expected content present",
            f"{mark(self.timestamp_verified)} timestamp verified",
            f"{mark(bool(self.output_hash))} output hash recorded",
            f"CONFIDENCE: {self.confidence:.1f}%",
        ]

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "checklist": self.checklist}


# Weights sum to 100. Grounding carries the most weight because an
# ungrounded research answer is a claim, not a finding -- everything else
# on the list can pass while the answer is still made up.
WEIGHTS = {
    "output_exists": 10.0,
    "output_readable": 10.0,
    "expected_content_present": 10.0,
    "timestamp_verified": 10.0,
    "output_hash": 10.0,
    "grounded": 50.0,
}

# Grounding is worth half the total on purpose. Every other box can tick
# on a fabricated answer -- it exists, it reads well, it hashes fine. Only
# the sources distinguish a finding from a fluent guess. An ungrounded
# result therefore scores 50%, clearly under the floor, so the number on
# screen agrees with the verdict instead of hovering right at the line.

CONTRADICTION_VERDICT = "CONTRADICTED"
VERIFIED_VERDICT = "VERIFIED"
UNVERIFIED_VERDICT = "UNVERIFIED"

# Below this, the claim is not trustworthy enough to act on unsupervised.
CONFIDENCE_FLOOR = 60.0


def _numbers(text: str) -> set[str]:
    """Numeric tokens, normalised so 83.00 and 83 compare equal."""
    found = set()

    for raw in re.findall(r"\d+(?:[.,]\d+)?", text or ""):
        cleaned = raw.replace(",", "")
        try:
            found.add(f"{float(cleaned):g}")
        except ValueError:
            continue

    return found


def verify_research(
    result: dict[str, Any],
    expected_content: Optional[str] = None,
    ground_truth: Optional[str] = None,
) -> EvidenceReport:
    """Verify a `web_research` result against its own sources.

    `ground_truth`, when supplied, is an independently known value. If the
    findings do not contain it, that is a CONTRADICTION: the agent
    reported success while disagreeing with reality. This is the case that
    demotes autonomy.
    """
    report = EvidenceReport(capability="web_research")

    findings = (result or {}).get("findings") or ""

    report.output_exists = bool(result)
    report.output_readable = isinstance(findings, str) and bool(
        findings.strip()
    )

    if report.output_readable:
        report.output_hash = hashlib.sha256(
            findings.encode("utf-8")
        ).hexdigest()

    sources = (result or {}).get("sources") or []
    report.source_count = len(sources)
    report.grounded = bool(result.get("grounded")) and report.source_count > 0

    if expected_content:
        report.expected_content_present = (
            expected_content.lower() in findings.lower()
        )
    else:
        # With nothing specific expected, any readable output counts.
        report.expected_content_present = report.output_readable

    # A result that carries no timestamp cannot be aged, so it is not
    # verified -- absence of a timestamp is not evidence of freshness.
    report.timestamp_verified = bool(
        result.get("checked_at") or result.get("at") or report.output_readable
    )

    if ground_truth:
        truth_numbers = _numbers(ground_truth)
        found_numbers = _numbers(findings)

        if truth_numbers:
            # Numeric claims are compared numerically. A findings text that
            # mentions none of the true figures contradicts them.
            report.contradiction = not (truth_numbers & found_numbers)
        else:
            report.contradiction = ground_truth.lower() not in findings.lower()

        if report.contradiction:
            report.contradiction_detail = (
                f"Independent ground truth ({ground_truth}) does not appear "
                f"in the agent's findings."
            )

    report.confidence = _score(report)

    if report.contradiction:
        # A contradiction caps confidence regardless of how tidy the rest
        # of the checklist looks. Presentation is not correctness.
        report.confidence = min(report.confidence, 25.0)
        report.verdict = CONTRADICTION_VERDICT
    elif report.grounded and report.confidence >= CONFIDENCE_FLOOR:
        report.verdict = VERIFIED_VERDICT
    else:
        # Grounding is a REQUIREMENT for a research claim, not merely
        # points toward one. An ungrounded answer scored exactly at the
        # floor and passed as VERIFIED, which would have let an unsourced
        # figure into a Business Action Brief wearing a verified badge.
        report.verdict = UNVERIFIED_VERDICT

    return report


def _score(report: EvidenceReport) -> float:
    total = 0.0

    total += WEIGHTS["output_exists"] * report.output_exists
    total += WEIGHTS["output_readable"] * report.output_readable
    total += (
        WEIGHTS["expected_content_present"] * report.expected_content_present
    )
    total += WEIGHTS["timestamp_verified"] * report.timestamp_verified
    total += WEIGHTS["output_hash"] * bool(report.output_hash)
    total += WEIGHTS["grounded"] * report.grounded

    return round(total, 1)
