"""Gemma evaluator parsing and honest-failure behaviour.

The live model call is a manual probe (scripts/check_evaluator.py). What
is tested here is the part that decides whether a score exists at all --
because the failure that matters is a malformed response silently
becoming a passing score.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

from app.synapse import evaluator  # noqa: E402


def test_model_is_a_real_pinned_id():
    """Regression: gemma-3-27b-it did not exist and 404'd at runtime."""
    assert evaluator.MODEL != "gemma-3-27b-it"
    assert evaluator.MODEL.startswith("gemma-")


def test_parses_a_well_formed_response():
    parsed = evaluator._parse(
        "SCORE: 85 | VERDICT: PASS | REASON: handles bad input"
    )

    assert parsed["score"] == 85
    assert parsed["verdict"] == "PASS"
    assert parsed["reason"] == "handles bad input"


def test_parses_a_failing_response():
    parsed = evaluator._parse(
        "SCORE: 0 | VERDICT: FAIL | REASON: returns a hardcoded value"
    )

    assert parsed["score"] == 0
    assert parsed["verdict"] == "FAIL"


def test_score_is_clamped_to_range():
    assert evaluator._parse("SCORE: 900 | VERDICT: PASS")["score"] == 100


def test_unparseable_response_yields_no_score(monkeypatch):
    """A model that rambles must produce UNSCORED, never a default pass."""
    async def rambling(prompt):
        return "I think this code is pretty good overall!"

    monkeypatch.setattr(evaluator, "_score", rambling)

    result = evaluator.evaluate("x", "y", "code", {"passed": True})

    assert result["status"] == "UNSCORED"
    assert result["score"] is None


def test_unavailable_model_yields_unscored(monkeypatch):
    async def boom(prompt):
        raise RuntimeError("404 NOT_FOUND")

    monkeypatch.setattr(evaluator, "_score", boom)

    result = evaluator.evaluate("x", "y", "code", {"passed": True})

    assert result["status"] == "UNSCORED"
    assert result["score"] is None
    assert "404" in result["reason"]
