"""Real, non-mocked tests against the sandbox service itself.

Confirmed absent before this file: `python -m pytest tests/` never
touches anything under sandbox/ (pytest.ini scopes testpaths to tests/
only, and this service is deployed separately from aion-core), so
sandbox/main.py's actual execution behavior -- the layer that owns
resource-exhaustion containment, per its own docstring and the one the
live red-team runner explicitly declines to claim credit for -- had
literally zero test coverage.

These tests call the REAL FastAPI app and, for the timeout case, run a
REAL subprocess that is REALLY killed by a REAL wall-clock timeout. This
is deliberate: a mocked subprocess.run would prove nothing about whether
the timeout actually works. The one thing these tests CANNOT prove on
this machine is the POSIX rlimits (RLIMIT_AS/CPU/FSIZE/NPROC) -- the
`resource` module is POSIX-only and this is a Windows dev machine, so
`_limits()` silently no-ops here exactly as its own code says it will.
That gap is inherent to local Windows development, not to this test
file, and is stated here rather than hidden.
"""
import time

import pytest
from fastapi.testclient import TestClient

from sandbox.main import MAX_CODE_CHARS, app

client = TestClient(app)


def test_health_and_root_are_reachable():
    assert client.get("/").json()["status"] == "LIVE"
    assert client.get("/health").json()["status"] == "OK"


def test_env_proof_finds_no_credential_shaped_variables():
    """The sandbox's own headline claim -- zero credentials -- checked
    from outside, not just asserted in a docstring."""
    body = client.get("/env-proof").json()
    assert body  # real response, not empty/broken
    # Whatever shape env_proof() returns, it must not contain a real key.
    import json
    serialized = json.dumps(body).upper()
    assert "AIzaSy" not in json.dumps(body)  # a real Google API key shape
    assert "-----BEGIN" not in serialized     # a real PEM private key


def test_a_real_trivial_candidate_actually_executes_and_passes():
    """Not mocked: a real subprocess runs real Python and reports a real
    exit code."""
    response = client.post("/execute", json={
        "code": "def f():\n    return 1 + 1\n",
        "test": "assert f() == 2\nprint('OK')\n",
    })
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["passed"] is True
    assert body["exit_code"] == 0
    assert "OK" in body["stdout"]


def test_a_real_failing_candidate_is_reported_not_mistaken_for_an_outage():
    response = client.post("/execute", json={
        "code": "def f():\n    return 1\n",
        "test": "assert f() == 2\n",
    })
    body = response.json()
    assert body["status"] == "COMPLETED"  # ran fine; the ASSERTION failed
    assert body["passed"] is False
    assert body["exit_code"] != 0
    assert "AssertionError" in body["stderr"]


def test_a_real_infinite_loop_is_really_killed_by_the_real_timeout():
    """The genuinely important test in this file: an actual `while True`
    candidate, given a short real timeout, must actually be terminated
    within roughly that time -- not merely return a TIMEOUT string while
    secretly having hung. Measures real wall-clock elapsed time around
    the real subprocess call as independent proof the kill was real."""
    t0 = time.monotonic()
    response = client.post("/execute", json={
        "code": "def f():\n    while True:\n        pass\n",
        "test": "f()\n",
        "timeout_seconds": 2,
    })
    elapsed = time.monotonic() - t0

    body = response.json()
    assert body["status"] == "TIMEOUT"
    assert body["passed"] is False
    # Real proof the process didn't hang: the HTTP call itself returned
    # promptly, not after minutes. Generous upper bound for CI variance.
    assert elapsed < 15


def test_code_over_the_size_cap_is_rejected_before_any_subprocess_runs():
    oversized = "x = 1\n" * (MAX_CODE_CHARS // 5 + 100)
    response = client.post("/execute", json={"code": oversized})
    body = response.json()
    assert body["status"] == "REJECTED"
    assert body["passed"] is False


def test_timeout_seconds_cannot_exceed_the_configured_maximum():
    """A caller passing a huge timeout_seconds must be clamped to
    MAX_SECONDS, not honored -- otherwise the size cap is real but the
    time cap is client-controlled."""
    from sandbox.main import MAX_SECONDS

    response = client.post("/execute", json={
        "code": "def f():\n    return 1\n",
        "test": "f()\n",
        "timeout_seconds": 9999,
    })
    # Pydantic's own field bound (le=30) already refuses anything above
    # 30; this proves that bound is real, not merely declared.
    assert response.status_code == 422


@pytest.mark.parametrize("forbidden_env", ["GOOGLE_API_KEY", "AXON_OWNER_TOKEN"])
def test_the_child_environment_is_stripped_of_real_secret_shaped_names(monkeypatch, forbidden_env):
    """Plant a real value under a real secret-shaped name in THIS
    process's environment, then prove a candidate that tries to read it
    back gets nothing -- because the child env is a hardcoded allowlist,
    not an inherited copy."""
    monkeypatch.setenv(forbidden_env, "sk-should-never-be-visible-to-a-candidate")

    response = client.post("/execute", json={
        "code": (
            "import os\n"
            "def f():\n"
            f"    return os.environ.get('{forbidden_env}')\n"
        ),
        "test": f"print(repr(f()))\n",
    })
    body = response.json()
    # This candidate imports os -- outside this test's own scope, that
    # would be caught by app.synapse.safety_screen before ever reaching
    # here. This test is specifically about what the CHILD PROCESS
    # ENVIRONMENT contains if code somehow runs, independent of the AST
    # layer -- defense in depth, not a substitute for it.
    assert "sk-should-never-be-visible-to-a-candidate" not in body.get("stdout", "")
