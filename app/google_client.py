"""Shared google-genai client construction for every real Gemini/Vertex
call site (SYNAPSE's generator/evaluator, web_research).

google-genai's own `Client` already resolves Vertex AI + Application
Default Credentials automatically -- with NO explicit arguments -- from
`GOOGLE_GENAI_USE_VERTEXAI` / `GOOGLE_CLOUD_PROJECT` /
`GOOGLE_CLOUD_LOCATION` whenever no `api_key` is passed (confirmed by
reading `google.genai._api_client.BaseApiClient.__init__` in the
installed google-genai==2.18.1: it reads exactly those three env vars
and falls back to `google.auth.default()` for credentials). The bug
this file fixes was never a missing capability -- every call site
across this codebase raised RuntimeError before that resolution logic
ever ran, because an API key was the only auth path each one checked
for. google.adk.models.Gemini's own `api_client` property constructs
the same `Client` the same way, so the ADK-driven planner agents
already get Vertex+ADC support for free; nothing there needed changing.

Preserves the existing, intentional API-key compatibility path exactly
as before -- GOOGLE_API_KEY/GEMINI_API_KEY still works, with the same
precedence the SDK itself already gives it. No plaintext secret or ADC
credential is read, stored, or logged by this module; both auth paths
are resolved entirely inside google-genai/google-auth.
"""
import os

from google import genai


def genai_available() -> bool:
    """True when either a Gemini API key or a Vertex AI configuration
    is present -- the two auth paths genai.Client() itself supports.

    Checking `GOOGLE_GENAI_USE_VERTEXAI` here (rather than, say,
    trying to construct a client and seeing if it raises) mirrors
    exactly what the SDK itself keys its own vertexai/api-key decision
    on, without duplicating its full resolution logic or triggering a
    real ADC lookup just to answer "would this work at all".
    """
    has_api_key = bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
    uses_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in ("true", "1")
    return has_api_key or uses_vertex


def genai_client() -> genai.Client:
    """Build the one real client every generation/evaluation/research
    call site uses.

    Deliberately called with NO arguments: genai.Client() already reads
    GOOGLE_API_KEY/GEMINI_API_KEY, GOOGLE_GENAI_USE_VERTEXAI,
    GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION from the environment
    itself, and falls back to Application Default Credentials for
    Vertex AI when no key is set. Passing those values through
    explicitly here would only risk drifting out of sync with the
    SDK's own (already correct) precedence rules between them.
    """
    if not genai_available():
        raise RuntimeError(
            "No Gemini access configured -- set GOOGLE_API_KEY or "
            "GEMINI_API_KEY, or configure Vertex AI (GOOGLE_GENAI_USE_VERTEXAI=true, "
            "GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION) with Application "
            "Default Credentials (`gcloud auth application-default login`)."
        )

    return genai.Client()
