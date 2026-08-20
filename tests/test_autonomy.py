"""Evidence Engine + Autonomy Ledger — Amendment 7 P0.

The behaviour under test is the one the demo is built on: autonomy that
goes DOWN when reality disagrees with the agent's own success claim, and
a demotion that actually changes what the agent is allowed to do.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

import pytest  # noqa: E402

from app.governance import autonomy_ledger as ledger_module  # noqa: E402
from app.governance.autonomy_ledger import (  # noqa: E402
    PROMOTION_DELTA,
    STARTING_AUTONOMY,
    SUPERVISION_THRESHOLD,
    autonomy_ledger,
)
from app.governance.evidence_engine import (  # noqa: E402
    CONTRADICTION_VERDICT,
    VERIFIED_VERDICT,
    verify_research,
)
from app.governance.guardian import Decision, RiskLevel, guardian  # noqa: E402
from app.memory.firestore_store import firestore_store  # noqa: E402


@pytest.fixture(autouse=True)
def clean_ledger():
    firestore_store.capabilities.clear()
    yield
    firestore_store.capabilities.clear()


def grounded_result(findings: str, sources: int = 2) -> dict:
    return {
        "status": "SUCCESS",
        "findings": findings,
        "grounded": True,
        "sources": [
            {"title": f"src{i}", "uri": f"https://example.com/{i}"}
            for i in range(sources)
        ],
        "source_count": sources,
    }


# --- Evidence Engine ------------------------------------------------------

def test_grounded_result_verifies_with_high_confidence():
    report = verify_research(grounded_result("USD to INR is 83.2 today."))

    assert report.verdict == VERIFIED_VERDICT
    assert report.confidence >= 60.0
    assert report.output_hash
    assert report.grounded


def test_ungrounded_result_is_not_verified():
    """A confident answer with no sources is a claim, not a finding."""
    result = {
        "status": "DEGRADED",
        "findings": "I reckon it is about 83.",
        "grounded": False,
        "sources": [],
    }

    report = verify_research(result)

    assert report.verdict != VERIFIED_VERDICT
    assert report.grounded is False
    # Grounding alone is 40 points; losing it must drop below the floor.
    assert report.confidence < 60.0


def test_contradiction_is_detected_against_ground_truth():
    """The demo beat: the agent is confidently wrong."""
    report = verify_research(
        grounded_result("The USD to INR rate is 12.0."),
        ground_truth="83.2",
    )

    assert report.contradiction is True
    assert report.verdict == CONTRADICTION_VERDICT
    assert "83.2" in report.contradiction_detail


def test_contradiction_caps_confidence_however_tidy_the_rest_looks():
    """Every other box can tick and the answer still be wrong."""
    report = verify_research(
        grounded_result("The rate is 12.0.", sources=5),
        ground_truth="83.2",
    )

    assert report.output_exists
    assert report.output_readable
    assert report.grounded
    assert report.output_hash
    assert report.confidence <= 25.0


def test_matching_ground_truth_is_not_a_contradiction():
    report = verify_research(
        grounded_result("Today the rate is 83.2 rupees."),
        ground_truth="83.2",
    )

    assert report.contradiction is False
    assert report.verdict == VERIFIED_VERDICT


def test_numbers_compare_numerically_not_textually():
    """83.20 and 83.2 are the same number and must not read as a mismatch."""
    report = verify_research(
        grounded_result("The rate is 83.20 rupees."),
        ground_truth="83.2",
    )

    assert report.contradiction is False


def test_empty_output_fails_the_checklist():
    report = verify_research({"findings": "", "grounded": False,
                              "sources": []})

    assert report.output_readable is False
    assert report.output_hash is None
    assert report.verdict != VERIFIED_VERDICT


def test_checklist_renders_the_locked_format():
    report = verify_research(grounded_result("83.2 rupees."))
    checklist = report.checklist

    assert checklist[0].endswith("output exists")
    assert checklist[2].endswith("expected content present")
    assert checklist[4].endswith("output hash recorded")
    assert checklist[5].startswith("CONFIDENCE:")
    assert "%" in checklist[5]


# --- Autonomy Ledger ------------------------------------------------------

def test_new_capability_starts_at_the_baseline():
    assert autonomy_ledger.autonomy_of("web_research") == STARTING_AUTONOMY


def test_verified_success_promotes():
    change = autonomy_ledger.record_outcome(
        "web_research", verified=True, reason="verified against sources",
    )

    assert change.after == STARTING_AUTONOMY + PROMOTION_DELTA
    assert change.demoted is False


def test_contradiction_demotes():
    """Autonomy going DOWN is the differentiator."""
    autonomy_ledger.record_outcome("web_research", True, "ok")
    before = autonomy_ledger.autonomy_of("web_research")

    change = autonomy_ledger.record_outcome(
        "web_research", verified=False, reason="ground truth disagreed",
    )

    assert change.demoted is True
    assert change.after < before


def test_the_demo_arc_32_to_47_to_29():
    """The exact on-screen numbers from the locked demo script."""
    assert autonomy_ledger.autonomy_of("web_research") == 32.0

    up = autonomy_ledger.record_outcome("web_research", True, "verified")
    assert up.after == 47.0

    down = autonomy_ledger.record_outcome("web_research", False, "contradicted")
    assert down.after == 29.0
    assert down.oversight_restored is True


def test_demotion_is_larger_than_promotion():
    """Trust must be slower to earn than to lose."""
    assert ledger_module.DEMOTION_DELTA > ledger_module.PROMOTION_DELTA


def test_autonomy_never_reaches_certainty():
    for _ in range(20):
        autonomy_ledger.record_outcome("web_research", True, "verified")

    assert autonomy_ledger.autonomy_of("web_research") <= 95.0


def test_autonomy_never_goes_negative():
    for _ in range(20):
        autonomy_ledger.record_outcome("web_research", False, "wrong")

    assert autonomy_ledger.autonomy_of("web_research") >= 0.0


def test_rates_are_tracked():
    autonomy_ledger.record_outcome("web_research", True, "ok")
    autonomy_ledger.record_outcome("web_research", False, "bad",
                                   intervened=True)

    record = autonomy_ledger.get("web_research")

    assert record["total_outcomes"] == 2
    assert record["success_rate"] == 0.5
    assert record["intervention_rate"] == 0.5


# --- The consequence: demotion changes what is allowed --------------------

def test_demoted_capability_requires_human_verification():
    """Without this, demotion is just a number on a dashboard."""
    autonomy_ledger.record_outcome("web_research", False, "contradicted")

    assert autonomy_ledger.autonomy_of("web_research") < SUPERVISION_THRESHOLD

    decision = guardian.evaluate(
        "research the rate",
        RiskLevel.LOW,
        capability="web_research",
    )

    assert decision.decision == Decision.APPROVAL_REQUIRED
    assert decision.policy_id == "G-07"


def test_trusted_capability_still_runs_unsupervised():
    autonomy_ledger.record_outcome("web_research", True, "verified")

    assert autonomy_ledger.autonomy_of("web_research") >= SUPERVISION_THRESHOLD

    decision = guardian.evaluate(
        "research the rate",
        RiskLevel.LOW,
        capability="web_research",
    )

    assert decision.decision == Decision.ALLOW


def test_prohibited_policy_still_beats_autonomy():
    """High autonomy must never unlock a prohibition."""
    for _ in range(5):
        autonomy_ledger.record_outcome("web_research", True, "verified")

    decision = guardian.evaluate(
        "read the api key",
        RiskLevel.LOW,
        capability="web_research",
    )

    assert decision.decision == Decision.REFUSE
    assert decision.policy_id == "G-04"


def test_untracked_capability_is_not_supervised():
    """Regression: 'no record' must not read as 'no trust'.

    Every seed capability started below the threshold, so the Guardian
    demanded approval for basic arithmetic and the demo mission stalled
    on step 1.
    """
    assert autonomy_ledger.tracked("calculator") is None
    assert autonomy_ledger.requires_supervision("calculator") is False

    decision = guardian.evaluate(
        "add two numbers", RiskLevel.LOW, capability="calculator",
    )

    assert decision.decision == Decision.ALLOW


def test_grounding_is_required_for_a_verified_verdict():
    """Regression: an ungrounded answer scored exactly at the floor.

    Confidence alone must not certify a research claim, or an unsourced
    figure reaches the Business Action Brief wearing a verified badge.
    """
    result = {
        "findings": "The rate is 83.2.",
        "grounded": False,
        "sources": [],
        "checked_at": "2026-08-20T00:00:00Z",
    }

    report = verify_research(result)

    assert report.verdict == "UNVERIFIED"
