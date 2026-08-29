"""The calculator must not be turnable into a denial-of-service.

`eval()` here was never a code-execution risk -- empty builtins plus a
digits-and-operators character allowlist leave no way to name anything.
The reachable danger was resource exhaustion: `**` passed the allowlist
because `*` is allowed, and integer exponentiation is unbounded, so
`9**9**9` never returns. `calculator` is the bootstrapped capability
every demo path runs, and any mission plan can supply its argument.

The timeout in the DoS test is the assertion: before the fix this call
did not return at all.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

import multiprocessing  # noqa: E402

import pytest  # noqa: E402

from app.tools.calculator import calculate  # noqa: E402


def test_the_demo_path_is_untouched():
    """50 + 50 must still be 100.0 -- the fix must not cost the happy path."""
    result = calculate("50 + 50")

    assert result["status"] == "SUCCESS"
    assert result["result"] == 100.0


@pytest.mark.parametrize(
    "expression, expected",
    [
        ("2 * 20", 40.0),
        ("(1250 * 1.18)", 1475.0),
        ("10 % 3", 1.0),
        ("7 / 2", 3.5),
        ("100 - 1", 99.0),
    ],
)
def test_supported_operators_still_work(expression, expected):
    result = calculate(expression)

    assert result["status"] == "SUCCESS"
    assert result["result"] == expected


@pytest.mark.parametrize(
    "expression",
    ["9**9**9", "2**999999999", "2 ** 64", "9**9"],
)
def test_exponentiation_is_refused_not_evaluated(expression):
    """Refused as unsupported -- including the small, harmless-looking
    ones. Allowing `2**64` while blocking `9**9**9` would mean guessing
    which exponents are safe, and the operator is undocumented anyway."""
    result = calculate(expression)

    assert result["status"] == "ERROR"
    assert "Exponentiation is not supported" in result["error"]


def test_over_long_expression_is_refused():
    result = calculate("1+" * 500 + "1")

    assert result["status"] == "ERROR"
    assert "too long" in result["error"]


def _run(expression, queue):
    queue.put(calculate(expression))


def test_the_dos_expression_returns_promptly():
    """Runs in a child process with a hard join timeout.

    Before the fix this expression pinned a CPU indefinitely; asserting
    inside this process would have hung the suite instead of failing it.
    """
    queue = multiprocessing.Queue()
    child = multiprocessing.Process(target=_run, args=("9**9**9", queue))
    child.start()
    child.join(timeout=10)

    if child.is_alive():
        child.terminate()
        child.join()
        pytest.fail(
            "calculate('9**9**9') did not return within 10s -- the "
            "exponentiation DoS is reachable again."
        )

    assert queue.get_nowait()["status"] == "ERROR"
