"""Generates a candidate capability from a gap and its research.

The model writes the code; it does not decide whether the code ships.
Everything downstream -- safety screen, sandbox, evaluator, Guardian,
owner approval -- exists because generated code is a proposal, not an
authority.
"""
import asyncio
import json
import os
from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.observability.telemetry import record_model_call, timed

MODEL = os.getenv("AXON_BUILDER_MODEL", "gemini-3.6-flash")


class Candidate(BaseModel):
    name: str = Field(..., description="snake_case capability name.")
    description: str = Field(..., description="One line, plain language.")
    risk: str = Field("LOW", description="LOW | MEDIUM | HIGH")
    code: str = Field(..., description="Python source defining the function.")
    test: str = Field(..., description="Assertions proving it works.")
    entrypoint: str = Field(..., description="Function name to call.")


INSTRUCTION = """
You write a single self-contained Python capability for AION Axon.

Hard constraints -- a candidate breaking any of these is rejected before
it ever runs:

1. Standard library ONLY, and only pure computation modules such as json,
   math, re, datetime, decimal, statistics.
2. NEVER import os, sys, subprocess, socket, shutil, pathlib, importlib,
   pickle, ctypes, threading, multiprocessing, or any google package.
3. NEVER call eval, exec, compile, open, input, __import__, getattr,
   setattr, or access dunder attributes.
4. No network access. No file access. No environment access.
5. Define ONE top-level function. It takes strings and returns a dict
   containing at least {"status": "SUCCESS" | "ERROR"}.
6. The function must be deterministic and must not raise: return
   {"status": "ERROR", "error": "..."} instead.
7. The test must be plain `assert` statements followed by print("OK").
   It must cover a normal case AND a bad-input case.
8. NEVER assert exact equality on a float. `assert x == -0.010027` fails
   on binary rounding even when the maths is right, and a candidate whose
   own test fails is rejected outright — so a brittle assertion throws
   away working code. Use `round(x, 4) == ...`, or
   `abs(x - expected) < 1e-6`, or assert a range.
9. Assert what the function GUARANTEES, not incidental detail. Prefer
   status, sign, ordering, key presence and magnitude over exact
   arithmetic you worked out in your head and may have got wrong.

If the need includes a sample of the real input, parse THAT shape
exactly. Do not rename its fields to ones you find more natural: the
capability is called with that data and nothing else, so a tidier field
name is just a capability that does not work.

Return only the structured candidate.
"""


def _client() -> genai.Client:
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

    if not key:
        raise RuntimeError("No Gemini API key configured for generation.")

    return genai.Client(api_key=key)


async def _generate(prompt: str) -> str:
    # Built inside the coroutine: the ADK Runner closes the shared genai
    # transport when its loop tears down, and the planner runs on every
    # mission.
    client = _client()

    with timed() as clock:
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=INSTRUCTION,
                response_mime_type="application/json",
                response_schema=Candidate,
            ),
        )

    record_model_call("generate", MODEL, response, clock["ms"])

    return (response.text or "").strip()


def generate_candidate(
    need: str,
    research: Optional[str] = None,
    prior_failure: Optional[str] = None,
) -> tuple[Optional[Candidate], Optional[str]]:
    """Return (candidate, error). Never raises.

    `prior_failure` is optional and additive: passing None (every existing
    call site) produces the exact same prompt as before this parameter
    existed. When set, it carries the previous candidate's real sandbox
    stderr/reason into the prompt so a bounded retry can address the
    ACTUAL failure rather than generate blind a second time.
    """
    prompt = f"CAPABILITY NEEDED:\n{need}\n"

    if research:
        prompt += f"\nRESEARCH NOTES:\n{research}\n"

    if prior_failure:
        prompt += (
            f"\nA PREVIOUS ATTEMPT FAILED ITS OWN SANDBOX TEST:\n"
            f"{prior_failure[:1500]}\n"
            f"Write a corrected candidate that avoids this specific failure.\n"
        )

    try:
        raw = asyncio.run(_generate(prompt))
    except Exception as error:  # noqa: BLE001
        return None, f"{type(error).__name__}: {error}"

    if not raw:
        return None, "Builder returned an empty response."

    try:
        return Candidate.model_validate(json.loads(raw)), None
    except Exception as error:  # noqa: BLE001
        return None, f"Builder returned an unusable candidate: {error}"
