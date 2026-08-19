"""The sandbox must hold zero credentials. That claim is tested, not asserted."""
import importlib
import sys

from fastapi.testclient import TestClient


def load_sandbox():
    sys.path.insert(0, "sandbox")
    module = importlib.import_module("main")
    return importlib.reload(module)


def test_scan_reports_zero_on_clean_environment(monkeypatch):
    module = load_sandbox()

    for name in list(module.os.environ):
        if any(m in name.upper() for m in module.CREDENTIAL_MARKERS):
            monkeypatch.delenv(name, raising=False)

    assert module.scan_environment() == []
    assert module.env_proof()["verdict"] == "ZERO_CREDENTIALS"


def test_scan_detects_a_planted_credential(monkeypatch):
    """Prove the check bites -- a scan that can never fail proves nothing."""
    module = load_sandbox()

    monkeypatch.setenv("SOME_API_KEY", "planted-value")

    found = module.scan_environment()

    assert "SOME_API_KEY" in found
    assert module.env_proof()["verdict"] == "CREDENTIALS_PRESENT"


def test_proof_never_leaks_values(monkeypatch):
    module = load_sandbox()

    monkeypatch.setenv("SOME_API_KEY", "planted-value")

    assert "planted-value" not in str(module.env_proof())


def test_env_proof_endpoint(monkeypatch):
    module = load_sandbox()

    for name in list(module.os.environ):
        if any(m in name.upper() for m in module.CREDENTIAL_MARKERS):
            monkeypatch.delenv(name, raising=False)

    client = TestClient(module.app)

    body = client.get("/env-proof").json()

    assert body["service"] == "aion-sandbox"
    assert body["verdict"] == "ZERO_CREDENTIALS"
