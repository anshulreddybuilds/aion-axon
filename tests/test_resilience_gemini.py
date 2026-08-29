"""PHASE 12 — every Gemini failure mode must fail safely and VISIBLY.

The evaluator's 404/timeout handling is already covered in
tests/test_evaluator.py, and web_research's grounding-degradation and
total-failure paths in tests/test_web_research.py. The gap these close is
the other two call sites — the structured mission planner and SYNAPSE's
generator — under the four failures that actually happen in production:

  429 RESOURCE_EXHAUSTED  (free-tier daily cap; observed live in Mission #1)
  404 NOT_FOUND           (model absent on the configured path -- observed
                           on Vertex, where gemma-4-26b-a4b-it does not
                           exist at any location)
  timeout                 (deadline exceeded mid-call)
  connection failure      (no network / DNS / transport error)

The property under test is the same for all of them and is not "it
returns something": the failure must be REPORTED, carry the real reason,
and never be mistaken for a successful plan or a usable candidate. A
degraded run that looks like a good one is the single failure mode this
whole project argues against.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

import pytest  # noqa: E402

from app.agents import mission_planner as planner_module  # noqa: E402
from app.synapse import generator as generator_module  # noqa: E402


class Quota(Exception):
    """Stands in for google.genai's ClientError; the code paths under test
    catch by breadth, not by SDK type, so the concrete class does not
    matter -- only that a real exception crosses the boundary."""


FAILURES = [
    pytest.param(
        Quota("429 RESOURCE_EXHAUSTED. Quota exceeded for "
              "generate_content_free_tier_requests, limit: 20"),
        "429", id="quota_429"),
    pytest.param(
        Quota("404 NOT_FOUND. Publisher model "
              "`gemma-4-26b-a4b-it` was not found"),
        "404", id="model_404"),
    pytest.param(TimeoutError("deadline exceeded"), "deadline", id="timeout"),
    pytest.param(
        ConnectionError("[Errno 11001] getaddrinfo failed"),
        "getaddrinfo", id="network"),
]


# --- structured mission planner -------------------------------------------

@pytest.mark.parametrize("error, needle", FAILURES)
def test_planner_reports_the_real_reason_and_never_invents_a_plan(
    monkeypatch, error, needle,
):
    monkeypatch.setattr(planner_module, "planner_available", lambda: True)

    async def explode(request, user_id):
        raise error

    monkeypatch.setattr(planner_module, "_run", explode)

    plan, err = planner_module.plan_mission("Calculate 50 plus 50")

    # No plan is the honest outcome. A fabricated one would be worse than
    # the failure it is hiding.
    assert plan is None
    assert err is not None
    assert needle in err
    # The exception TYPE is named too, so a 429 is distinguishable from a
    # network outage in the mission record without re-running anything.
    assert type(error).__name__ in err


def test_planner_without_credentials_says_so_rather_than_failing_obscurely(
    monkeypatch,
):
    monkeypatch.setattr(planner_module, "planner_available", lambda: False)

    plan, err = planner_module.plan_mission("Calculate 50 plus 50")

    assert plan is None
    # Must name BOTH supported auth paths -- a message that only mentions
    # an API key sends a Vertex/ADC operator down the wrong road, which
    # is exactly the confusion 8b30ba4 set out to remove.
    assert "GOOGLE_API_KEY" in err
    assert "GOOGLE_GENAI_USE_VERTEXAI" in err


def test_planner_empty_response_is_not_treated_as_a_plan(monkeypatch):
    """An empty completion is a failure, not an empty-but-valid plan."""
    monkeypatch.setattr(planner_module, "planner_available", lambda: True)

    async def silent(request, user_id):
        return ""

    monkeypatch.setattr(planner_module, "_run", silent)

    plan, err = planner_module.plan_mission("Calculate 50 plus 50")

    assert plan is None
    assert err


# --- SYNAPSE generator ----------------------------------------------------

@pytest.mark.parametrize("error, needle", FAILURES)
def test_generator_reports_the_real_reason_and_never_invents_a_candidate(
    monkeypatch, error, needle,
):
    async def explode(prompt):
        raise error

    monkeypatch.setattr(generator_module, "_generate", explode)

    candidate, err = generator_module.generate_candidate("count things")

    # A fabricated candidate would be code proposed for installation that
    # no model ever wrote.
    assert candidate is None
    assert err is not None
    assert needle in err


def test_generator_malformed_json_is_rejected_not_half_parsed(monkeypatch):
    async def garbage(prompt):
        return "this is not json at all"

    monkeypatch.setattr(generator_module, "_generate", garbage)

    candidate, err = generator_module.generate_candidate("count things")

    assert candidate is None
    assert err
