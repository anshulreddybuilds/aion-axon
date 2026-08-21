"""Ground truth — the independent check the Evidence Engine needs.

The failure mode that matters here is NOT missing a contradiction. It is
manufacturing one: applying a loosely-related fact would demote a
capability that was actually right, and an agent punished for being
correct makes the ledger meaningless.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

from datetime import datetime, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402

from app.governance import ground_truth as gt  # noqa: E402
from app.governance.autonomy_ledger import autonomy_ledger  # noqa: E402
from app.governance.verification import verify_outcome  # noqa: E402
from app.memory.firestore_store import firestore_store  # noqa: E402


@pytest.fixture(autouse=True)
def clean():
    firestore_store.ground_truth.clear()
    firestore_store.capabilities.clear()
    yield
    firestore_store.ground_truth.clear()
    firestore_store.capabilities.clear()


def fx_fact():
    return gt.record(
        key="usd_inr_aug_2026",
        statement="USD to INR exchange rate August 2026",
        value="83.2",
        source="https://rbi.org.in/reference-rates",
        recorded_by="anshul",
    )


# --- Provenance is mandatory ---------------------------------------------

def test_a_fact_without_a_source_is_rejected():
    """An unauditable fact must not be able to demote a capability."""
    result = gt.record("k", "some statement", "1", "", "anshul")

    assert result["status"] == "REJECTED"
    assert "provenance" in result["error"]
    assert gt.all_facts() == []


def test_recording_stores_who_and_where_from():
    fact = fx_fact()["fact"]

    assert fact["recorded_by"] == "anshul"
    assert fact["source"].startswith("https://")
    assert fact["recorded_at"]


# --- Matching is conservative --------------------------------------------

def test_a_clear_match_is_found():
    fx_fact()

    fact = gt.lookup("What is the USD to INR exchange rate?")

    assert fact is not None
    assert fact.value == "83.2"


def test_an_unrelated_query_matches_nothing():
    """Silence beats a guess."""
    fx_fact()

    assert gt.lookup("How many moons does Jupiter have?") is None


def test_a_weak_overlap_is_refused():
    """One shared word must not be enough to manufacture a contradiction."""
    fx_fact()

    assert gt.lookup("exchange students in August") is None


def test_empty_query_matches_nothing():
    fx_fact()

    assert gt.lookup("") is None


# --- Staleness ------------------------------------------------------------

def test_a_stale_fact_is_flagged():
    """'The rate was 83.2 in August' is not evidence about December."""
    fx_fact()

    old = datetime.now(timezone.utc) - timedelta(days=200)
    stored = firestore_store.ground_truth["usd_inr_aug_2026"]
    stored["recorded_at"] = old.isoformat()

    fact = gt.lookup("USD to INR exchange rate")

    assert fact.stale is True


# --- The whole point: a real contradiction demotes ------------------------

def research(findings, query="What is the USD to INR exchange rate?"):
    return {
        "status": "EXECUTED",
        "result": {
            "query": query,
            "findings": findings,
            "grounded": True,
            "sources": [{"title": "s", "uri": "https://example.com"}],
            "source_count": 1,
        },
    }


def test_a_claim_contradicting_ground_truth_demotes():
    """Reality disagrees with the agent -- the beat the demo is built on."""
    fx_fact()

    autonomy_ledger.record_outcome("web_research", True, "seed")
    before = autonomy_ledger.autonomy_of("web_research")

    evidence = verify_outcome(
        "web_research", research("The USD to INR rate is 12.0."),
    )

    assert evidence["verdict"] == "CONTRADICTED"
    assert evidence["demoted"] is True
    assert autonomy_ledger.autonomy_of("web_research") < before
    assert evidence["ground_truth"]["source"].startswith("https://")


def test_a_correct_claim_is_not_demoted():
    """The check must not punish a capability for being right."""
    fx_fact()

    evidence = verify_outcome(
        "web_research", research("Today the rate is 83.2 rupees."),
    )

    assert evidence["verdict"] == "VERIFIED"
    assert evidence["demoted"] is False


def test_no_matching_fact_means_no_contradiction():
    """With nothing to check against, form is all that can be judged."""
    fx_fact()

    evidence = verify_outcome(
        "web_research",
        research("Jupiter has 95 moons.", query="How many moons has Jupiter?"),
    )

    assert evidence["verdict"] != "CONTRADICTED"
    assert evidence["ground_truth"] is None


def test_a_stale_fact_does_not_demote():
    """A stale fact is reported, not silently trusted."""
    fx_fact()

    old = datetime.now(timezone.utc) - timedelta(days=200)
    firestore_store.ground_truth["usd_inr_aug_2026"]["recorded_at"] = (
        old.isoformat()
    )

    evidence = verify_outcome(
        "web_research", research("The USD to INR rate is 12.0."),
    )

    assert evidence["verdict"] != "CONTRADICTED"
    assert evidence["ground_truth"]["stale"] is True


def test_matching_requires_covering_most_of_the_fact():
    """Absolute overlap alone let an unrelated query through.

    "exchange students in August" shares two words with the FX fact and
    would have been checked against the exchange rate. Coverage is what
    separates a query about the fact from one brushing past it.
    """
    fx_fact()

    assert gt.lookup("exchange students in August") is None
    assert gt.lookup("USD to INR exchange rate") is not None


def test_the_best_covering_fact_wins_when_several_could_match():
    fx_fact()
    gt.record(
        key="usd_eur",
        statement="USD to EUR exchange rate August 2026",
        value="0.92",
        source="https://ecb.europa.eu",
        recorded_by="anshul",
    )

    fact = gt.lookup("What is the USD to EUR exchange rate in August 2026?")

    assert fact.key == "usd_eur"
