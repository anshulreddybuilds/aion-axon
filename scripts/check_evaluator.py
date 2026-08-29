"""Probe the Gemma evaluator against a known-good and a known-bad candidate.

Verifies the pinned model id actually answers, and that it can tell a real
capability from a broken one. Two calls, no deploy needed.

A model that scores everything highly is worse than no evaluator, so the
second case matters more than the first.
"""
from app.synapse.evaluator import MODEL, evaluate

GOOD_CODE = (
    "def convert(amount, rate):\n"
    "    try:\n"
    "        return {'status': 'SUCCESS', 'value': float(amount) * float(rate)}\n"
    "    except ValueError:\n"
    "        return {'status': 'ERROR', 'error': 'bad input'}\n"
)

BAD_CODE = (
    "def convert(amount, rate):\n"
    "    return {'status': 'SUCCESS', 'value': 42}\n"
)


def show(label: str, result: dict) -> None:
    print(f"--- {label} ---")
    print("  status :", result.get("status"))
    print("  score  :", result.get("score"))
    print("  verdict:", result.get("verdict"))
    print("  reason :", (result.get("reason") or "")[:160])
    print()


def main() -> None:
    print(f"EVALUATOR MODEL: {MODEL}\n")

    show("GOOD candidate (real conversion, handles bad input)", evaluate(
        "convert_currency_amount",
        "Converts an amount using an exchange rate.",
        GOOD_CODE,
        {"passed": True, "stdout": "OK", "stderr": ""},
    ))

    show("BAD candidate (ignores inputs, returns a constant)", evaluate(
        "convert_currency_amount",
        "Converts an amount using an exchange rate.",
        BAD_CODE,
        {"passed": True, "stdout": "OK", "stderr": ""},
    ))


if __name__ == "__main__":
    main()
