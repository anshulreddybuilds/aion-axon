"""Sandbox /execute — the trust boundary actually running code.

Windows lacks the `resource` module, so these tests exercise the endpoint
through the app rather than asserting POSIX rlimits. The rlimits are
applied in the deployed Linux container and verified by the live probe.
"""
import importlib
import sys

import pytest
from fastapi.testclient import TestClient


def load_sandbox():
    sys.path.insert(0, "sandbox")
    module = importlib.import_module("main")
    return importlib.reload(module)


@pytest.fixture
def client():
    return TestClient(load_sandbox().app)


def run(client, code, test="", timeout=10):
    return client.post("/execute", json={
        "code": code, "test": test, "timeout_seconds": timeout,
    }).json()


def test_working_candidate_passes(client):
    body = run(client, "def add(a, b):\n    return a + b\n",
               "assert add(2, 3) == 5\nprint('OK')")

    assert body["status"] == "COMPLETED"
    assert body["passed"] is True
    assert "OK" in body["stdout"]


def test_failing_candidate_reports_failure_not_an_outage(client):
    """A broken candidate is a RESULT, not a sandbox error.

    If a crash read as an outage, SYNAPSE would retry a genuinely broken
    candidate forever instead of rejecting it.
    """
    body = run(client, "def add(a, b):\n    return a - b\n",
               "assert add(2, 3) == 5")

    assert body["status"] == "COMPLETED"
    assert body["passed"] is False
    assert body["exit_code"] != 0
    assert "AssertionError" in body["stderr"]


def test_syntax_error_is_reported(client):
    body = run(client, "def broken(:\n")

    assert body["passed"] is False
    assert "SyntaxError" in body["stderr"]


def test_oversized_code_is_rejected_before_running(client):
    module = load_sandbox()
    body = run(client, "x = 1\n" * module.MAX_CODE_CHARS)

    assert body["status"] == "REJECTED"
    assert body["passed"] is False


def test_candidate_cannot_read_the_parent_environment(client):
    """The child env is stripped even though the parent holds nothing."""
    body = run(
        client,
        "import os\n"
        "leaked = [k for k in os.environ if 'KEY' in k.upper()]\n"
        "print('LEAKED:', leaked)\n",
    )

    assert body["passed"] is True
    assert "LEAKED: []" in body["stdout"]


def test_output_is_truncated(client):
    module = load_sandbox()
    body = run(client, f"print('x' * {module.MAX_OUTPUT_CHARS * 2})")

    assert len(body["stdout"]) <= module.MAX_OUTPUT_CHARS
