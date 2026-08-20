"""Gemma evaluator — scores a tested candidate before Guardian review.

Gemma is the bonus model in §4.2, used for the one job it genuinely
suits: a cheap second opinion on whether test output actually
demonstrates the capability, rather than merely exiting zero.

Honesty rule from the project doctrine: quality is scored mechanically or
it is honestly UNSCORED. If Gemma is unavailable -- wrong model id, quota,
outage -- this returns UNSCORED. It never invents a number, because a
fabricated score is worse than a missing one: a missing score prompts a
human to look, a fabricated one stops them looking.
"""
import asyncio
import os
from typing import Any

from google import genai
from google.genai import types

# Overridable because Gemma model ids move. An unknown id must degrade to
# UNSCORED, never to a guess.
MODEL = os.getenv("AXON_EVALUATOR_MODEL", "gemma-3-27b-it")

PROMPT = """You are grading a generated Python capability.

Answer with ONE line in exactly this format:
SCORE: <0-100> | VERDICT: <PASS|FAIL> | REASON: <one short sentence>

Score on whether the TEST OUTPUT demonstrates the capability really works,
not on style. If the tests passed but only tested trivial input, score low
and say so.
"""


def _client() -> genai.Client:
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

    if not key:
        raise RuntimeError("No API key configured for the evaluator.")

    return genai.Client(api_key=key)


async def _score(prompt: str) -> str:
    client = _client()

    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=PROMPT),
    )

    return (response.text or "").strip()


def _parse(text: str) -> dict[str, Any]:
    score = None
    verdict = None
    reason = text.strip()

    for part in text.split("|"):
        part = part.strip()

        if part.upper().startswith("SCORE:"):
            digits = "".join(
                c for c in part.split(":", 1)[1] if c.isdigit()
            )
            if digits:
                score = max(0, min(100, int(digits)))

        elif part.upper().startswith("VERDICT:"):
            value = part.split(":", 1)[1].strip().upper()
            if value in ("PASS", "FAIL"):
                verdict = value

        elif part.upper().startswith("REASON:"):
            reason = part.split(":", 1)[1].strip()

    return {"score": score, "verdict": verdict, "reason": reason}


def evaluate(
    candidate_name: str,
    description: str,
    code: str,
    test_result: dict[str, Any],
) -> dict[str, Any]:
    """Score a candidate. Never raises; UNSCORED when unavailable."""
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
        return {
            "status": "UNSCORED",
            "model": MODEL,
            "reason": (
                f"Evaluator unavailable: {type(error).__name__}: {error}"
            ),
            "score": None,
            "verdict": None,
        }

    parsed = _parse(raw)

    if parsed["score"] is None:
        return {
            "status": "UNSCORED",
            "model": MODEL,
            "reason": "Evaluator response could not be parsed into a score.",
            "raw": raw[:300],
            "score": None,
            "verdict": None,
        }

    return {
        "status": "SCORED",
        "model": MODEL,
        "score": parsed["score"],
        "verdict": parsed["verdict"],
        "reason": parsed["reason"],
    }
