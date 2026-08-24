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


def _free_local_port() -> int:
    import socket as _socket
    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _local_http_server():
    """A real local HTTP server bound to 127.0.0.1 -- never a real
    external system, per the explicit instruction not to attack anything
    real. Returns (port, server, thread); caller must shut it down."""
    import http.server
    import threading

    class _OK(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"reached")

        def log_message(self, *a):
            pass  # keep test output quiet

    port = _free_local_port()
    server = http.server.HTTPServer(("127.0.0.1", port), _OK)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return port, server, thread


def test_network_egress_via_the_real_execute_endpoint_as_deployed_today():
    """Calls /execute directly with EXACTLY the child_env sandbox/main.py
    actually uses today -- bypassing AST entirely, to isolate what the
    sandbox process layer alone contributes.

    RESULT ON THIS MACHINE: the connection attempt fails, but NOT because
    of any network policy -- it fails with Windows error 10106 ("service
    provider could not be loaded"), because the real child_env has no
    SYSTEMROOT and Winsock cannot initialize without it. This is a
    Windows-only quirk of this stripped environment, not a deliberate
    control, and it says nothing about whether the same stripped env
    would block a connection on the actual deployed Linux container
    (POSIX sockets have no such requirement). See the next test for the
    isolated, platform-neutral answer to the real question.
    """
    port, server, thread = _local_http_server()
    try:
        response = client.post("/execute", json={
            "code": (
                "import urllib.request\n"
                "def f():\n"
                f"    return urllib.request.urlopen('http://127.0.0.1:{port}', timeout=5).read()\n"
            ),
            "test": "print(f().decode())\n",
        })
    finally:
        server.shutdown()
        thread.join(timeout=5)

    body = response.json()
    print(f"\nSANDBOX NETWORK EGRESS as deployed today (Windows dev machine): {body}")
    assert response.status_code == 200  # the call itself must not error


def test_network_egress_is_not_actually_blocked_by_the_sandbox_process_layer():
    """The real finding, isolated from the Windows Winsock artifact
    above: replicate sandbox/main.py's OWN subprocess call (-I flag,
    same stripped env, same real subprocess) with exactly one addition
    -- SYSTEMROOT, required only for Windows socket initialization and
    irrelevant on POSIX -- to answer the actual question the previous
    test's platform quirk obscured: does the sandbox's stripped
    environment, on its own, prevent a network connection?

    HONEST RESULT: no. Confirmed by first connecting to a closed local
    port (proves Winsock initializes and produces a real connection
    error, not another 10106) and then to the real local test server
    (proves data actually round-trips). No VPC egress rule or firewall
    is configured anywhere in this repository (checked sandbox/Dockerfile
    and docs/deployment/ -- neither mentions network policy), so this is
    the accurate current answer FOR THIS MACHINE: the sandbox process
    layer provides no network isolation on its own. AST screening
    (app/synapse/safety_screen.py, covering socket/urllib/http/ftplib/
    smtplib/xmlrpc/telnetlib/asyncio as of this session) is the ONLY
    control against this vector today -- a blocklist, which is
    inherently incomplete against imports not yet enumerated. This is a
    real, documented gap, not a claim of safety.

    Still cannot prove Cloud Run's actual VPC/egress configuration,
    which is GCP infrastructure this session has no way to inspect.
    """
    import os
    import subprocess
    import sys
    import tempfile

    def _run(code: str, timeout: float = 5) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as workdir:
            path = os.path.join(workdir, "candidate.py")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(code)
            child_env = {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "HOME": workdir,
                "PYTHONDONTWRITEBYTECODE": "1",
                # The one addition versus sandbox/main.py's real
                # child_env -- Windows-only, required for Winsock, does
                # not exist as a concept on POSIX.
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            }
            return subprocess.run(
                [sys.executable, "-I", path], cwd=workdir, env=child_env,
                capture_output=True, text=True, timeout=timeout,
            )

    # Step 1: prove sockets initialize at all with this env (a real
    # connection-refused error, not a Winsock provider-load failure).
    closed_port = _free_local_port()  # freed immediately -- nothing listens
    refusal = _run(
        "import urllib.request\n"
        f"urllib.request.urlopen('http://127.0.0.1:{closed_port}', timeout=2).read()\n"
    )
    assert "10106" not in refusal.stderr, (
        "Winsock still failed to initialize -- SYSTEMROOT alone did not "
        "neutralize the platform artifact; the result below is not yet "
        "meaningful:\n" + refusal.stderr
    )

    # Step 2: the real question -- does data actually round-trip.
    port, server, thread = _local_http_server()
    try:
        completed = _run(
            "import urllib.request\n"
            f"print(urllib.request.urlopen('http://127.0.0.1:{port}', timeout=5).read().decode())\n"
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)

    reached = "reached" in completed.stdout
    print(f"\nSANDBOX NETWORK EGRESS, Winsock artifact neutralized: "
          f"{'REACHED the local test server' if reached else 'did not reach it'} "
          f"(stdout={completed.stdout!r}, stderr={completed.stderr[-200:]!r})")
    assert reached, (
        "If this ever fails, that is GOOD NEWS: it means something now "
        "blocks the connection this test previously proved was open. "
        "Investigate and update this docstring before treating it as a "
        "regression."
    )
