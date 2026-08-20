"""Read-only public web research, grounded in Google Search.

Returns findings WITH source receipts. An ungrounded answer from a model
is a claim; a grounded one carries the URLs it came from, and a Business
Action Brief is only worth reading if its numbers can be traced.

Read-only by construction: this tool retrieves and summarises. It has no
write path to anything.
"""
import asyncio
import os
from typing import Any

from google import genai
from google.genai import types

MODEL = os.getenv("AXON_RESEARCH_MODEL", "gemini-3.6-flash")


def _api_key() -> str:
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

    if not key:
        raise RuntimeError("No Gemini API key configured for web research.")

    return key


async def _generate_async(query: str, grounded: bool = True) -> Any:
    """Build the client INSIDE the coroutine that uses it.

    The ADK Runner drives the planner in its own event loop and closes the
    shared genai transport when that loop tears down. Since the planner
    runs on every mission, a client created outside this coroutine is
    already closed by the time research runs ("Cannot send a request, as
    the client has been closed"). Creating it here binds it to the loop
    that actually issues the request -- the same pattern the planner uses,
    which is why the planner never hit this.
    """
    client = genai.Client(api_key=_api_key())

    instruction = (
        "You are a research assistant. Answer only from search "
        "results. State findings plainly and include concrete "
        "figures and dates where available. If the sources do "
        "not support an answer, say so instead of guessing."
    ) if grounded else (
        "You are a research assistant answering WITHOUT live search. "
        "Answer only from stable background knowledge. Say plainly that "
        "you cannot confirm anything time-sensitive such as a current "
        "price or rate. Never invent a figure or a source."
    )

    config = types.GenerateContentConfig(system_instruction=instruction)

    if grounded:
        config.tools = [types.Tool(google_search=types.GoogleSearch())]

    return await client.aio.models.generate_content(
        model=MODEL,
        contents=query,
        config=config,
    )


def _receipts(response: Any) -> list[dict[str, str]]:
    """Extract source receipts from grounding metadata.

    Returns [] when the model answered without grounding. The caller must
    treat that as ungrounded rather than assume sources exist.
    """
    receipts: list[dict[str, str]] = []

    for candidate in getattr(response, "candidates", None) or []:
        metadata = getattr(candidate, "grounding_metadata", None)

        if metadata is None:
            continue

        for chunk in getattr(metadata, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)

            if web is None:
                continue

            receipts.append({
                "title": getattr(web, "title", "") or "",
                "uri": getattr(web, "uri", "") or "",
            })

    seen = set()
    unique = []

    for receipt in receipts:
        if receipt["uri"] and receipt["uri"] not in seen:
            seen.add(receipt["uri"])
            unique.append(receipt)

    return unique


def search_web(query: str) -> dict[str, Any]:
    """Research a question on the public web. No external side effects."""
    if not query or not query.strip():
        return {"status": "ERROR", "error": "Search query cannot be empty."}

    query = query.strip()

    degraded_reason = None

    try:
        response = asyncio.run(_generate_async(query, grounded=True))
    except Exception as error:  # noqa: BLE001 - reported, never retried blindly
        # Search grounding has its own quota, separate from plain
        # generation. When it is exhausted, fall back to an UNGROUNDED
        # answer that is clearly labelled as such. The fallback exists so
        # a mission degrades honestly instead of dying -- it must never
        # be mistaken for a sourced answer, so grounded stays false and
        # sources stays empty.
        degraded_reason = f"{type(error).__name__}: {error}"

        try:
            response = asyncio.run(_generate_async(query, grounded=False))
        except Exception as fallback_error:  # noqa: BLE001
            return {
                "status": "ERROR",
                "query": query,
                "error": f"{type(fallback_error).__name__}: {fallback_error}",
                "grounding_error": degraded_reason,
            }

    receipts = [] if degraded_reason else _receipts(response)

    return {
        "status": "SUCCESS" if not degraded_reason else "DEGRADED",
        "query": query,
        "findings": (response.text or "").strip(),
        "sources": receipts,
        "source_count": len(receipts),
        "grounded": bool(receipts),
        "model": MODEL,
        "degraded_reason": degraded_reason,
    }
