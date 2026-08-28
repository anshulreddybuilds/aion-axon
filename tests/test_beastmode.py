"""Tests for the additive Beastmode layer.

Same discipline as the rest of the suite: every claim gets an assertion,
and where a fix mattered, a regression test proves it by construction
(the ledger tamper test literally mutates an event and checks the
mismatch is detected, rather than trusting the code to notice).
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

import pytest

from app.beastmode.contracts import build_contract
from app.beastmode.ledger_chain import GENESIS, build_chain, seal, verify
from app.beastmode.red_team import _run
from app.beastmode.risk_score import compute_risk_score
from app.memory.firestore_store import firestore_store
from app.synapse.safety_screen import FORBIDDEN_CALLS, FORBIDDEN_IMPORTS


# ---------------------------------------------------------------- contracts

def test_contract_reads_the_real_forbidden_lists_not_a_copy():
    """If safety_screen.py ever adds an 18th forbidden import, this number
    must move with it -- proving the two cannot silently drift apart."""
    contract = build_contract(
        name="x", entrypoint="x", risk="LOW", ast_safe=True,
    )
    assert contract.forbidden_imports_checked == len(FORBIDDEN_IMPORTS)
    assert contract.forbidden_calls_checked == len(FORBIDDEN_CALLS)


def test_contract_declares_zero_network_and_credentials_always():
    contract = build_contract(name="x", entrypoint="x", risk="HIGH", ast_safe=True)
    d = contract.to_dict()
    assert d["permissions"]["network"] == "DENY"
    assert d["permissions"]["credentials"] == "DENY"


def test_contract_carries_real_ast_findings_through():
    contract = build_contract(
        name="x", entrypoint="x", risk="LOW", ast_safe=False,
        ast_findings=["Forbidden import: os"],
    )
    assert contract.ast_safe is False
    assert "Forbidden import: os" in contract.to_dict()["static_screen"]["findings"]


# ---------------------------------------------------------------- red team

def test_red_team_calls_the_real_screen_function():
    """Not a simulation: feed it something actually forbidden and it must
    actually be caught, using the exact same screen() the pipeline uses."""
    results, contained = _run()
    subprocess_result = next(r for r in results if r["vector"] == "subprocess execution")
    assert subprocess_result["blocked"] is True
    assert "subprocess" in subprocess_result["detail"]


def test_red_team_marks_the_resource_vector_as_other_layer_not_a_pass():
    """The resource-exhaustion vector must NEVER silently read as 'blocked'
    -- the AST screen genuinely does not catch it, and pretending otherwise
    would be exactly the fabricated-confidence failure this project exists
    to avoid."""
    results, _ = _run()
    resource = next(r for r in results if r["vector"].startswith("resource exhaustion"))
    assert resource["blocked"] is False
    assert resource["expected_miss_here"] is True


def test_red_team_persuasion_attacks_cite_a_real_policy_id():
    results, _ = _run()
    persuasion = [r for r in results if r["vector"].startswith("persuasion")]
    assert len(persuasion) == 5
    for r in persuasion:
        assert r["blocked"] is True
        assert "G-04" in r["layer"] or "G-06" in r["layer"]


# ---------------------------------------------------------------- risk score

def test_risk_score_never_treats_a_missing_evaluator_score_as_safe():
    """Doctrine: a missing verdict is not a confident one. A None score
    must never compute to the same risk as a clean 100."""
    missing = compute_risk_score(
        ast_finding_count=0, sandbox_passed=True, evaluator_score=None,
    )
    clean = compute_risk_score(
        ast_finding_count=0, sandbox_passed=True, evaluator_score=100,
    )
    assert missing.score > clean.score


def test_risk_score_low_evaluator_score_outweighs_a_passing_sandbox():
    result = compute_risk_score(
        ast_finding_count=0, sandbox_passed=True, evaluator_score=10,
    )
    assert result.tier in ("HIGH", "CRITICAL", "PROHIBITED")


def test_risk_score_is_read_only_narration_not_a_gate():
    """This module has no way to block anything -- it only returns data.
    Asserting the return type carries no side-effecting method is the
    closest a unit test gets to proving "this cannot become a bypass"."""
    result = compute_risk_score(
        ast_finding_count=5, sandbox_passed=False, evaluator_score=0,
        network_declared=True, credentials_declared=True,
    )
    assert not hasattr(result, "execute")
    assert not hasattr(result, "approve")
    assert result.score == 100
    assert result.tier == "PROHIBITED"


# ---------------------------------------------------------------- ledger

def _fake_events(n: int) -> list[dict]:
    return [
        {"change": f"event {i}", "capability": f"cap_{i}", "approver": "anshul"}
        for i in range(n)
    ]


def test_ledger_chain_is_deterministic_for_the_same_events():
    events = _fake_events(4)
    a = build_chain(events)
    b = build_chain(events)
    assert [link.chain_hash for link in a] == [link.chain_hash for link in b]


def test_ledger_chain_changes_if_a_single_event_is_altered():
    """The whole point of chaining: touching event #1 must move every
    hash after it, not just that one entry."""
    events = _fake_events(4)
    before = build_chain(events)

    tampered = [dict(e) for e in events]
    tampered[1]["change"] = "a different change, silently substituted"
    after = build_chain(tampered)

    assert before[1].chain_hash != after[1].chain_hash
    assert before[2].chain_hash != after[2].chain_hash
    assert before[3].chain_hash != after[3].chain_hash
    # Event 0, before the tamper, is correctly unaffected.
    assert before[0].chain_hash == after[0].chain_hash


def test_ledger_seal_and_verify_round_trip(monkeypatch):
    # Isolated per-test via monkeypatch (auto-restored after the test),
    # same as every other test's own state in this suite -- seal storage
    # moved from a local file to firestore_store (see ledger_chain.py's
    # module docstring for why: a Cloud Run container's filesystem is
    # neither shared across instances nor durable across a cold start).
    monkeypatch.setattr(firestore_store, "ledger_seal", None)

    events = _fake_events(3)
    seal(events)
    report = verify(events)

    assert report["status"] == "VERIFIED"
    assert report["event_count"] == 3


def test_ledger_verify_detects_tampering_after_sealing(monkeypatch):
    """Proven by reverting the fix, project-style: seal the real events,
    mutate one, and check verify() actually notices rather than trusting
    that it would."""
    monkeypatch.setattr(firestore_store, "ledger_seal", None)

    events = _fake_events(3)
    seal(events)

    tampered = [dict(e) for e in events]
    tampered[0]["approver"] = "someone-else"

    report = verify(tampered)
    assert report["status"] == "MISMATCH"


def test_ledger_verify_with_no_prior_seal_says_so_honestly(monkeypatch):
    monkeypatch.setattr(firestore_store, "ledger_seal", None)

    report = verify(_fake_events(2))
    assert report["status"] == "NO_SEAL"


def test_genesis_hash_is_a_fixed_64_char_hex_string():
    assert len(GENESIS) == 64
    assert GENESIS == "0" * 64
