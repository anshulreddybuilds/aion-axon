"""Drives the ADK planner agent against Gemini.

This is the layer that makes google.adk load-bearing rather than declared:
the planner Agent is executed by an ADK Runner, and its output is a real
Gemini completion.

Planning is advisory only. It produces a plan; it never executes anything.
All execution still goes through the Unified Execution Gate, so a planner
failure can never widen what AION AXON is allowed to do.

If no API key is present the planner is skipped and the caller receives
None. That keeps tests and CI offline and deterministic without pretending
a plan was produced.
"""
import asyncio
from typing import Optional

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agents.planner import planner_agent
from app.google_client import genai_available

APP_NAME = "aion_axon"


def planner_available() -> bool:
    """True when a Gemini API key OR a Vertex AI configuration is
    present. google.adk.models.Gemini builds its client the same way
    genai_client() does (see app/google_client.py's own docstring for
    the traced SDK source), so both auth paths that make a real call
    possible also make the ADK-driven planner possible."""
    return genai_available()


async def _run(user_request: str, user_id: str) -> str:
    session_service = InMemorySessionService()

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
    )

    runner = Runner(
        app_name=APP_NAME,
        agent=planner_agent,
        session_service=session_service,
    )

    message = types.Content(
        role="user",
        parts=[types.Part(text=user_request)],
    )

    chunks: list[str] = []

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=message,
    ):
        if not event.content or not event.content.parts:
            continue

        for part in event.content.parts:
            if getattr(part, "text", None):
                chunks.append(part.text)

    return "".join(chunks).strip()


def run_planner(
    user_request: str,
    user_id: str = "anshul",
) -> Optional[str]:
    """Return the planner's plan text, or None if planning was skipped.

    Never raises: a planner outage must not take down the governed loop.
    """
    if not planner_available():
        return None

    try:
        return asyncio.run(_run(user_request, user_id))
    except Exception as error:  # noqa: BLE001 - planning is advisory
        return f"PLANNER_ERROR: {type(error).__name__}: {error}"
