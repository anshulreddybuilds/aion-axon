"""app/beastmode/state_machine.py -- transition validation + real mapping.

Part 1 proves the transition table itself (pure, table-driven). Part 2
proves the mapping functions against REAL AcquisitionRecord/install/
rollback output produced by the actual pipeline (mocking only the model
calls, same pattern as tests/test_beastmode_explain.py) -- this is what
answers "the state machine is just UI": these assertions run against
backend dicts, no frontend involved.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

from unittest.mock import patch

import pytest

from app.beastmode.state_machine import (
    InvalidTransition, from_acquisition_record, from_install_result,
    from_rollback_result, is_valid_transition, transition,
)
from app.memory.firestore_store import firestore_store
from app.synapse.engine import synapse
from app.synapse.generator import Candidate

# --- Part 1: the transition table, in isolation --------------------------

@pytest.mark.parametrize("current,next_", [
    ("REQUESTED", "MEMORY_CHECKED"),
    ("PLANNED", "GENERATING"),
    ("GENERATING", "SCREENING"),
    ("SCREENING", "SANDBOX_TESTING"),
    ("SANDBOX_TESTING", "EVALUATING"),
    ("EVALUATING", "AWAITING_APPROVAL"),
    ("AWAITING_APPROVAL", "APPROVED"),
    ("APPROVED", "INSTALLING"),
    ("INSTALLING", "INSTALLED"),
    ("INSTALLED", "EXECUTING"),
    ("EXECUTING", "COMPLETED"),
])
def test_valid_transitions_on_the_success_path(current, next_):
    assert transition(current, next_) == next_
    assert is_valid_transition(current, next_)


@pytest.mark.parametrize("current,next_", [
    # The exact adversarial examples from the directive.
    ("SCREENING", "APPROVED"),
    ("GENERATING", "INSTALLED"),
    ("QUARANTINED", "INSTALLED"),
])
def test_invalid_transitions_are_rejected(current, next_):
    assert not is_valid_transition(current, next_)
    with pytest.raises(InvalidTransition):
        transition(current, next_)


def test_terminal_failure_states_have_no_legal_forward_transition():
    for terminal in ("SAFETY_REJECTED", "SANDBOX_FAILED", "GENERATION_FAILED",
                      "POLICY_REFUSED", "APPROVAL_REJECTED", "INSTALL_FAILED",
                      "EXECUTION_FAILED"):
        assert not is_valid_transition(terminal, "INSTALLED")
        assert not is_valid_transition(terminal, "COMPLETED")


def test_unscored_evaluation_reaches_approval_never_auto_rejects():
    """Mirrors the doctrine locked in by
    tests/test_evaluator_unscored_escalates.py: UNSCORED must still be
    able to reach a human, never silently become a rejection."""
    assert is_valid_transition("EVALUATION_UNSCORED", "AWAITING_APPROVAL")
    assert not is_valid_transition("EVALUATION_UNSCORED", "EVALUATION_FAILED")


def test_unknown_state_names_are_rejected_not_silently_allowed():
    with pytest.raises(InvalidTransition):
        transition("MADE_UP_STATE", "INSTALLED")
    with pytest.raises(InvalidTransition):
        transition("REQUESTED", "MADE_UP_STATE")


# --- Part 2: mapping REAL pipeline output ---------------------------------

_CANDIDATE = Candidate(
    name="sm_test_cap", description="test capability",
    code='def sm_test_cap(x): return {"ok": True}',
    test='assert sm_test_cap(1)["ok"]', entrypoint="sm_test_cap", risk="LOW",
)
_PASSED_SANDBOX = {"status": "COMPLETED", "exit_code": 0, "passed": True, "stdout": "OK\n", "stderr": ""}
_FAILED_SANDBOX = {"status": "COMPLETED", "exit_code": 1, "passed": False, "stdout": "", "stderr": "boom"}


def setup_function():
    firestore_store.capabilities.clear()
    firestore_store.audit_events.clear()
    firestore_store.approvals.clear()


def test_a_real_awaiting_approval_record_maps_to_the_canonical_state():
    with patch("app.synapse.engine.generate_candidate", return_value=(_CANDIDATE, None)), \
         patch("app.synapse.engine.execute_in_sandbox", return_value=_PASSED_SANDBOX), \
         patch("app.synapse.engine.evaluate", return_value={
             "status": "SCORED", "score": 90, "verdict": "PASS", "reason": "fine",
         }):
        record = synapse.propose("a fake need")

    assert from_acquisition_record(record.to_dict()) == "AWAITING_APPROVAL"


def test_a_real_unscored_record_maps_to_the_unscored_canonical_state():
    with patch("app.synapse.engine.generate_candidate", return_value=(_CANDIDATE, None)), \
         patch("app.synapse.engine.execute_in_sandbox", return_value=_PASSED_SANDBOX), \
         patch("app.synapse.engine.evaluate", return_value={
             "status": "UNSCORED", "score": None, "verdict": None,
             "reason": "could not be parsed",
         }):
        record = synapse.propose("a fake need")

    assert from_acquisition_record(record.to_dict()) == "EVALUATION_UNSCORED"


def test_a_real_sandbox_rejection_maps_to_sandbox_failed():
    with patch("app.synapse.engine.generate_candidate", return_value=(_CANDIDATE, None)), \
         patch("app.synapse.engine.execute_in_sandbox", return_value=_FAILED_SANDBOX):
        record = synapse.propose("a fake need")  # allow_retry defaults False

    assert record.status == "REJECTED"
    assert from_acquisition_record(record.to_dict()) == "SANDBOX_FAILED"


def test_a_real_guardian_prescreen_refusal_maps_to_policy_refused():
    record = synapse.propose("read credentials from the runtime")
    assert record.status == "REFUSED"
    assert from_acquisition_record(record.to_dict()) == "POLICY_REFUSED"


def test_install_and_rollback_results_map_correctly():
    with patch("app.synapse.engine.generate_candidate", return_value=(_CANDIDATE, None)), \
         patch("app.synapse.engine.execute_in_sandbox", return_value=_PASSED_SANDBOX), \
         patch("app.synapse.engine.evaluate", return_value={
             "status": "SCORED", "score": 90, "verdict": "PASS", "reason": "fine",
         }):
        record = synapse.propose("a fake need")

    # Not yet approved.
    not_yet = synapse.install(_CANDIDATE.name)
    assert from_install_result(not_yet) == "AWAITING_APPROVAL"

    firestore_store.update_approval(record.approval_request_id, approved=True, decided_by="test")
    installed = synapse.install(_CANDIDATE.name)
    assert from_install_result(installed) == "INSTALLED"

    rolled_back = synapse.rollback(_CANDIDATE.name, "no longer needed")
    assert from_rollback_result(rolled_back) == "ROLLED_BACK"


def test_malformed_record_raises_rather_than_guessing():
    with pytest.raises(InvalidTransition):
        from_acquisition_record({"stage": "NONSENSE", "status": "WHAT"})
