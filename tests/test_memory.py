"""app/beastmode/memory.py — capability memory, derived from real records.

Fixtures mirror the real shapes: firestore_store.list_capabilities()
documents (as written by synapse.engine.install()/propose()) and
list_audit_events() (as written by synapse.engine._audit()).
"""
from app.beastmode.memory import find_related, recommend


def _capability(name, description, *, state="READY", implemented=True, risk="LOW"):
    return {
        "name": name, "description": description, "state": state,
        "implemented": implemented, "risk": risk,
    }


def _event(event_type, capability, status, **extra):
    return {
        "event_type": event_type, "capability": capability, "status": status,
        "stage": extra.pop("stage", "EVALUATE"),
        "reason": extra.pop("reason", "some reason"),
        "policy_id": extra.pop("policy_id", None),
        "timestamp": extra.pop("timestamp", "2026-08-23T10:00:00Z"),
    }


def test_no_related_capability_yields_acquire_new():
    rec = recommend("do something nobody has ever asked for", [], [])
    assert rec.recommendation == "ACQUIRE_NEW"
    assert rec.matches == []


def test_strong_match_on_installed_capability_recommends_reuse():
    caps = [_capability(
        "detect_yoy_anomalies",
        "Calculates year-over-year percentage change and flags anomalies",
    )]
    rec = recommend("detect year-over-year anomalies in the data", caps, [])
    assert rec.recommendation == "REUSE_EXISTING_CAPABILITY"
    assert rec.matches[0].name == "detect_yoy_anomalies"


def test_quarantined_match_is_never_recommended_for_reuse():
    caps = [_capability(
        "convert_currency_amount", "Converts a monetary amount using an exchange rate",
        state="VALIDATING", implemented=False,
    )]
    events = [_event("SYNAPSE_REJECTED", "convert_currency_amount", "REJECTED",
                      reason="failed sandbox test")]
    rec = recommend("convert currency amount using exchange rate", caps, events)
    assert rec.recommendation == "DO_NOT_REUSE"
    assert "REJECTED" in rec.reason or "quarantined" in rec.reason.lower()


def test_installed_capability_that_is_also_quarantined_is_not_reused():
    """A capability can be READY/implemented in the registry from an
    earlier version while its MOST RECENT audit trail is a rejection
    (e.g. a later re-proposal failed). Memory must not recommend reuse
    just because the registry doc says READY."""
    caps = [_capability("flaky_cap", "does something flaky")]
    events = [
        _event("SYNAPSE_AWAITING_APPROVAL", "flaky_cap", "AWAITING_APPROVAL",
               timestamp="2026-08-20T10:00:00Z"),
        _event("SYNAPSE_REJECTED", "flaky_cap", "REJECTED",
               timestamp="2026-08-23T10:00:00Z", reason="regenerated candidate failed"),
    ]
    rec = recommend("does something flaky", caps, events)
    assert rec.recommendation == "DO_NOT_REUSE"


def test_no_history_and_no_installed_match_yields_acquire_new_not_reuse():
    caps = [_capability(
        "summarize_performance_text", "Extracts KPIs from business performance text",
        state="VALIDATING", implemented=False,
    )]
    rec = recommend("summarize performance text and extract KPIs", caps, [])
    assert rec.recommendation == "ACQUIRE_NEW"


def test_conflicting_matches_escalate_rather_than_pick_a_side():
    caps = [
        _capability("calculate_birth_cagr", "Calculates CAGR for birth totals by year"),
        _capability("calculate_birth_volatility", "Calculates volatility for birth totals by year",
                     state="VALIDATING", implemented=False),
    ]
    rec = recommend("calculate birth totals by year metric", caps, [])
    assert rec.recommendation == "ESCALATE"


def test_find_related_is_lexical_not_semantic_and_says_so():
    """No embedding model is called here -- this locks in that the
    scoring is pure token overlap, so a future change cannot silently
    claim semantic understanding it doesn't have."""
    caps = [_capability("convert_currency_amount", "Converts a monetary amount using an exchange rate")]
    matches = find_related("translate money between currencies", caps)
    # Zero real token overlap ("convert"/"currency"/"amount"/"exchange"/"rate"
    # vs "translate"/"money"/"currencies") -- a semantic model would match
    # this; pure lexical overlap correctly does not.
    assert matches == []


def test_recommendation_never_claims_authorization():
    rec = recommend("detect year-over-year anomalies", [
        _capability("detect_yoy_anomalies", "Calculates year-over-year percentage change and flags anomalies"),
    ], [])
    d = rec.to_dict()
    assert "does not skip" in d["security_note"]
    assert "approval" in d["security_note"].lower()


def test_memory_output_is_deterministic():
    caps = [_capability("detect_yoy_anomalies", "Calculates year-over-year percentage change")]
    events = [_event("SYNAPSE_AWAITING_APPROVAL", "detect_yoy_anomalies", "AWAITING_APPROVAL")]
    a = recommend("detect year-over-year anomalies", caps, events).to_dict()
    b = recommend("detect year-over-year anomalies", caps, events).to_dict()
    assert a == b
