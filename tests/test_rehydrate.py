"""Acquired capabilities must survive a restart.

Cloud Run scales to zero. Without rehydration, a capability acquired at
09:26 is gone by 09:40 and the whole acquisition story is an illusion that
lasts one container.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

import pytest  # noqa: E402

from app.capabilities.registry import registry  # noqa: E402
from app.capabilities.rehydrate import rehydrate_capabilities  # noqa: E402
from app.memory.firestore_store import firestore_store  # noqa: E402

CODE = (
    "def double(value):\n"
    "    return {'status': 'SUCCESS', 'value': float(value) * 2}\n"
)


@pytest.fixture(autouse=True)
def clean():
    firestore_store.capabilities.clear()
    firestore_store.install_claims.clear()
    registry.unregister("restored_skill")
    yield
    firestore_store.capabilities.clear()
    firestore_store.install_claims.clear()
    registry.unregister("restored_skill")


def store(name="restored_skill", state="READY", implemented=True, code=CODE):
    firestore_store.save_capability(name, {
        "name": name,
        "description": "doubles a number",
        "risk": "LOW",
        "state": state,
        "implemented": implemented,
        "passport": {
            "candidate": {
                "name": name,
                "description": "doubles a number",
                "risk": "LOW",
                "code": code,
                "entrypoint": "double",
            },
        },
    })


def test_ready_capability_is_restored():
    store()

    assert registry.is_implemented("restored_skill") is False

    result = rehydrate_capabilities()

    assert "restored_skill" in result["restored"]
    assert registry.is_implemented("restored_skill") is True


def test_rolled_back_capability_is_not_restored():
    """A capability the owner disabled must stay disabled across restarts."""
    store(state="DISABLED", implemented=False)

    result = rehydrate_capabilities()

    assert result["restored"] == []
    assert registry.is_implemented("restored_skill") is False


def test_capability_awaiting_approval_is_not_restored():
    """Restarting must not install something never approved."""
    store(state="VALIDATING", implemented=False)

    rehydrate_capabilities()

    assert registry.is_implemented("restored_skill") is False


def test_record_without_code_is_skipped_not_registered():
    """Registering something unrunnable would fail on first call instead."""
    store(code="")

    result = rehydrate_capabilities()

    assert result["restored"] == []
    assert any(s["name"] == "restored_skill" for s in result["skipped"])
    assert registry.is_implemented("restored_skill") is False


def test_hand_written_seeds_are_left_alone():
    """Rehydration must not replace a real implementation with a proxy."""
    import app.capabilities.bootstrap  # noqa: F401

    rehydrate_capabilities()

    tool = registry.describe("calculator")

    assert tool.implemented
    assert tool.function.__name__ == "calculate"


def test_rehydration_never_raises_on_a_broken_store(monkeypatch):
    """Losing a capability is bad; refusing to boot is worse."""
    monkeypatch.setattr(
        firestore_store, "list_capabilities",
        lambda: (_ for _ in ()).throw(RuntimeError("firestore down")),
    )

    result = rehydrate_capabilities()

    assert result["restored"] == []
    assert "firestore down" in result["error"]


def test_a_rehydrated_capability_genuinely_executes_not_just_registers(
    monkeypatch,
):
    """Every prior test here (and the original coverage this file
    shipped with) only ever checked `registry.is_implemented(name)` --
    which proves the name exists in the registry, not that CALLING it
    actually works. That is exactly the class of gap that produced
    BUG-005/006/007 elsewhere in this project: something that looks
    wired up but was never actually invoked. Proven here by real-
    executing the code the sandbox proxy would run (the technique this
    session already established for testing acquisition end-to-end
    without network access to the real sandbox service) and calling the
    rehydrated function for real.
    """
    import contextlib
    import io

    import app.synapse.engine as engine_module

    store()

    def real_exec_sandbox(code, test="", timeout_seconds=10):
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                exec(code + "\n" + test, {})
            return {
                "status": "COMPLETED", "passed": True,
                "stdout": buf.getvalue(), "stderr": "", "exit_code": 0,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "COMPLETED", "passed": False,
                "stdout": buf.getvalue(), "stderr": str(exc), "exit_code": 1,
            }

    monkeypatch.setattr(engine_module, "execute_in_sandbox", real_exec_sandbox)

    result = rehydrate_capabilities()
    assert "restored_skill" in result["restored"]

    tool = registry.get("restored_skill")
    outcome = tool.function("21")

    assert outcome == {"status": "SUCCESS", "value": 42.0}, (
        f"rehydrated capability registered but did not actually execute "
        f"correctly: {outcome}"
    )
