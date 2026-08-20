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

    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=INSTRUCTION,
            response_mime_type="application/json",
            response_schema=Candidate,
        ),
    )

    return (response.text or "").strip()


def generate_candidate(
    need: str,
    research: Optional[str] = None,
) -> tuple[Optional[Candidate], Optional[str]]:
    """Return (candidate, error). Never raises."""
    prompt = f"CAPABILITY NEEDED:\n{need}\n"

    if research:
        prompt += f"\nRESEARCH NOTES:\n{research}\n"

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
