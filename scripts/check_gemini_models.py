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

    names = [m.name for m in client.models.list() if "gemini" in m.name]

    print(f"VISIBLE GEMINI MODELS: {len(names)}")
    for name in sorted(names):
        print(" ", name)


if __name__ == "__main__":
    main()
