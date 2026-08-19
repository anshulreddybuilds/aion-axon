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
