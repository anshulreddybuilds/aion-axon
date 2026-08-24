"""A formal capability lifecycle, layered read-only over the real pipeline.

This does NOT replace app.synapse.engine's status strings -- it is a
compatibility mapping FROM them, plus an explicit, testable transition
table. synapse.propose()/install()/rollback() are untouched; this module
only interprets what they already return.

Two things this module can do:
  1. `from_acquisition_record(record)` / `from_install_result(result)` /
     `from_rollback_result(result)` -- map a REAL dict the pipeline
     already produced to one canonical state name.
  2. `transition(current, next_)` -- validate whether a move between two
     canonical states is legal, against an explicit table. This is what
     answers "is the state machine just UI?" -- no: an illegal pair
     raises InvalidTransition regardless of what any frontend renders.

Two canonical states extend the directive's list, each because the real
pipeline distinguishes something the shorter list collapses:
  - POLICY_REFUSED: Guardian refusing an install (pre- or post-generation)
    is not the same fact as AST static analysis rejecting generated code
    (SAFETY_REJECTED) -- collapsing them would hide WHICH control fired.
  - SANDBOX_UNREACHABLE: an infrastructure outage is not a failing
    candidate (see app/synapse/engine.py's own comment on this exact
    point) -- collapsing it into SANDBOX_FAILED would misreport "the
    generated code is bad" when the truth is "the tester was down".
"""
from __future__ import annotations

from typing import Any

# --- canonical states -------------------------------------------------

SUCCESS_PATH = (
    "REQUESTED", "MEMORY_CHECKED", "PLANNED", "GENERATING", "SCREENING",
    "SANDBOX_TESTING", "EVALUATING", "AWAITING_APPROVAL", "APPROVED",
    "INSTALLING", "INSTALLED", "EXECUTING", "COMPLETED",
)

FAILURE_STATES = (
    "GENERATION_FAILED", "SAFETY_REJECTED", "EVALUATION_FAILED",
    "EVALUATION_UNSCORED", "SANDBOX_FAILED", "SANDBOX_UNREACHABLE",
    "APPROVAL_REJECTED", "INSTALL_FAILED", "EXECUTION_FAILED",
    "QUARANTINED", "ROLLED_BACK", "POLICY_REFUSED",
)

CANONICAL_STATES = frozenset(SUCCESS_PATH + FAILURE_STATES)

TERMINAL_STATES = frozenset(FAILURE_STATES) | {"COMPLETED", "ROLLED_BACK"}


class InvalidTransition(ValueError):
    pass


# --- transition table ---------------------------------------------------
#
# Each key's value is the set of canonical states it may legally move to.
# A pair not present here is illegal, full stop -- there is no default
# "allow" path.

_TRANSITIONS: dict[str, frozenset[str]] = {
    "REQUESTED": frozenset({"MEMORY_CHECKED", "POLICY_REFUSED"}),
    "MEMORY_CHECKED": frozenset({"PLANNED"}),
    "PLANNED": frozenset({"GENERATING", "QUARANTINED"}),
    "GENERATING": frozenset({"SCREENING", "GENERATION_FAILED"}),
    "SCREENING": frozenset({"SANDBOX_TESTING", "SAFETY_REJECTED"}),
    "SANDBOX_TESTING": frozenset({
        "EVALUATING", "SANDBOX_FAILED", "SANDBOX_UNREACHABLE",
    }),
    "EVALUATING": frozenset({
        "AWAITING_APPROVAL", "EVALUATION_FAILED", "EVALUATION_UNSCORED",
    }),
    # An UNSCORED evaluation still reaches a human -- see
    # tests/test_evaluator_unscored_escalates.py's regression guard for
    # why this must never auto-reject.
    "EVALUATION_UNSCORED": frozenset({"AWAITING_APPROVAL"}),
    "AWAITING_APPROVAL": frozenset({"APPROVED", "APPROVAL_REJECTED"}),
    "APPROVED": frozenset({"INSTALLING", "POLICY_REFUSED"}),
    "INSTALLING": frozenset({"INSTALLED", "INSTALL_FAILED"}),
    "INSTALLED": frozenset({"EXECUTING", "ROLLED_BACK"}),
    "EXECUTING": frozenset({"COMPLETED", "EXECUTION_FAILED"}),
    "COMPLETED": frozenset({"ROLLED_BACK"}),
    # Terminal failure/rollback states have no legal onward transition in
    # THIS state machine. Recovering from one means starting a new
    # REQUESTED lifecycle (a new attempt/version), not resuming this one --
    # matching how synapse.propose(allow_retry=True) already works: a
    # retry is a new generate+sandbox attempt, not a resurrection of the
    # failed one. QUARANTINED -> INSTALLED is explicitly impossible here.
}


def transition(current: str, next_: str) -> str:
    """Validate a proposed move. Returns `next_` if legal, else raises."""
    if current not in CANONICAL_STATES:
        raise InvalidTransition(f"Unknown current state: {current!r}")
    if next_ not in CANONICAL_STATES:
        raise InvalidTransition(f"Unknown target state: {next_!r}")

    allowed = _TRANSITIONS.get(current, frozenset())
    if next_ not in allowed:
        raise InvalidTransition(
            f"{current} -> {next_} is not a legal transition. "
            f"Legal from {current}: {sorted(allowed) or '(terminal)'}"
        )
    return next_


def is_valid_transition(current: str, next_: str) -> bool:
    try:
        transition(current, next_)
        return True
    except InvalidTransition:
        return False


# --- mapping REAL pipeline output to a canonical state -------------------

def from_acquisition_record(record: dict[str, Any]) -> str:
    """Map a real AcquisitionRecord.to_dict() (as returned by
    synapse.propose()) to the canonical state it terminated in."""
    stage = record.get("stage")
    status = record.get("status")

    if stage == "GUARDIAN_PRESCREEN" and status == "REFUSED":
        return "POLICY_REFUSED"
    if stage == "SAFETY_SCREEN" and status == "REJECTED":
        return "SAFETY_REJECTED"
    if stage == "SANDBOX_TEST" and status == "REJECTED":
        return "SANDBOX_FAILED"
    if stage == "SANDBOX_TEST" and status == "BLOCKED":
        return "SANDBOX_UNREACHABLE"
    if stage == "EVALUATE" and status == "REJECTED":
        return "EVALUATION_FAILED"
    if stage == "GUARDIAN_SCREEN" and status == "REFUSED":
        return "POLICY_REFUSED"
    if stage == "AWAITING_APPROVAL" and status == "AWAITING_APPROVAL":
        evaluation = record.get("evaluation") or {}
        if evaluation.get("status") == "UNSCORED":
            return "EVALUATION_UNSCORED"
        return "AWAITING_APPROVAL"
    if status == "FAILED":
        return "GENERATION_FAILED"

    raise InvalidTransition(
        f"No canonical mapping for stage={stage!r} status={status!r}. "
        f"This is either a new pipeline outcome that needs a mapping "
        f"added here, or a malformed record."
    )


def from_install_result(result: dict[str, Any]) -> str:
    status = result.get("status")
    if status == "INSTALLED":
        return "INSTALLED"
    if status == "APPROVAL_REQUIRED":
        return "AWAITING_APPROVAL"
    if status == "FAILED":
        return "INSTALL_FAILED"
    raise InvalidTransition(f"No canonical mapping for install status={status!r}")


def from_rollback_result(result: dict[str, Any]) -> str:
    status = result.get("status")
    if status == "ROLLED_BACK":
        return "ROLLED_BACK"
    if status == "FAILED":
        return "INSTALL_FAILED"  # rollback of an install-family action
    raise InvalidTransition(f"No canonical mapping for rollback status={status!r}")
