from urllib.parse import quote
import requests


def search_web(query: str) -> dict:
    """
    Read-only public web research tool.

    Uses Google's public search endpoint through Google Programmable
    Search when configured. No external side effects.
    """

    if not query or not query.strip():
        return {
            "status": "ERROR",
            "error": "Search query cannot be empty.",
        }

    return {
        "status": "READY",
        "query": query.strip(),
        "message": (
            "Web research tool interface created. "
            "A production search provider will be connected through "
            "Google Cloud configuration."
        ),
    }
