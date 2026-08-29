"""Read-only probe: list the Gemini models this credential can actually see.

Prints model names only. Never prints the key, token, or credential.

Builds its client through app.google_client, the same construction every
real call site uses, so this probe exercises the auth path the
application will actually take. It previously hardcoded
`genai.Client(api_key=...)`, which meant it could only ever test the
API-key path -- so under a Vertex AI + ADC configuration it reported
"NO KEY SET" for a setup that works, and it could not have surfaced an
auth problem that affects the app but not itself.
"""
import os

from app.google_client import genai_available, genai_client


def main() -> None:
    if not genai_available():
        print(
            "NO GEMINI ACCESS CONFIGURED. Set GOOGLE_API_KEY or "
            "GEMINI_API_KEY, or configure Vertex AI "
            "(GOOGLE_GENAI_USE_VERTEXAI=true, GOOGLE_CLOUD_PROJECT, "
            "GOOGLE_CLOUD_LOCATION) with Application Default Credentials."
        )
        return

    # Which path the SDK will take, so a surprising result is
    # interpretable. Names the path only -- never the credential.
    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in ("true", "1"):
        print("AUTH PATH: Vertex AI + Application Default Credentials")
        print("PROJECT:", os.getenv("GOOGLE_CLOUD_PROJECT") or "(unset)")
        print("LOCATION:", os.getenv("GOOGLE_CLOUD_LOCATION") or "(unset)")
    else:
        which = "GOOGLE_API_KEY" if os.getenv("GOOGLE_API_KEY") else "GEMINI_API_KEY"
        print(f"AUTH PATH: Gemini Developer API (key from {which})")

    print()

    client = genai_client()

    # List EVERY model, not just gemini-*. Guessing an id is how the
    # Gemma evaluator ended up returning 404 at runtime.
    names = sorted(model.name for model in client.models.list())

    gemma = [name for name in names if "gemma" in name.lower()]

    print(f"TOTAL MODELS VISIBLE: {len(names)}")
    print()
    print(f"GEMMA MODELS: {len(gemma)}")

    for name in gemma:
        print("  ", name)

    if not gemma:
        print("   (none - this key has no Gemma access)")


if __name__ == "__main__":
    main()
