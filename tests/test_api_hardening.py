"""SEC-API (Batch 2 completion) — input hardening at the HTTP boundary.

Route inventory (from a grep of every @app.get/post in app/api.py, not
the remediation directive's assumed list -- there is no /missions/execute
in this codebase; the real equivalents are /missions, /missions/planned,
and the /missions/{id}/resume* family):

METHOD  ROUTE                                  AUTH    MODEL                    NOTES
GET     /                                       public  -                        status only
GET     /health                                 public  -
GET     /capabilities                           public  -
POST    /missions/planned                       owner   PlannedMissionRequest    real Gemini call (planner)
POST    /missions/{id}/acquire                  owner   -                        path param only
POST    /missions/{id}/resume-blocked           owner   ResumeBlockedRequest     capability_name optional (BUG-006)
POST    /missions/{id}/resume-planned           owner   -
POST    /missions                               owner   MissionRequest           real tool execution
GET     /missions/{id}                          public  -
POST    /missions/{id}/resume                   owner   -
GET     /autonomy, /autonomy/{capability}        public  -
GET     /telemetry                              public  -
POST    /ground-truth                           owner   GroundTruthRequest
GET     /ground-truth                           public  -
GET     /ground-truth/match                     public  query: str               was unbounded, fixed this pass
GET     /evolution                              public  -
POST    /synapse/propose                        owner   AcquisitionRequest       real Gemini + sandbox call
POST    /synapse/install/{capability}            owner   -                        path param only
POST    /synapse/rollback/{capability}           owner   RollbackRequest
GET     /capabilities/{capability}/passport      public  -
POST    /monitors                               owner   MonitorRequest
GET     /monitors                               public  -
POST    /monitors/run-due                       owner   -
POST    /monitors/{id}/disable                   owner   DisableMonitorRequest
GET     /sandbox/proof                          public  -
GET     /approvals/{id}/review                   public  -
GET     /approvals/pending                       public  -
POST    /approvals/{id}/decide                   owner   ApprovalDecision         mutates governed state
POST    /killswitch                             owner   KillSwitchRequest
GET     /killswitch                             public  -
GET     /beastmode/red-team                      public  -
GET     /beastmode/ledger/verify                 public  -
POST    /beastmode/ledger/seal                   owner   -
GET     /beastmode/contract/{capability}          public  -
GET     /beastmode/quarantine                    public  -
GET     /beastmode/lineage/{capability}           public  -
GET     /beastmode/approval/{id}/explain          public  -
POST    /beastmode/memory/query                  PUBLIC  MemoryQuery              no owner gate, no LLM call
GET     /beastmode/memory/{capability}            public  -
POST    /beastmode/plan                          PUBLIC  PlanQuery                no owner gate, no LLM call
GET     /beastmode/security/report                public  -
GET     /beastmode/mission/readiness              public  -

Every mutating (POST-with-a-body) route already required the owner
token before this pass (verified in tests/test_owner_auth.py, parametrized
across every write). The two PUBLIC POST routes (`/beastmode/memory/query`,
`/beastmode/plan`) were deliberately left ungated when built -- confirmed
this pass that neither calls an LLM (grepped both modules for
genai/generate_content/Client(: zero matches), so their exposure is
"anonymous callers can spend local CPU on a lexical match," not a quota
or authorization bypass. Both still get the same string bounds as
everything else below, as defense in depth.

`artifact_hash` does not exist anywhere in this schema (checked again
this pass) -- not tested here for the same reason it wasn't invented in
the ledger tests.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")
os.environ.setdefault("AXON_OWNER_TOKEN", "test-owner-token")

import json  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import MAX_REQUEST_BODY_BYTES, app  # noqa: E402
from app.governance.rate_limit import (  # noqa: E402
    planned_mission_limiter,
    propose_limiter,
)

TOKEN = {"X-Axon-Token": "test-owner-token"}
owner = TestClient(app, headers=TOKEN)
anonymous = TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limiters():
    """This file makes many consecutive real calls to /synapse/propose
    with the same token -- without this, its own test order trips the
    real rate limiter (see test_rate_limit.py) partway through, which is
    a test-isolation bug, not evidence of anything wrong with either
    the limiter or the validation these tests actually check."""
    propose_limiter.reset()
    planned_mission_limiter.reset()
    yield


# --- 1-6: field-level validation on the real, most security-relevant
# mutating route (POST /synapse/propose) --------------------------------

def test_missing_required_field_is_422():
    r = owner.post("/synapse/propose", json={"allow_retry": False})
    assert r.status_code == 422


def test_null_field_is_422():
    r = owner.post("/synapse/propose", json={"need": None})
    assert r.status_code == 422


def test_wrong_primitive_type_is_422():
    r = owner.post("/synapse/propose", json={"need": 12345})
    assert r.status_code == 422


def test_empty_string_need_is_422():
    r = owner.post("/synapse/propose", json={"need": ""})
    assert r.status_code == 422


def test_whitespace_only_need_is_422():
    """Pre-existing guard (min_length alone doesn't catch this -- ' '
    has length 1). Confirms it still holds after this pass's changes."""
    r = owner.post("/synapse/propose", json={"need": "   "})
    assert r.status_code == 422


def test_oversized_need_is_422():
    r = owner.post("/synapse/propose", json={"need": "x" * 5000})
    assert r.status_code == 422


# --- 7: oversized request body (the new middleware) -----------------------

def test_oversized_request_body_is_413():
    huge = json.dumps({"need": "x" * (MAX_REQUEST_BODY_BYTES + 1000)})
    r = owner.post(
        "/synapse/propose",
        content=huge,
        headers={**TOKEN, "Content-Type": "application/json"},
    )
    assert r.status_code == 413
    assert r.json()["code"] == "REQUEST_TOO_LARGE"


def test_body_under_the_limit_is_not_rejected_by_size():
    """Negative control: the size gate must not fire on ordinary
    traffic -- this should fail on VALIDATION (422, need too short-ish
    is fine here) or reach real logic, never 413."""
    r = owner.post("/synapse/propose", json={"need": "a real need"})
    assert r.status_code != 413


# --- 9: huge list (MissionRequest.args) ------------------------------------

def test_oversized_args_list_is_422():
    r = owner.post("/missions", json={
        "request": "x", "tool": "calculator", "action": "add",
        "risk": "LOW", "args": list(range(1000)),
    })
    assert r.status_code == 422


# --- 10: invalid enum (risk) — the real bug found and fixed this pass -----

def test_invalid_risk_enum_is_422_not_500():
    """Before this pass: mission_service.start() does RiskLevel(risk)
    with no try/except, so an invalid string reached that line and
    surfaced as an unhandled 500 -- reproduced live before fixing.
    risk is now a Literal, so Pydantic rejects it before the route runs."""
    r = owner.post("/missions", json={
        "request": "x", "tool": "calculator", "action": "add",
        "risk": "NOT_A_REAL_RISK_LEVEL", "args": [1, 2],
    })
    assert r.status_code == 422
    assert r.status_code != 500


def test_valid_risk_enum_values_are_accepted_by_validation():
    """Negative control: all three real values must still pass Pydantic
    validation (may still 500/error downstream for unrelated reasons --
    "calculator" needing specific args -- but never on the risk field)."""
    for risk in ("LOW", "MEDIUM", "HIGH"):
        r = owner.post("/missions", json={
            "request": "x", "tool": "calculator", "action": "add",
            "risk": risk, "args": [1, 2],
        })
        assert r.status_code != 422, f"risk={risk} was wrongly rejected"


# --- 11-12: NaN / Infinity --------------------------------------------------

def test_nan_numeric_field_is_422():
    r = owner.post(
        "/monitors",
        content='{"name": "m", "capability": "calculator", "interval_minutes": NaN}',
        headers={**TOKEN, "Content-Type": "application/json"},
    )
    assert r.status_code == 422


def test_infinity_numeric_field_is_422():
    r = owner.post(
        "/monitors",
        content='{"name": "m", "capability": "calculator", "interval_minutes": Infinity}',
        headers={**TOKEN, "Content-Type": "application/json"},
    )
    assert r.status_code == 422


# --- 13-14: numeric bounds (MonitorRequest.interval_minutes) --------------

def test_negative_interval_minutes_is_422():
    r = owner.post("/monitors", json={
        "name": "m", "capability": "calculator", "interval_minutes": -5,
    })
    assert r.status_code == 422


def test_absurdly_large_interval_minutes_is_422():
    r = owner.post("/monitors", json={
        "name": "m", "capability": "calculator", "interval_minutes": 10_000_000,
    })
    assert r.status_code == 422


# --- 15: malformed JSON -----------------------------------------------------

def test_malformed_json_body_is_422():
    r = owner.post(
        "/synapse/propose",
        content='{"need": "unterminated',
        headers={**TOKEN, "Content-Type": "application/json"},
    )
    assert r.status_code == 422


# --- 16: Unicode must NOT be blindly rejected ------------------------------

def test_legitimate_unicode_need_is_not_rejected_by_validation():
    """Non-Latin text and emoji are completely legitimate input -- must
    pass validation (may still degrade at the real Gemini call for
    unrelated reasons, but never on this field's shape)."""
    r = owner.post("/synapse/propose", json={
        "need": "convertir prix de devises en yen (円) with emoji 🔄",
    })
    assert r.status_code != 422


# --- 17: control characters -------------------------------------------------

def test_control_characters_in_need_do_not_crash_validation():
    """No demonstrated security problem from a stray control character in
    a text field that's only ever stored/displayed, never executed or
    interpolated into a shell/SQL context -- so this is a "does not
    crash" check, not a blanket rejection (per the explicit instruction
    not to reject Unicode/control chars without a real reason)."""
    r = owner.post("/synapse/propose", json={
        "need": "a need with a stray control char \x07 in it",
    })
    assert r.status_code in (200, 422, 500)  # never a raw crash/hang
    assert "Traceback" not in r.text


# --- 18-21: IDOR at the API layer (engine-level already covered in
# tests/test_reliability.py and tests/test_adversarial.py; these confirm
# the SAME properties survive through the real HTTP routes) -----------------

def test_forged_approval_id_returns_a_clean_not_found():
    r = owner.post("/approvals/does-not-exist/decide", json={"approved": True})
    assert r.status_code == 200  # route returns a structured NOT_FOUND, not a 500
    assert r.json()["status"] == "NOT_FOUND"


def test_forged_capability_name_install_returns_a_clean_failure():
    r = owner.post("/synapse/install/does-not-exist-capability")
    assert r.status_code == 200
    assert r.json()["status"] == "FAILED"


def test_forged_mission_id_returns_a_clean_not_found():
    r = owner.get("/missions/does-not-exist-mission-id")
    assert r.status_code == 200
    assert r.json()["status"] == "NOT_FOUND"


# --- error responses never expose internals --------------------------------

def test_422_responses_never_contain_a_python_traceback():
    r = owner.post("/synapse/propose", json={"need": 123})
    assert "Traceback" not in r.text
    assert "site-packages" not in r.text


def test_413_response_never_contains_internal_paths():
    huge = json.dumps({"need": "x" * (MAX_REQUEST_BODY_BYTES + 1000)})
    r = owner.post(
        "/synapse/propose", content=huge,
        headers={**TOKEN, "Content-Type": "application/json"},
    )
    assert "C:\\" not in r.text and "/app/" not in r.text
