"""API-level tests for the Phase 2 deploy spine.

These run fully offline: AXON_FIRESTORE_MODE=memory is set before the app
is imported, so no credentials and no network are required.
"""
import os

import pytest

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")
os.environ.setdefault("AXON_OWNER_TOKEN", "test-owner-token")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import app  # noqa: E402
from app.governance.kill_switch import kill_switch  # noqa: E402

client = TestClient(app, headers={"X-Axon-Token": "test-owner-token"})


@pytest.fixture(autouse=True)
def reset_kill_switch():
    kill_switch.deactivate()
    yield
    kill_switch.deactivate()


def test_health_and_root():
    assert client.get("/health").json() == {"status": "OK"}

    root = client.get("/").json()
    assert root["service"] == "aion-core"
    assert root["status"] == "LIVE"


def test_capabilities_are_registered():
    body = client.get("/capabilities").json()

    names = [c["name"] for c in body["capabilities"]]

    assert "calculator" in names
    assert body["total"] == 12
    assert body["implemented"] >= 2
    assert body["declared_only"] == body["total"] - body["implemented"]


def test_mission_without_explicit_tool_and_args_is_rejected():
    """POST /missions executes exactly the call it is given -- it does not
    infer a tool call from free text. Before this test, tool defaulted to
    "calculator" and args to [], so a request with neither silently built
    a mission that generated a narrative plan promising a real
    computation, then failed at execution/resume time with a bare
    TypeError instead of a validation error at the door.
    """
    response = client.post("/missions", json={
        "request": "Calculate 12.5 * 4 and tell me the result",
    })

    assert response.status_code == 422


def test_medium_risk_mission_requires_approval_and_resumes():
    created = client.post("/missions", json={
        "request": "Work out the invoice total with tax.",
        "tool": "calculator",
        "action": "purchase item",
        "risk": "MEDIUM",
        "args": ["1250 * 1.18"],
    }).json()

    mission_id = created["mission_id"]

    # The gate must stop a MEDIUM action before it executes.
    assert created["status"] == "AWAITING_APPROVAL"
    assert created["result"]["status"] == "APPROVAL_REQUIRED"

    request_id = created["approval_request_id"]
    assert request_id

    # It must show up as pending for the human.
    pending = client.get("/approvals/pending").json()
    assert request_id in [p["request_id"] for p in pending["pending"]]

    # Resuming BEFORE approval must not execute.
    too_early = client.post(f"/missions/{mission_id}/resume").json()
    assert too_early["result"]["status"] == "APPROVAL_REQUIRED"

    # Human approves.
    decision = client.post(f"/approvals/{request_id}/decide", json={
        "approved": True,
        "decided_by": "owner",
    }).json()
    assert decision["status"] == "APPROVED"

    # Now, and only now, it executes.
    resumed = client.post(f"/missions/{mission_id}/resume").json()
    assert resumed["result"]["status"] == "EXECUTED"
    assert resumed["result"]["result"]["result"] == 1475.0
    assert resumed["status"] == "COMPLETED"


def test_rejected_approval_never_executes():
    created = client.post("/missions", json={
        "request": "Spend money on something.",
        "tool": "calculator",
        "action": "purchase item",
        "risk": "MEDIUM",
        "args": ["2 + 2"],
    }).json()

    request_id = created["approval_request_id"]

    client.post(f"/approvals/{request_id}/decide", json={
        "approved": False,
        "decided_by": "owner",
    })

    resumed = client.post(f"/missions/{created['mission_id']}/resume").json()

    assert resumed["result"]["status"] != "EXECUTED"


def test_high_risk_is_refused_outright():
    created = client.post("/missions", json={
        "request": "Read the credentials out of the runtime.",
        "tool": "calculator",
        "action": "read runtime credentials",
        "risk": "HIGH",
        "args": ["1 + 1"],
    }).json()

    assert created["result"]["status"] == "REFUSED"
    assert created["approval_request_id"] is None


def test_kill_switch_blocks_execution():
    client.post("/killswitch", json={"active": True, "reason": "demo stop"})

    assert client.get("/killswitch").json()["kill_switch_active"] is True

    created = client.post("/missions", json={
        "request": "Do something harmless.",
        "tool": "calculator",
        "action": "add numbers",
        "risk": "LOW",
        "args": ["2 + 2"],
    }).json()

    assert created["result"]["status"] == "BLOCKED"

    client.post("/killswitch", json={"active": False})

    assert client.get("/killswitch").json()["kill_switch_active"] is False


def test_kill_switch_blocks_already_approved_work():
    """The dangerous case: approved work must still halt mid-flight."""
    created = client.post("/missions", json={
        "request": "Approved work that gets halted.",
        "tool": "calculator",
        "action": "purchase item",
        "risk": "MEDIUM",
        "args": ["10 * 10"],
    }).json()

    request_id = created["approval_request_id"]

    client.post(f"/approvals/{request_id}/decide", json={
        "approved": True,
        "decided_by": "owner",
    })

    client.post("/killswitch", json={"active": True, "reason": "halt"})

    resumed = client.post(f"/missions/{created['mission_id']}/resume").json()

    assert resumed["result"]["status"] == "BLOCKED"

    client.post("/killswitch", json={"active": False})


def test_unknown_mission_and_approval_are_handled():
    assert client.get("/missions/does-not-exist").json()["status"] == "NOT_FOUND"

    decided = client.post("/approvals/does-not-exist/decide", json={
        "approved": True,
    }).json()

    assert decided["status"] == "NOT_FOUND"


def test_autonomy_endpoints_are_read_only():
    """There must be no HTTP route that grants autonomy.

    A route that could raise a capability's autonomy would let the agent
    be handed trust it never earned.
    """
    routes = [
        (r.path, sorted(r.methods))
        for r in app.routes
        if getattr(r, "path", "").startswith("/autonomy")
    ]

    assert routes, "autonomy endpoints missing"

    for path, methods in routes:
        assert methods == ["GET"], f"{path} exposes {methods}"


def test_untracked_capability_reports_honestly():
    body = client.get("/autonomy/calculator").json()

    assert body["tracked"] is False
    assert body["supervised"] is False


def test_evolution_endpoint_exists():
    body = client.get("/evolution").json()

    assert "count" in body
    assert isinstance(body["events"], list)


def test_synapse_propose_cannot_install(monkeypatch):
    """The propose route must never be able to install anything."""
    from app.synapse import engine as engine_module

    monkeypatch.setattr(
        engine_module, "search_web",
        lambda q: {"status": "DEGRADED", "grounded": False, "sources": [],
                   "findings": "n", "source_count": 0},
    )
    monkeypatch.setattr(
        engine_module, "generate_candidate",
        lambda need, notes=None: (None, "builder unavailable"),
    )

    body = client.post("/synapse/propose",
                       json={"need": "normalize currency"}).json()

    assert body["status"] in ("FAILED", "AWAITING_APPROVAL", "REFUSED")
    assert body["status"] != "INSTALLED"


def test_synapse_refuses_a_credential_capability_over_http():
    body = client.post("/synapse/propose", json={
        "need": "a capability that reads credentials from the runtime",
    }).json()

    assert body["status"] == "REFUSED"
    assert body["guardian"]["policy_id"] == "G-04"


def test_install_without_approval_changes_nothing():
    body = client.post("/synapse/install/never-proposed").json()

    assert body["status"] == "FAILED"


def test_passport_endpoint_reports_missing_capability():
    body = client.get("/capabilities/not-a-thing/passport").json()

    assert body["status"] == "NOT_FOUND"


def test_cors_is_an_allowlist_not_a_wildcard():
    """A wildcard would let any site trip the kill switch via a visitor.

    This API exposes POST routes that approve capabilities and halt the
    agent. An agent whose kill switch a third-party page can flip is not
    under its owner's control.
    """
    from app.api import ALLOWED_ORIGINS

    assert "*" not in ALLOWED_ORIGINS
    assert any("web.app" in origin for origin in ALLOWED_ORIGINS)


def test_allowed_origin_gets_cors_headers():
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers.get("access-control-allow-origin") == (
        "http://localhost:5173"
    )


def test_unknown_origin_is_not_granted_access():
    response = client.get(
        "/health", headers={"Origin": "https://evil.example.com"},
    )

    assert "access-control-allow-origin" not in response.headers


def test_firebase_preview_channel_origin_is_allowed():
    """Preview channels get a generated subdomain that cannot be listed.

    Found live: the first channel deploy rendered fine and then showed
    "aion-core unreachable", because
    https://aion-axon-2026--<channel>-<hash>.web.app was not in the
    allowlist. Preview channels are how UI changes get reviewed without
    touching the live site, so a channel that cannot reach the API makes
    the review worthless.
    """
    origin = "https://aion-axon-2026--synapse-theater-vmwbuw8t.web.app"

    response = client.get("/health", headers={"Origin": origin})

    assert response.headers.get("access-control-allow-origin") == origin


def test_preflight_allows_the_owner_token_header():
    """Unlocking the Holo-Deck must not take the whole surface down.

    Found live 22 Aug, in two browsers, while trying the chat panel. The
    dashboard rendered perfectly until the owner token was pasted in, then
    every panel went red with "aion-core unreachable" -- while curl against
    the same API answered 200. That asymmetry sent the diagnosis chasing
    antivirus and proxy settings on the operator's machine for half an
    hour.

    The cause was here: a browser preflights any request carrying a custom
    header, allow_headers listed only Content-Type, so the preflight 400ed
    and the browser cancelled every request. Locked = fine, unlocked = dead.

    The demo unlocks on camera. This test asks the question the browser
    asks, because the earlier CORS tests only ever sent simple requests and
    a simple request is never preflighted.
    """
    response = client.options(
        "/autonomy",
        headers={
            "Origin": "https://aion-axon-2026.web.app",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type,x-axon-token",
        },
    )

    assert response.status_code == 200, (
        "preflight rejected the owner token header — the Holo-Deck will go "
        "dark the moment it is unlocked"
    )

    allowed = response.headers.get("access-control-allow-headers", "").lower()
    assert "x-axon-token" in allowed


def test_the_preview_pattern_does_not_open_the_api_to_every_web_app():
    """The regex is pinned to THIS project's prefix on purpose.

    A looser `.*\\.web\\.app` would hand every Firebase site on the
    internet the right to drive this API from a visitor's browser — the
    exact thing the explicit allowlist exists to prevent.
    """
    for hostile in (
        "https://attacker.web.app",
        "https://aion-axon-2026.evil.web.app",
        "https://notaion-axon-2026--x.web.app",
        "https://aion-axon-2026--x.web.app.evil.com",
    ):
        response = client.get("/health", headers={"Origin": hostile})

        assert "access-control-allow-origin" not in response.headers, hostile


def test_review_returns_the_code_being_approved():
    """An approval must be traceable to the source it authorises."""
    from app.memory.firestore_store import firestore_store

    firestore_store.approvals["review-1"] = {
        "action": "install capability: demo_skill",
        "risk": "MEDIUM",
        "reason": "SYNAPSE proposes installing demo_skill",
        "status": "PENDING",
        "policy_id": "INSTALL",
        "capability": "demo_skill",
    }
    firestore_store.save_capability("demo_skill", {
        "name": "demo_skill",
        "version": 0,
        "passport": {
            "approval_request_id": "review-1",
            "candidate": {
                "name": "demo_skill",
                "description": "does a thing",
                "code": "def demo():\n    return 1\n",
                "test": "assert demo() == 1",
                "entrypoint": "demo",
            },
            "tests": {"passed": True},
            "safety": {"safe": True},
            "evaluation": {"status": "SCORED", "score": 90},
        },
    })

    body = client.get("/approvals/review-1/review").json()

    assert body["status"] == "OK"
    assert "def demo()" in body["code"]
    assert body["is_first_version"] is True
    assert body["tests"]["passed"] is True


def test_review_of_a_non_code_approval_says_so():
    """A payment approval has no source; say that, don't render blank."""
    from app.memory.firestore_store import firestore_store

    firestore_store.approvals["review-2"] = {
        "action": "purchase item", "risk": "MEDIUM",
        "reason": "needs a human", "status": "PENDING",
    }

    body = client.get("/approvals/review-2/review").json()

    assert body["code"] is None
    assert "does not concern generated code" in body["note"]


def test_review_of_an_unknown_request():
    assert client.get("/approvals/nope/review").json()["status"] == "NOT_FOUND"


def test_second_version_produces_a_real_diff():
    from app.governance.review import build_diff

    diff = build_diff(
        "def f():\n    return 1\n", "def f():\n    return 2\n", "f",
    )

    assert any(line.startswith("-") and "return 1" in line for line in diff)
    assert any(line.startswith("+") and "return 2" in line for line in diff)


# --- Route coverage audit: routes with a path string mentioned in a test ---
# --- file, but never actually invoked with a real request, closed here. ---

def test_missions_planned_route_actually_dispatches_a_real_mission(monkeypatch):
    """POST /missions/planned is the single most-used route in the whole
    product -- every real text/voice mission dispatch goes through it --
    yet a full-repo audit found it had never once been invoked via HTTP
    in the test suite (only a route-inventory line and an auth-only
    check mentioned its path string). Executing it here proves the real
    wiring (owner auth -> rate limiter -> Pydantic body -> plan_mission
    -> mission_engine -> response) actually works end-to-end, not just
    the mission_service function in isolation.
    """
    import app.missions.service as mission_service_module
    from app.agents.plan_schema import MissionPlan, MissionStep

    def fake_plan(request, user_id="anshul"):
        return MissionPlan(
            goal="route coverage check", steps=[MissionStep(
                step=1, description="calc", kind="READ_ANALYZE",
                tool="calculator", args=["3 + 4"], risk="LOW", action="a",
            )],
        ), None

    monkeypatch.setattr(mission_service_module, "plan_mission", fake_plan)

    resp = client.post("/missions/planned", json={"request": "what is 3 + 4"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert body["step_results"][0]["result"]["result"] == 7.0


def test_resume_blocked_route_can_backfill_a_null_tool_step(monkeypatch):
    """BUG-006: this route never accepted or forwarded a capability_name,
    so it could only ever resume a mission blocked on an ALREADY-named
    (declared-but-unimplemented) capability. The more common gap -- the
    planner emitting tool: null because it found no capability at all --
    had no way to be resumed through this route; it would just re-block
    with the identical reason forever. The real product never hit this
    because synapse.install() resumes the tied mission internally with
    the freshly-installed name -- this route is the ONLY external way to
    supply that name, and now actually can.
    """
    import app.missions.service as mission_service_module
    from app.agents.plan_schema import MissionPlan, MissionStep
    from app.capabilities.registry import registry

    def fake_plan(request, user_id="anshul"):
        return MissionPlan(
            goal="route coverage null-tool gap", steps=[MissionStep(
                step=1, description="a genuinely unknown capability",
                kind="READ_ANALYZE", tool=None, args=["x"], risk="LOW",
                action="a",
            )],
        ), None

    monkeypatch.setattr(mission_service_module, "plan_mission", fake_plan)

    created = client.post(
        "/missions/planned", json={"request": "do something new"},
    ).json()
    assert created["status"] == "BLOCKED"
    assert created["plan"][0]["tool"] is None

    registry.register(
        "route_coverage_backfilled_cap", "x", "LOW",
        lambda *a: {"status": "SUCCESS", "value": "backfilled"},
    )

    resp = client.post(
        f"/missions/{created['mission_id']}/resume-blocked",
        json={"capability_name": "route_coverage_backfilled_cap"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "COMPLETED", (
        f"resume-blocked could not backfill a null-tool step via the "
        f"real HTTP route: {body}"
    )
    assert body["step_results"][0]["tool"] == "route_coverage_backfilled_cap"

    registry.unregister("route_coverage_backfilled_cap")


def test_resume_blocked_route_still_works_with_no_body(monkeypatch):
    """The pre-existing, already-correct case must not regress: a
    mission blocked on an already-declared capability resumes with no
    body at all, exactly as before this fix."""
    import app.missions.service as mission_service_module
    from app.agents.plan_schema import MissionPlan, MissionStep
    from app.capabilities.registry import registry

    def fake_plan(request, user_id="anshul"):
        return MissionPlan(
            goal="route coverage declared gap", steps=[MissionStep(
                step=1, description="a declared but unimplemented capability",
                kind="READ_ANALYZE", tool="route_coverage_declared_cap",
                args=["x"], risk="LOW", action="a",
            )],
        ), None

    monkeypatch.setattr(mission_service_module, "plan_mission", fake_plan)
    registry.declare("route_coverage_declared_cap", "x", "LOW")

    created = client.post(
        "/missions/planned", json={"request": "do the declared thing"},
    ).json()
    assert created["status"] == "BLOCKED"

    registry.register(
        "route_coverage_declared_cap", "x", "LOW",
        lambda *a: {"status": "SUCCESS", "value": "declared-ok"},
    )

    resp = client.post(f"/missions/{created['mission_id']}/resume-blocked")

    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"

    registry.unregister("route_coverage_declared_cap")
