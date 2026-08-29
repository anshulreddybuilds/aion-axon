"""Gemma evaluator — scores a tested candidate before Guardian review.

Gemma is the bonus model in §4.2, used for the one job it genuinely
suits: a cheap second opinion on whether test output actually
demonstrates the capability, rather than merely exiting zero.

Honesty rule from the project doctrine: quality is scored mechanically or
it is honestly UNSCORED. If Gemma is unavailable -- wrong model id, quota,
outage -- this returns UNSCORED. It never invents a number, because a
fabricated score is worse than a missing one: a missing score prompts a
human to look, a fabricated one stops them looking.

SEC-01 (found live during Mission #1, 24 Aug): the original parser
expected one strict pipe-delimited line (`SCORE: 0-100 | VERDICT: ... |
REASON: ...`) with no fallback. Gemma answered with free-form prose
instead of that line -- a real, reproducible model-adherence failure, not
a quota issue (the call itself succeeded; see the git history for the
full forensic trace). Structured JSON output is more reliably followed by
instruction-tuned models than a bespoke pipe format, so this now asks for
JSON and validates it strictly server-side. The validator is the actual
security boundary here, not the prompt -- a JSON-shaped response is not
trusted just because it parses; every field is type- and range-checked,
and anything ambiguous still degrades to the same honest UNSCORED shape
callers already handle.
"""
import asyncio
import json
import math
import os
from typing import Any, Optional

from pydantic import BaseModel, Field
from google.genai import types

from app.google_client import genai_client
from app.observability.telemetry import record_model_call, timed

# History: gemma-3-27b-it 404'd (UNSCORED during Acquisition #1), then its
# replacement gemma-4-26b-a4b-it ALSO 404'd on 2026-08-29 - it's a real,
# newly-announced model (Gemma-4-26B-A4B, MoE, ~4B active/26B total params)
# but Google's own announcement says serverless Model Garden availability is
# rolling out "over the coming days," so it isn't live in asia-south1 yet.
#
# Rather than guess a third Gemma name, this now uses gemini-3.5-flash - the
# exact model already verified working in this project/region/call-path
# (see app/agents/mission_planner.py, planner.py, synapse/generator.py,
# tools/web_research.py). It's a cheap second opinion, same as intended.
MODEL = os.getenv("AXON_EVALUATOR_MODEL", "gemini-3.5-flash")

PROMPT = """You are grading a generated Python capability.

Respond with ONLY a single JSON object, no other text, no markdown
fences, matching exactly this shape:

{"score": <integer 0-100>, "passed": <true|false>, "reason": "<one short sentence>"}

Score on whether the TEST OUTPUT demonstrates the capability really works,
not on style. If the tests passed but only tested trivial input, score low
and say so in "reason". Output nothing before or after the JSON object.
"""


class _EvaluatorResponse(BaseModel):
    """The schema handed to the model as response_schema.

    Optional fields are additive -- current callers only read score and
    passed/reason -- but accepting them means a model that volunteers
    more detail doesn't get punished for it, and future callers can start
    reading them without another schema migration.
    """

    score: int = Field(ge=0, le=100)
    passed: bool
    reason: str = ""
    security_concerns: list[str] = Field(default_factory=list)
    correctness_concerns: list[str] = Field(default_factory=list)


async def _score(prompt: str) -> str:
    client = genai_client()

    # response_mime_type/response_schema ask the API for JSON directly.
    # This is a request, not a guarantee -- if the model or API version
    # rejects the config, or the call fails for any other reason (quota,
    # network, timeout), the exception propagates to evaluate()'s own
    # try/except exactly like before this change and degrades to
    # UNSCORED. Deliberately NOT retried here in a different mode: a
    # silent second call on failure would double real API usage on every
    # transient error, which is the wrong tradeoff on a quota that has
    # already been observed exhausted in production (see the research
    # stage's 429 during Mission #1). The manual JSON extraction +
    # validation below is the real safety net for the call that DOES
    # succeed but returns malformed content -- that was the actual
    # Mission #1 failure mode, not a call failure.
    with timed() as clock:
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=PROMPT,
                response_mime_type="application/json",
                response_schema=_EvaluatorResponse,
            ),
        )

    record_model_call("evaluate", MODEL, response, clock["ms"])

    return (response.text or "").strip()


def _extract_json_object(text: str) -> Optional[str]:
    """Finds the first balanced {...} substring in `text`, if any.

    Models sometimes wrap JSON in markdown fences or add a stray sentence
    before/after it despite instructions. This is a bounded brace-count
    scan over the literal text -- no eval, no regex backtracking risk --
    so it safely tolerates that without trusting anything about the
    content inside the braces; validation still happens after.
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None


def _parse(text: str) -> dict[str, Any]:
    """Strict JSON parse + validation. Never raises; returns a dict with
    "valid": False on anything malformed, ambiguous, or out of range."""
    candidate = _extract_json_object(text)

    if candidate is None:
        return {"valid": False}

    try:
        payload = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return {"valid": False}

    if not isinstance(payload, dict):
        return {"valid": False}

    raw_score = payload.get("score")

    # bool is a subclass of int in Python -- isinstance(True, int) is
    # True -- so bool must be rejected explicitly or "score": true would
    # silently pass as score=1.
    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        return {"valid": False}

    if isinstance(raw_score, float) and (
        math.isnan(raw_score) or math.isinf(raw_score)
    ):
        return {"valid": False}

    score = int(raw_score)

    if score != raw_score or score < 0 or score > 100:
        return {"valid": False}

    passed = payload.get("passed")

    if not isinstance(passed, bool):
        return {"valid": False}

    reason = payload.get("reason")

    if reason is not None and not isinstance(reason, str):
        return {"valid": False}

    return {
        "valid": True,
        "score": score,
        "verdict": "PASS" if passed else "FAIL",
        "reason": (reason or "").strip()[:500],
    }


def evaluate(
    candidate_name: str,
    description: str,
    code: str,
    test_result: dict[str, Any],
) -> dict[str, Any]:
    """Score a candidate. Never raises; UNSCORED when unavailable or
    malformed. Fails closed at every step -- an ambiguous or partially
    valid response is treated the same as no response at all."""
    prompt = (
        f"CAPABILITY: {candidate_name}\n"
        f"PURPOSE: {description}\n\n"
        f"CODE:\n{code}\n\n"
        f"TESTS PASSED: {test_result.get('passed')}\n"
        f"STDOUT:\n{(test_result.get('stdout') or '')[:2000]}\n"
        f"STDERR:\n{(test_result.get('stderr') or '')[:2000]}\n"
    )

    try:
        raw = asyncio.run(_score(prompt))
    except Exception as error:  # noqa: BLE001
        # asyncio.run(...) re-raises whatever the SDK call raised; a
        # deadline/timeout from the SDK surfaces as one of these two
        # names depending on transport, so both get their own reason
        # code instead of collapsing into the generic "unavailable" one
        # a human would otherwise have to read the message to diagnose.
        is_timeout = type(error).__name__ in ("TimeoutError", "DeadlineExceeded")
        return {
            "status": "UNSCORED",
            "reason_code": "EVALUATOR_TIMEOUT" if is_timeout else "EVALUATOR_UNAVAILABLE",
            "model": MODEL,
            "reason": (
                f"Evaluator unavailable: {type(error).__name__}: {error}"
            ),
            "score": None,
            "verdict": None,
        }

    parsed = _parse(raw)

    if not parsed.get("valid"):
        return {
            "status": "UNSCORED",
            "reason_code": "EVALUATOR_MALFORMED_OUTPUT",
            "model": MODEL,
            "reason": "Evaluator response could not be parsed into a valid score.",
            "raw": raw[:300],
            "score": None,
            "verdict": None,
        }

    return {
        "status": "SCORED",
        "reason_code": "EVALUATOR_SCORED_FAIL" if parsed["verdict"] == "FAIL" else "EVALUATOR_SCORED_PASS",
        "model": MODEL,
        "score": parsed["score"],
        "verdict": parsed["verdict"],
        "reason": parsed["reason"],
    }
