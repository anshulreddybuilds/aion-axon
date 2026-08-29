from decimal import Decimal, InvalidOperation


def calculate(expression: str) -> dict:
    """
    Safe arithmetic tool for AXON.

    Supports basic arithmetic only:
    +, -, *, /, %, parentheses and decimal numbers.
    """

    if not expression or not expression.strip():
        return {
            "status": "ERROR",
            "error": "Expression cannot be empty.",
        }

    expression = expression.strip()

    allowed = set("0123456789.+-*/%() ")

    if any(character not in allowed for character in expression):
        return {
            "status": "ERROR",
            "error": "Expression contains unsupported characters.",
        }

    # `**` is not in this tool's documented operator set, but it slipped
    # through the character allowlist because `*` is allowed. Exponentiation
    # on ints is unbounded: `9**9**9` never returns, pinning a CPU and
    # exhausting memory. The eval() below is not the danger -- empty
    # builtins plus a digits-and-operators allowlist leave no way to name
    # anything -- but a capability that can be made to hang forever is a
    # denial-of-service reachable from any mission plan, and `calculator`
    # is the bootstrapped one every demo path runs.
    if "**" in expression:
        return {
            "status": "ERROR",
            "expression": expression,
            "error": (
                "Exponentiation is not supported. Supported operators: "
                "+, -, *, /, %, and parentheses."
            ),
        }

    # Second layer, deliberately crude: the allowlist above already bounds
    # what can appear, so this only exists to stop a pathological but
    # syntactically legal expression from being built out of permitted
    # characters alone. Not a substitute for the check above.
    if len(expression) > 200:
        return {
            "status": "ERROR",
            "error": "Expression is too long (200 character maximum).",
        }

    try:
        result = eval(
            expression,
            {"__builtins__": {}},
            {},
        )

        result = Decimal(str(result))

        return {
            "status": "SUCCESS",
            "expression": expression,
            "result": float(result),
        }

    except (ArithmeticError, InvalidOperation, SyntaxError, TypeError, ValueError) as exc:
        return {
            "status": "ERROR",
            "expression": expression,
            "error": str(exc),
        }
