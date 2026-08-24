"""app/synapse/planner.py -- memory-informed plans, and the invariant
that a plan can never itself authorize anything.
"""
from app.synapse.planner import plan


def _capability(name, description, *, state="READY", implemented=True, risk="LOW"):
    return {"name": name, "description": description, "state": state,
            "implemented": implemented, "risk": risk}


def _event(event_type, capability, status, **extra):
    return {
        "event_type": event_type, "capability": capability, "status": status,
        "stage": extra.pop("stage", "EVALUATE"),
        "reason": extra.pop("reason", "some reason"),
        "policy_id": extra.pop("policy_id", None),
        "timestamp": extra.pop("timestamp", "2026-08-23T10:00:00Z"),
    }


# --- CASE A: existing success ------------------------------------------

def test_case_a_existing_success_recommends_reuse():
    caps = [_capability("detect_yoy_anomalies", "Calculates year-over-year percentage change and flags anomalies")]
    p = plan("detect year-over-year anomalies", caps, [])
    assert p.decision == "REUSE_EXISTING_CAPABILITY"
    assert p.capability == "detect_yoy_anomalies"
    # Reuse must still require re-checking current state, never a bare pass.
    assert "CURRENT_CONTRACT_CHECK" in p.required_checks
    assert "CURRENT_QUARANTINE_STATUS" in p.required_checks


# --- CASE B: previous failure, no retry evidence -------------------------

def test_case_b_a_single_unrecovered_failure_escalates_not_silently_retried():
    """A capability whose only history is one rejection is, by the
    existing (separately tested) quarantine logic, quarantined -- the
    planner correctly escalates rather than quietly trying again. This is
    the safer reading of "previous failure, no retry evidence": without
    evidence a retry would help, the plan must not assume one will."""
    events = [_event("SYNAPSE_REJECTED", "convert_currency_amount", "REJECTED",
                      stage="SANDBOX_TEST", reason="AssertionError: bad rate")]
    p = plan("convert currency amount using exchange rate", [], events)
    assert p.decision == "ESCALATE"


def test_case_b_a_similarly_named_but_distinct_need_still_plans_a_fresh_attempt():
    """A need with NO real match in memory at all -- not even a rejected
    one -- must plan a normal single attempt, proving ESCALATE isn't the
    planner's default for every unfamiliar need."""
    events = [_event("SYNAPSE_REJECTED", "convert_currency_amount", "REJECTED",
                      stage="SANDBOX_TEST", reason="AssertionError: bad rate")]
    p = plan("summarize a block of unrelated text", [], events)
    assert p.decision == "ACQUIRE_NEW"
    assert p.strategy == "GENERATE_SINGLE_ATTEMPT"
    assert p.previous_failure is None


# --- CASE C: quarantine -----------------------------------------------

def test_case_c_quarantined_match_escalates():
    events = [_event("SYNAPSE_REJECTED", "risky_cap", "REJECTED", reason="failed AST screen")]
    p = plan("risky cap", [], events)
    assert p.decision == "ESCALATE"


# --- CASE D: previous retry success -------------------------------------

def test_case_d_prior_sandbox_failure_then_approval_plans_retry_with_feedback():
    events = [
        _event("SYNAPSE_REJECTED", "flaky_cap", "REJECTED", stage="SANDBOX_TEST",
               reason="AssertionError: off by one", timestamp="2026-08-20T10:00:00Z"),
        _event("SYNAPSE_AWAITING_APPROVAL", "flaky_cap", "AWAITING_APPROVAL",
               timestamp="2026-08-20T10:05:00Z"),
    ]
    p = plan("flaky cap", [], events)
    assert p.decision == "ACQUIRE_NEW"
    assert p.strategy == "GENERATE_WITH_RETRY"
    assert p.planned_attempts == 2
    assert "off by one" in p.previous_failure
    assert "retry-with-feedback recovered it before" in p.reason


# --- CASE E: conflicting history ----------------------------------------

def test_case_e_conflicting_near_tied_matches_escalate():
    caps = [
        _capability("calculate_birth_cagr", "Calculates CAGR for birth totals by year"),
        _capability("calculate_birth_volatility", "Calculates volatility for birth totals by year",
                     state="VALIDATING", implemented=False),
    ]
    p = plan("calculate birth totals by year metric", caps, [])
    assert p.decision == "ESCALATE"


# --- No history at all ---------------------------------------------------

def test_no_history_plans_a_single_fresh_attempt():
    p = plan("something entirely novel that nobody has asked for", [], [])
    assert p.decision == "ACQUIRE_NEW"
    assert p.strategy == "GENERATE_SINGLE_ATTEMPT"
    assert p.planned_attempts == 1
    assert set(p.required_checks) == {
        "GUARDIAN_PRESCREEN", "AST_SCREEN", "SANDBOX", "EVALUATOR",
        "GUARDIAN_SCREEN", "HUMAN_APPROVAL",
    }


# --- Malformed memory input ----------------------------------------------

def test_malformed_audit_events_do_not_crash_the_planner():
    """A history entry missing fields must degrade gracefully, not raise
    -- the planner must never become the reason a request fails."""
    events = [{"event_type": "SYNAPSE_REJECTED"}]  # no capability, no status
    p = plan("anything", [], events)
    assert p.decision == "ACQUIRE_NEW"


# --- Safety invariants ---------------------------------------------------

def test_plan_never_contains_an_approval_or_install_field():
    """Structural proof, not a docstring claim: a Plan's serialized form
    has no field an install/approval path could mistake for a real
    decision -- 'approved', 'installed', 'authorized' never appear as
    dict keys at any level."""
    caps = [_capability("detect_yoy_anomalies", "Calculates year-over-year percentage change")]
    d = plan("detect year-over-year anomalies", caps, []).to_dict()

    def _walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                assert k.lower() not in ("approved", "installed", "authorized", "owner_token"), k
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(d)


def test_plan_reuse_decision_still_requires_current_checks_not_a_bare_pass():
    """The literal Invariant 3/6/7 from the directive: historical success
    must not imply current safety or current approval. A REUSE plan must
    always carry at least one required check -- it can never be empty."""
    caps = [_capability("detect_yoy_anomalies", "Calculates year-over-year percentage change")]
    p = plan("detect year-over-year anomalies", caps, [])
    assert p.decision == "REUSE_EXISTING_CAPABILITY"
    assert len(p.required_checks) > 0


def test_plan_to_dict_states_the_authorization_boundary_explicitly():
    p = plan("anything", [], [])
    note = p.to_dict()["authorization_note"]
    assert "advisory" in note.lower()
    assert "human" in note.lower()
