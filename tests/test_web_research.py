"""web_research: receipt extraction and honest failure.

The live grounding call is a manual probe. What is testable offline is the
part that decides whether an answer is SOURCED or merely CLAIMED, which is
the part a Business Action Brief depends on.
"""
import os
from types import SimpleNamespace

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

from app.tools import web_research  # noqa: E402


def response_with(chunks):
    return SimpleNamespace(
        candidates=[
            SimpleNamespace(
                grounding_metadata=SimpleNamespace(grounding_chunks=chunks)
            )
        ],
        text="some findings",
    )


def web_chunk(title, uri):
    return SimpleNamespace(web=SimpleNamespace(title=title, uri=uri))


def test_receipts_extracted():
    response = response_with([
        web_chunk("RBI", "https://rbi.org.in/rates"),
        web_chunk("XE", "https://xe.com/usdinr"),
    ])

    receipts = web_research._receipts(response)

    assert len(receipts) == 2
    assert receipts[0]["uri"] == "https://rbi.org.in/rates"


def test_duplicate_sources_are_collapsed():
    response = response_with([
        web_chunk("RBI", "https://rbi.org.in/rates"),
        web_chunk("RBI again", "https://rbi.org.in/rates"),
    ])

    assert len(web_research._receipts(response)) == 1


def test_ungrounded_response_yields_no_receipts():
    """An answer with no grounding must not look sourced."""
    response = SimpleNamespace(
        candidates=[SimpleNamespace(grounding_metadata=None)],
        text="I reckon it is about 83",
    )

    assert web_research._receipts(response) == []


def test_chunks_without_web_are_ignored():
    response = response_with([SimpleNamespace(web=None)])

    assert web_research._receipts(response) == []


def test_empty_query_is_rejected_without_calling_the_api():
    assert web_research.search_web("   ")["status"] == "ERROR"


def test_missing_api_key_reports_error_rather_than_raising(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = web_research.search_web("anything")

    assert result["status"] == "ERROR"
    assert "RuntimeError" in result["error"]
