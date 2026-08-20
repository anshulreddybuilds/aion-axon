"""Read-only probe: list the Gemini models this API key can actually see.

Prints model names only. Never prints the key itself.
"""
import os

import google.genai as genai


def main() -> None:
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

    if not key:
        print("NO KEY SET (checked GOOGLE_API_KEY and GEMINI_API_KEY)")
        return

    client = genai.Client(api_key=key)

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
