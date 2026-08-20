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


async def _generate_async(query: str) -> Any:
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

    return await client.aio.models.generate_content(
        model=MODEL,
        contents=query,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            system_instruction=(
                "You are a research assistant. Answer only from search "
                "results. State findings plainly and include concrete "
                "figures and dates where available. If the sources do "
                "not support an answer, say so instead of guessing."
            ),
        ),
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

    try:
        response = asyncio.run(_generate_async(query))
    except Exception as error:  # noqa: BLE001 - reported, never retried blindly
        return {
            "status": "ERROR",
            "query": query,
            "error": f"{type(error).__name__}: {error}",
        }

    receipts = _receipts(response)

    return {
        "status": "SUCCESS",
        "query": query,
        "findings": (response.text or "").strip(),
        "sources": receipts,
        "source_count": len(receipts),
        "grounded": bool(receipts),
        "model": MODEL,
    }
