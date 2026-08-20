"""SYNAPSE acquisition loop.

The properties under test are the governance ones, not the happy path:
nothing installs without a real approval, a dangerous candidate never
reaches the sandbox, and a sandbox outage never reads as a pass.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

import pytest  # noqa: E402

from app.capabilities.registry import registry  # noqa: E402
from app.memory.firestore_store import firestore_store  # noqa: E402
from app.synapse import engine as engine_module  # noqa: E402
from app.synapse.engine import synapse  # noqa: E402
from app.synapse.generator import Candidate  # noqa: E402
from app.synapse.safety_screen import screen  # noqa: E402

SAFE_CODE = (
    "def fx_normalize(amount, rate):\n"
    "    try:\n"
    "        return {'status': 'SUCCESS',\n"
    "                'value': float(amount) * float(rate)}\n"
    "    except ValueError:\n"
    "        return {'status': 'ERROR', 'error': 'bad input'}\n"
)


@pytest.fixture(autouse=True)
def clean():
    # The registry is a module-level singleton, so an install in one test
    # leaks into the next unless it is removed.
    firestore_store.capabilities.clear()
    firestore_store.approvals.clear()
    firestore_store.evolution_events.clear()
    registry.unregister("fx_normalize")
    yield
    firestore_store.capabilities.clear()
    registry.unregister("fx_normalize")


def good_candidate() -> Candidate:
    return Candidate(
        name="fx_normalize",
        description="Converts an amount between currencies at a given rate.",
        risk="LOW",
        code=SAFE_CODE,
        test="assert fx_normalize('10', '2')['value'] == 20.0\nprint('OK')",
        entrypoint="fx_normalize",
    )


def patch_pipeline(monkeypatch, candidate=None, tests=None, evaluation=None,
                   research=None):
    monkeypatch.setattr(
        engine_module, "search_web",
        lambda q: research or {
            "status": "DEGRADED", "grounded": False, "sources": [],
            "findings": "notes", "source_count": 0,
        },
    )
    monkeypatch.setattr(
        engine_module, "generate_candidate",
        lambda need, notes=None: (candidate or good_candidate(), None),
    )
    monkeypatch.setattr(
        engine_module, "execute_in_sandbox",
        lambda code, test="", timeout_seconds=10: tests or {
            "status": "COMPLETED", "passed": True, "stdout": "OK",
            "stderr": "", "exit_code": 0,
        },
    )
    monkeypatch.setattr(
        engine_module, "evaluate",
        lambda *a, **k: evaluation or {
            "status": "SCORED", "score": 80, "verdict": "PASS",
            "reason": "solid", "model": "gemma-3-27b-it",
        },
    )


# --- The refusal path -----------------------------------------------------

def test_credential_capability_is_refused_before_any_work(monkeypatch):
    """The doorway check: refuse before spending tokens researching it."""
    called = []
    monkeypatch.setattr(
        engine_module, "search_web",
        lambda q: called.append(q) or {},
    )

    record = synapse.propose(
        "a capability that can read credentials from the runtime"
    )

    assert record.status == "REFUSED"
    assert record.stage == "GUARDIAN_PRESCREEN"
    assert record.guardian["policy_id"] == "G-04"
    assert called == [], "research ran on a request that should be refused"


# --- Safety screen --------------------------------------------------------

def test_safety_screen_blocks_dangerous_imports():
    result = screen("import os\ndef f():\n    return os.environ\n")

    assert result.safe is False
    assert any("os" in finding for finding in result.findings)


def test_safety_screen_blocks_exec_and_dunder():
    assert screen("def f():\n    exec('1')\n").safe is False
    assert screen("def f():\n    return ().__class__\n").safe is False


def test_safety_screen_allows_ordinary_computation():
    assert screen(SAFE_CODE).safe is True


def test_unsafe_candidate_never_reaches_the_sandbox(monkeypatch):
    reached = []

    patch_pipeline(monkeypatch, candidate=Candidate(
        name="sneaky", description="reads env", risk="LOW",
        code="import os\ndef sneaky():\n    return os.environ\n",
        test="print('OK')", entrypoint="sneaky",
    ))
    monkeypatch.setattr(
        engine_module, "execute_in_sandbox",
        lambda *a, **k: reached.append(1) or {"passed": True},
    )

    record = synapse.propose("read the environment")

    assert record.status == "REJECTED"
    assert record.stage == "SAFETY_SCREEN"
    assert reached == []


# --- Sandbox outcomes -----------------------------------------------------

def test_failing_candidate_is_rejected(monkeypatch):
    patch_pipeline(monkeypatch, tests={
        "status": "COMPLETED", "passed": False,
        "stderr": "AssertionError", "stdout": "", "exit_code": 1,
    })

    record = synapse.propose("normalize currency")

    assert record.status == "REJECTED"
    assert record.stage == "SANDBOX_TEST"


def test_sandbox_outage_blocks_rather_than_passes(monkeypatch):
    """Installing an untested candidate because the tester was down is the
    worst available outcome."""
    patch_pipeline(monkeypatch, tests={
        "status": "UNREACHABLE", "passed": False, "reason": "timeout",
    })

    record = synapse.propose("normalize currency")

    assert record.status == "BLOCKED"
    assert "never tested" in record.reason


# --- Evaluator ------------------------------------------------------------

def test_low_evaluator_score_rejects(monkeypatch):
    patch_pipeline(monkeypatch, evaluation={
        "status": "SCORED", "score": 20, "verdict": "FAIL",
        "reason": "only trivial input tested",
    })

    record = synapse.propose("normalize currency")

    assert record.status == "REJECTED"
    assert "below the" in record.reason


def test_unscored_evaluation_still_reaches_the_owner(monkeypatch):
    """UNSCORED must neither silently pass nor silently block."""
    patch_pipeline(monkeypatch, evaluation={
        "status": "UNSCORED", "score": None, "verdict": None,
        "reason": "Evaluator unavailable",
    })

    record = synapse.propose("normalize currency")

    assert record.status == "AWAITING_APPROVAL"
    assert record.evaluation["status"] == "UNSCORED"


# --- Approval is the wall -------------------------------------------------

def test_pipeline_stops_at_approval(monkeypatch):
    patch_pipeline(monkeypatch)

    record = synapse.propose("normalize currency")

    assert record.status == "AWAITING_APPROVAL"
    assert record.approval_request_id
    assert registry.is_implemented("fx_normalize") is False


def test_install_refuses_without_approval(monkeypatch):
    patch_pipeline(monkeypatch)
    synapse.propose("normalize currency")

    result = synapse.install("fx_normalize")

    assert result["status"] == "APPROVAL_REQUIRED"
    assert registry.is_implemented("fx_normalize") is False


def test_install_after_approval_emits_an_evolution_event(monkeypatch):
    patch_pipeline(monkeypatch)
    record = synapse.propose("normalize currency")

    firestore_store.update_approval(
        record.approval_request_id, approved=True, decided_by="anshul",
    )

    result = synapse.install("fx_normalize")

    assert result["status"] == "INSTALLED"
    assert registry.is_implemented("fx_normalize") is True

    events = firestore_store.list_evolution_events()
    assert len(events) == 1

    event = events[0]
    assert event["capability_id"] == "fx_normalize"
    assert event["approver"] == "anshul"
    for key in ("before", "change", "reason", "after"):
        assert event[key]


def test_rejected_approval_does_not_install(monkeypatch):
    patch_pipeline(monkeypatch)
    record = synapse.propose("normalize currency")

    firestore_store.update_approval(
        record.approval_request_id, approved=False, decided_by="anshul",
    )

    result = synapse.install("fx_normalize")

    assert result["status"] == "APPROVAL_REQUIRED"
    assert registry.is_implemented("fx_normalize") is False


def test_passport_records_the_whole_chain(monkeypatch):
    patch_pipeline(monkeypatch)
    record = synapse.propose("normalize currency")

    passport = firestore_store.get_capability("fx_normalize")["passport"]

    assert passport["need"]
    assert passport["research"] is not None
    assert passport["candidate"]["name"] == "fx_normalize"
    assert passport["safety"]["safe"] is True
    assert passport["tests"]["passed"] is True
    assert passport["evaluation"]["status"] == "SCORED"
    assert passport["approval_request_id"] == record.approval_request_id


def test_rollback_disables_and_records_why(monkeypatch):
    """ROLLBACK is the last step of the Skill Passport."""
    patch_pipeline(monkeypatch)
    record = synapse.propose("normalize currency")

    firestore_store.update_approval(
        record.approval_request_id, approved=True, decided_by="anshul",
    )
    synapse.install("fx_normalize")

    assert registry.is_implemented("fx_normalize") is True

    result = synapse.rollback("fx_normalize", "produced wrong totals")

    assert result["status"] == "ROLLED_BACK"
    assert registry.is_implemented("fx_normalize") is False

    stored = firestore_store.get_capability("fx_normalize")
    assert stored["state"] == "DISABLED"
    assert stored["rollback_reason"] == "produced wrong totals"


def test_rollback_keeps_the_original_acquisition_event(monkeypatch):
    """Erasing the install would make the chain of custody a story about
    successes only."""
    patch_pipeline(monkeypatch)
    record = synapse.propose("normalize currency")

    firestore_store.update_approval(
        record.approval_request_id, approved=True, decided_by="anshul",
    )
    synapse.install("fx_normalize")
    synapse.rollback("fx_normalize", "wrong totals")

    events = firestore_store.list_evolution_events()

    assert len(events) == 2
    assert any(not e.get("rollback") for e in events)
    assert any(e.get("rollback") for e in events)
