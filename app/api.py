"""AION AXON core HTTP API.

Every route that can cause execution goes through MissionService ->
Orchestrator -> ExecutionGate. There is no route that executes a tool
directly, and adding one would break the governance guarantee.
"""
import json
import os
from contextlib import asynccontextmanager
from typing import Any, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware

from app.capabilities.declarations import catalog_summary
from app.capabilities.registry import registry
from app.capabilities.rehydrate import rehydrate_capabilities
from app.governance.approval import KillSwitchActive, approval_manager
from app.governance.autonomy_ledger import (
    SUPERVISION_THRESHOLD,
    autonomy_ledger,
)
from app.governance.ground_truth import all_facts, lookup, record_fact
from app.governance.kill_switch import kill_switch
from app.governance.owner_auth import HEADER as OWNER_TOKEN_HEADER, require_owner
from app.governance.rate_limit import rate_limit_planned_mission, rate_limit_propose
from app.governance.review import review_package
from app.memory.firestore_store import firestore_store
from app.missions.service import mission_service
from app.observability.telemetry import summarise
from app.monitors.service import monitor_service
from app.synapse.engine import synapse
from app.synapse.sandbox_client import env_proof as sandbox_env_proof


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Reconcile the runtime registry to Firestore BEFORE serving traffic.

    Cloud Run scales to zero, so without this an acquired capability lives
    only as long as one container and the acquisition story becomes an
    illusion between demo takes.
    """
    application.state.rehydration = rehydrate_capabilities()
    yield


app = FastAPI(
    title="AION AXON Core",
    description="Governed, self-evolving background agent.",
    version="0.3.0",
    lifespan=lifespan,
)

# An explicit origin allowlist, NOT "*". This API exposes POST routes that
# approve capabilities and trip the kill switch. With a wildcard, any page
# on the internet could drive those from a visitor's browser -- an agent
# whose kill switch a third-party site can flip is not under its owner's
# control. Extra origins can be added via AXON_ALLOWED_ORIGINS (comma
# separated) without a code change.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "AXON_ALLOWED_ORIGINS",
        "https://aion-axon-2026.web.app,"
        "https://aion-axon-2026.firebaseapp.com,"
        "http://localhost:5173,"
        "http://localhost:4173,"
        "http://127.0.0.1:4173",
    ).split(",")
    if origin.strip()
]

# Firebase Hosting preview channels get a generated subdomain of the form
# https://aion-axon-2026--<channel>-<hash>.web.app, which cannot be listed
# ahead of time. Without this, every preview channel loads but shows
# "aion-core unreachable" -- found the first time one was deployed.
#
# The pattern is deliberately anchored and pinned to THIS project's
# prefix. A looser `.*\.web\.app` would hand every Firebase site on the
# internet the right to drive this API from a visitor's browser, which is
# the exact thing the explicit allowlist above exists to prevent. Writes
# still require the owner token regardless of origin.
PREVIEW_CHANNEL_ORIGIN = r"^https://aion-axon-2026--[a-z0-9-]+\.web\.app$"

# The owner token header MUST be listed here, not just Content-Type.
#
# A browser preflights any request carrying a custom header. With
# X-Axon-Token missing from this list that preflight returned 400, so the
# browser cancelled the request before sending it -- which meant the
# Holo-Deck worked perfectly while LOCKED and went completely dark the
# instant a token was pasted in. Every panel read "aion-core unreachable"
# while the API was healthy and answering curl normally, so the failure
# pointed at the machine rather than at the allowlist. Found live, in two
# browsers, four days before submission.
#
# Listing the header grants no authority: it only lets the request be
# sent. require_owner still decides whether the token inside it is valid.
# SEC-API (Batch 2 completion): Starlette places no limit on request body
# size by default. Every real body this API expects is a short JSON
# object -- a need, a reason, a handful of args -- so a multi-megabyte
# body is never legitimate traffic, only an oversized-payload probe.
# Checked BEFORE routing (so an unauthenticated flood can't reach route
# logic) via Content-Length when the client declares one; a body sent
# without Content-Length is still bounded because Pydantic's own
# max_length constraints on individual fields (added this pass) reject
# an oversized JSON payload once parsed, just after this coarser check.
MAX_REQUEST_BODY_BYTES = 256_000


def _reject_non_finite_json_constant(token: str):
    """Passed to json.loads() as parse_constant. The stdlib json module
    accepts bare NaN/Infinity/-Infinity tokens as a non-standard
    extension by default -- confirmed live this pass that sending
    `interval_minutes: NaN` reached Pydantic as a real float('nan') and
    surfaced as an unhandled 500, not a clean 422 (the "invalid request
    looks like a server failure" case this whole section exists to
    prevent). Raising here instead of returning float('nan')/inf makes
    json.loads itself fail cleanly, before Pydantic or any route logic
    ever sees the value."""
    raise ValueError(f"{token} is not a finite JSON number.")


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")

        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = None

            if declared is not None and declared > MAX_REQUEST_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={
                        "status": "ERROR",
                        "code": "REQUEST_TOO_LARGE",
                        "message": (
                            f"Request body exceeds the "
                            f"{MAX_REQUEST_BODY_BYTES}-byte limit."
                        ),
                    },
                )

        if (
            request.method in ("POST", "PUT", "PATCH")
            and "application/json" in request.headers.get("content-type", "")
        ):
            body = await request.body()

            if body:
                try:
                    json.loads(body, parse_constant=_reject_non_finite_json_constant)
                except ValueError:
                    return JSONResponse(
                        status_code=422,
                        content={
                            "status": "ERROR",
                            "code": "INVALID_JSON",
                            "message": (
                                "Request body is not valid JSON, or contains "
                                "a non-finite number (NaN/Infinity)."
                            ),
                        },
                    )
                # request.body() caches the bytes on the Request object,
                # so the route handler's own body parse below reads the
                # same cached bytes rather than an exhausted stream.

        return await call_next(request)


app.add_middleware(BodySizeLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=PREVIEW_CHANNEL_ORIGIN,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", OWNER_TOKEN_HEADER],
)


class MissionRequest(BaseModel):
    # tool/action/args are deliberately required, not defaulted. This
    # endpoint executes exactly the tool call it is given -- it does not
    # parse `request` into a plan. A caller who wants that must use
    # POST /missions/planned. Defaulting tool to "calculator" and args to
    # [] used to let a request with no tool call in it pass validation,
    # generate a narrative "plan" that described a real computation, and
    # then fail at execution/resume time with a bare TypeError -- the
    # narrative promised work the request never actually specified.
    # SEC-API (Batch 2 completion): max_length values are generous bounds
    # for a short human-typed request/label, not a guess -- they exist so
    # an oversized field can't inflate a stored mission record or (for
    # `request`, on the planned path) an LLM prompt built from it.
    # `risk` moving from a bare `str` to this Literal closes a real,
    # reproduced bug: mission_service.start() does `RiskLevel(risk)` with
    # no try/except, so an invalid string previously reached that line
    # and surfaced as an unhandled 500 instead of a clean 422 -- the
    # exact "invalid request looks like a server failure" case this
    # section exists to prevent. `args` gets a max item count for the
    # same reason as the string fields: bound what a single mutating
    # request can make this service store or act on.
    request: str = Field(..., max_length=4000, description="The messy human request.")
    tool: str = Field(..., max_length=200, description="Registered tool name.")
    action: str = Field(..., max_length=500, description="Action being proposed.")
    risk: Literal["LOW", "MEDIUM", "HIGH"] = Field(
        "MEDIUM", description="LOW | MEDIUM | HIGH"
    )
    args: list[Any] = Field(
        ..., max_length=50, description="Positional args for the tool.",
    )


class ApprovalDecision(BaseModel):
    approved: bool
    decided_by: str = Field("owner", max_length=200)


class KillSwitchRequest(BaseModel):
    active: bool
    reason: str = Field("Human emergency stop", max_length=500)


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "aion-core",
        "status": "LIVE",
        "kill_switch_active": kill_switch.is_active(),
        "capabilities": len(registry.list_tools()),
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "OK"}


@app.get("/capabilities")
def capabilities() -> dict[str, Any]:
    return {
        **catalog_summary(),
        "rehydrated": getattr(app.state, "rehydration", None),
    }


def _reject_blank_after_stripping(value: str) -> str:
    """min_length alone does not catch this: "   " (3 spaces) satisfies
    min_length=3 numerically while being semantically empty. Found live
    this pass -- a whitespace-only need reached synapse.propose()
    unconstrained despite the field's own comment claiming this was
    already handled, spending a real (wasted) generation attempt before
    failing downstream instead of a clean 422 up front."""
    if not value.strip():
        raise ValueError("must not be empty or whitespace-only")
    return value


class PlannedMissionRequest(BaseModel):
    # This request text is built directly into a real Gemini prompt
    # (mission_service.start_planned() -> the planner) -- min_length
    # mirrors AcquisitionRequest.need's existing empty-input guard,
    # max_length bounds what a single call can spend on planning.
    request: str = Field(
        ..., min_length=3, max_length=4000, description="The messy human request.",
    )

    _reject_blank = field_validator("request")(_reject_blank_after_stripping)


@app.post(
    "/missions/planned",
    dependencies=[Depends(require_owner), Depends(rate_limit_planned_mission)],
)
def create_planned_mission(body: PlannedMissionRequest) -> dict[str, Any]:
    """Plan a messy request with Gemini, then run it through the gate."""
    return mission_service.start_planned(body.request)


def _need_for_blocked_mission(mission_id: str) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """Shared by the sync and streaming acquire routes below: derive the
    real acquisition need from a BLOCKED mission's own gap, so neither
    route has to re-implement (or drift from) the other's logic.

    Returns (need, error_response). Exactly one is non-None.
    """
    mission = mission_service.get(mission_id)

    if mission is None:
        return None, {"status": "NOT_FOUND", "mission_id": mission_id}

    if mission.get("status") != "BLOCKED":
        return None, {
            "status": "FAILED",
            "error": f"Mission is {mission.get('status')}, not BLOCKED.",
        }

    gap = mission.get("blocked_on") or {}
    need = gap.get("capability_description") or gap.get("description")

    if not need:
        return None, {"status": "FAILED", "error": "Mission records no gap."}

    # Show SYNAPSE the ACTUAL input the new capability will receive, not
    # just a description of the job. Without this it guesses the shape and
    # has no way to know it guessed wrong: the safety screen, the sandbox
    # and Gemma all pass a candidate that fits nothing, because each is
    # answering a different question. Found live 22 Aug — `calculate_cagr`
    # was built for {date, value} records and the step feeds it
    # {year, total} rows.
    sample = mission_service.blocked_step_input(mission_id)

    if sample:
        need = (
            f"{need}\n\n"
            "The capability will be called with exactly this input, as a "
            f"single string argument:\n{sample}\n\n"
            "Parse THIS shape. Do not invent different field names."
        )

    return need, None


@app.post("/missions/{mission_id}/acquire", dependencies=[Depends(require_owner)])
def acquire_for_mission(mission_id: str) -> dict[str, Any]:
    """Propose the capability a BLOCKED mission is missing.

    Reads the gap off the mission itself rather than making the caller
    restate it, and ties the acquisition back to the mission so that
    installing it finishes the original job.
    """
    need, error = _need_for_blocked_mission(mission_id)
    if error is not None:
        return error

    return synapse.propose(need, mission_id).to_dict()


@app.get(
    "/missions/{mission_id}/acquire/stream",
    dependencies=[Depends(require_owner), Depends(rate_limit_propose)],
)
def acquire_for_mission_stream(mission_id: str) -> StreamingResponse:
    """The same acquisition as POST /missions/{mission_id}/acquire, streamed
    stage-by-stage exactly like GET /synapse/propose/stream -- same
    derivation of the need from the mission's own gap, same
    synapse.propose_stream() generator, just observed live instead of
    only at the end. No second pipeline: this route and the sync one
    above call the identical propose_stream()/propose() pair engine.py
    already exposes.
    """
    need, error = _need_for_blocked_mission(mission_id)

    if error is not None:
        def error_event():
            yield _sse_event("error", error)
        return StreamingResponse(error_event(), media_type="text/event-stream")

    def events():
        try:
            for record in synapse.propose_stream(need, mission_id):
                yield _sse_event("stage", record.to_dict())
        except Exception as exc:  # noqa: BLE001 -- see synapse_propose_stream's comment
            yield _sse_event("error", {"error": str(exc)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/missions/{mission_id}/resume-blocked", dependencies=[Depends(require_owner)])
def resume_blocked_mission(mission_id: str) -> dict[str, Any]:
    return mission_service.resume_blocked(mission_id)


@app.post("/missions/{mission_id}/resume-planned", dependencies=[Depends(require_owner)])
def resume_planned_mission(mission_id: str) -> dict[str, Any]:
    return mission_service.resume_planned(mission_id)


@app.post("/missions", dependencies=[Depends(require_owner)])
def create_mission(body: MissionRequest) -> dict[str, Any]:
    return mission_service.start(
        request=body.request,
        tool=body.tool,
        action=body.action,
        risk=body.risk,
        args=body.args,
    )


@app.get("/missions/{mission_id}")
def get_mission(mission_id: str) -> dict[str, Any]:
    mission = mission_service.get(mission_id)

    if mission is None:
        return {"status": "NOT_FOUND", "mission_id": mission_id}

    return mission


@app.post("/missions/{mission_id}/resume", dependencies=[Depends(require_owner)])
def resume_mission(mission_id: str) -> dict[str, Any]:
    return mission_service.resume(mission_id)


@app.get("/autonomy")
def autonomy_view() -> dict[str, Any]:
    """The Autonomy Ledger, READ-ONLY.

    There is deliberately no endpoint that sets autonomy. It moves only
    when the Evidence Engine scores a real outcome. A route that could
    raise a capability's autonomy would be a way to grant the agent trust
    it has not earned — the exact thing this subsystem exists to prevent.
    """
    records = firestore_store.list_capabilities()

    # Annotate rather than return raw documents. A capability record with
    # no autonomy_pct is NOT at 0% -- the ledger treats a missing score as
    # the starting value, and a dashboard rendering it as 0 would claim a
    # supervision state the backend does not actually apply.
    annotated = []

    for record in records:
        name = record.get("name")
        scored = int(record.get("total_outcomes", 0)) > 0

        annotated.append({
            **record,
            "scored": scored,
            "effective_autonomy_pct": autonomy_ledger.autonomy_of(name)
            if name else None,
            "supervised": autonomy_ledger.requires_supervision(name)
            if name else False,
        })

    return {
        "supervision_threshold": SUPERVISION_THRESHOLD,
        "tracked_count": len(annotated),
        "scored_count": len([a for a in annotated if a["scored"]]),
        "capabilities": annotated,
    }


@app.get("/autonomy/{capability}")
def autonomy_of(capability: str) -> dict[str, Any]:
    record = autonomy_ledger.tracked(capability)

    if record is None:
        return {
            "capability": capability,
            "tracked": False,
            "supervised": False,
            "note": (
                "Not tracked by the ledger. Hand-built seed capabilities "
                "were human-reviewed before shipping and are trusted "
                "until evidence says otherwise."
            ),
        }

    return {
        "capability": capability,
        "tracked": True,
        "supervised": autonomy_ledger.requires_supervision(capability),
        "supervision_threshold": SUPERVISION_THRESHOLD,
        **record,
    }


@app.get("/telemetry")
def telemetry(limit: int = 500) -> dict[str, Any]:
    """What the work cost: latency and real token usage.

    Token counts come from the model's own usage_metadata. Calls that did
    not report usage are counted as UNMEASURED rather than estimated --
    an inferred token count is a guess wearing the same clothes as a
    measurement, and would quietly corrupt every cost figure downstream.
    """
    events = firestore_store.list_audit_events(limit)

    return {"events_examined": len(events), **summarise(events)}


class GroundTruthRequest(BaseModel):
    # This is written into Firestore and read back to grade the agent's
    # future claims -- bounded so a single fact can't become an
    # unbounded storage/ledger-bloat vector.
    key: str = Field(..., max_length=200, description="Short identifier for the fact.")
    statement: str = Field(..., max_length=1000, description="What the fact is about.")
    value: str = Field(..., max_length=1000, description="The independently known value.")
    source: str = Field(..., max_length=1000, description="Where it came from. Required.")
    recorded_by: str = Field("owner", max_length=200, description="Who recorded it.")


@app.post("/ground-truth", dependencies=[Depends(require_owner)])
def record_ground_truth(body: GroundTruthRequest) -> dict[str, Any]:
    """Record an independently known fact, with provenance.

    This is what the Evidence Engine checks the agent's claims against. It
    must come from a human with a source: a fact the agent supplied would
    be the agent grading its own homework, and a fact with no source is an
    unaccountable veto over a capability's autonomy.
    """
    return record_fact(
        body.key, body.statement, body.value, body.source, body.recorded_by,
    )


@app.get("/ground-truth")
def list_ground_truth() -> dict[str, Any]:
    facts = all_facts()

    return {
        "count": len(facts),
        "facts": [
            {**f.to_dict(), "age_days": f.age_days, "stale": f.stale}
            for f in facts
        ],
    }


@app.get("/ground-truth/match")
def match_ground_truth(
    # SEC-API: a bare `str` query param has no length bound by default --
    # found during the Batch 2 route inventory. Public, read-only, local
    # lexical match only (no LLM call), so this bounds compute per
    # request rather than cost/quota.
    query: str = Query(..., max_length=4000),
) -> dict[str, Any]:
    """Show which fact WOULD be applied to a query, without running it.

    Useful before a demo: it makes the contradiction check inspectable
    rather than something that happens invisibly inside a verification.
    """
    fact = lookup(query)

    if fact is None:
        return {
            "query": query,
            "matched": False,
            "note": (
                "No fact matched closely enough. The claim will be checked "
                "for form but not against a known value."
            ),
        }

    return {
        "query": query,
        "matched": True,
        "fact": {**fact.to_dict(), "age_days": fact.age_days,
                 "stale": fact.stale},
    }


@app.get("/evolution")
def evolution_events() -> dict[str, Any]:
    events = firestore_store.list_evolution_events()
    return {"count": len(events), "events": events}


class AcquisitionRequest(BaseModel):
    # min_length: the frontend already guards with `!need.trim()`, but this
    # is the real, expensive, mutating path (spends a real Gemini call and
    # a real sandbox run) -- it must not trust the client alone. An empty
    # or whitespace-only need previously reached synapse.propose()
    # unconstrained; Pydantic now refuses it with a 422 before any real
    # resource is spent. See tests/test_reliability.py.
    need: str = Field(
        ..., min_length=3, max_length=4000,
        description="The capability AION Axon lacks.",
    )

    _reject_blank = field_validator("need")(_reject_blank_after_stripping)
    mission_id: Optional[str] = Field(
        None,
        description="Mission this acquisition should unblock, if any.",
    )
    allow_retry: bool = Field(
        False,
        description=(
            "Permit ONE additional generate+sandbox attempt if the first "
            "candidate fails its own test, fed the real stderr. Defaults "
            "to False, matching behavior before this field existed."
        ),
    )


@app.post(
    "/synapse/propose",
    dependencies=[Depends(require_owner), Depends(rate_limit_propose)],
)
def synapse_propose(body: AcquisitionRequest) -> dict[str, Any]:
    """Run the acquisition loop up to — and stopping at — human approval.

    This route can never install anything. It ends at AWAITING_APPROVAL
    at best; installation requires a separate call after a real decision.
    """
    return synapse.propose(
        body.need, body.mission_id, allow_retry=body.allow_retry,
    ).to_dict()


def _sse_event(event: str, data: dict[str, Any]) -> str:
    """Format one Server-Sent Event. `data` is JSON-encoded on a single
    line -- an SSE payload cannot contain a bare newline, and json.dumps
    never emits one by default."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get(
    "/synapse/propose/stream",
    dependencies=[Depends(require_owner), Depends(rate_limit_propose)],
)
def synapse_propose_stream(
    need: str = Query(..., min_length=3, max_length=4000),
    mission_id: Optional[str] = Query(None, max_length=200),
    allow_retry: bool = Query(False),
) -> StreamingResponse:
    """The same acquisition pipeline as POST /synapse/propose, streamed:
    one real Server-Sent Event per pipeline stage as it actually
    completes (GUARDIAN_PRESCREEN -> RESEARCH -> GENERATE ->
    SAFETY_SCREEN -> SANDBOX_TEST -> EVALUATE -> GUARDIAN_SCREEN ->
    AWAITING_APPROVAL, or an earlier terminal stage on a real
    refusal/rejection/block/failure).

    Backed directly by synapse.propose_stream() -- the exact generator
    synapse.propose() above also drains. There is one pipeline
    implementation; this route cannot show a stage the governed pipeline
    did not actually just execute, because it never re-derives or mocks
    any stage -- it only observes the real one as it runs.

    A GET route with the need in the query string, not a POST body: the
    frontend consumes this with `fetch()` + a stream reader (not the
    browser's native EventSource, which cannot send the `X-Axon-Token`
    header this route is gated on) -- see web/src/api.js. GET matches
    what every browser streaming primitive expects, and keeping auth on
    a header rather than a query string keeps the owner token out of
    server logs and browser history, same as every other route.
    """
    # A manual call, not a Pydantic field_validator (there is no request
    # body on a GET route to attach one to) -- so the ValueError it raises
    # is caught and turned into the same clean 422 the POST route gets
    # for free, instead of an unhandled 500 for a whitespace-only need.
    try:
        stripped = _reject_blank_after_stripping(need)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    def events():
        try:
            for record in synapse.propose_stream(
                stripped, mission_id, allow_retry=allow_retry,
            ):
                yield _sse_event("stage", record.to_dict())
        except Exception as exc:  # noqa: BLE001 -- see comment below
            # A stage that raises (a genuine bug, or a real model/network
            # failure not already caught and degraded inside the
            # pipeline itself) must still close the stream with an
            # honest error event. An SSE connection that just drops looks,
            # to the UI, identical to "still working" -- silently worse
            # than a visible failure.
            yield _sse_event("error", {"error": str(exc)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            # Disables buffering on Cloud Run's/nginx-style fronting
            # proxies, which otherwise hold the whole response until it
            # closes -- turning a live stream back into a delayed batch.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/synapse/install/{capability}", dependencies=[Depends(require_owner)])
def synapse_install(capability: str) -> dict[str, Any]:
    """Install an approved capability. Re-reads the approval from
    Firestore, so calling this without a decision changes nothing."""
    return synapse.install(capability)


class RollbackRequest(BaseModel):
    reason: str = Field(
        ..., max_length=1000, description="Why the capability is removed.",
    )


@app.post("/synapse/rollback/{capability}", dependencies=[Depends(require_owner)])
def synapse_rollback(capability: str, body: RollbackRequest) -> dict[str, Any]:
    return synapse.rollback(capability, body.reason)


@app.get("/capabilities/{capability}/passport")
def skill_passport(capability: str) -> dict[str, Any]:
    """WHY THIS SKILL EXISTS — the chain of custody for one capability."""
    stored = firestore_store.get_capability(capability)

    if stored is None:
        return {"status": "NOT_FOUND", "capability": capability}

    return {
        "capability": capability,
        "state": stored.get("state"),
        "version": stored.get("version"),
        "implemented": stored.get("implemented"),
        "approved_by": stored.get("approved_by"),
        "installed_at": stored.get("installed_at"),
        "passport": stored.get("passport"),
    }


class MonitorRequest(BaseModel):
    name: str = Field(..., max_length=200)
    capability: str = Field(..., max_length=200)
    args: list[str] = Field(default_factory=list, max_length=50)
    # An upper bound alongside the existing ge=1: a monitor scheduled to
    # "run" once a decade is not a real schedule.
    interval_minutes: int = Field(60, ge=1, le=525_600)
    description: str = Field("", max_length=1000)


@app.post("/monitors", dependencies=[Depends(require_owner)])
def create_monitor(body: MonitorRequest) -> dict[str, Any]:
    return monitor_service.create(
        name=body.name,
        capability=body.capability,
        args=body.args,
        interval_minutes=body.interval_minutes,
        description=body.description,
    )


@app.get("/monitors")
def list_monitors() -> dict[str, Any]:
    monitors = monitor_service.list_all()

    return {
        "count": len(monitors),
        "active": len([m for m in monitors if m.get("state") == "ACTIVE"]),
        "monitors": monitors,
    }


@app.post("/monitors/run-due", dependencies=[Depends(require_owner)])
def run_due_monitors() -> dict[str, Any]:
    """Run every monitor that is due. Called by an external scheduler.

    Pull-based rather than a message bus: the service still scales to zero
    between ticks, and every run goes through the ExecutionGate, so the
    kill switch halts scheduled work exactly like interactive work.
    """
    return monitor_service.run_due()


class DisableMonitorRequest(BaseModel):
    reason: str = Field("Disabled by owner", max_length=500)


@app.post("/monitors/{monitor_id}/disable", dependencies=[Depends(require_owner)])
def disable_monitor(
    monitor_id: str,
    body: DisableMonitorRequest,
) -> dict[str, Any]:
    return monitor_service.disable(monitor_id, body.reason)


@app.get("/sandbox/proof")
def sandbox_proof() -> dict[str, Any]:
    """The sandbox's credential scan, fetched THROUGH aion-core.

    The sandbox is no longer publicly reachable, which is the point: this
    response proves core can reach it and the internet cannot. A 403 here
    would mean core lost its invoker role; UNREACHABLE means the service
    is down. Both are worth telling apart.
    """
    return sandbox_env_proof()


@app.get("/approvals/{request_id}/review")
def review_approval(request_id: str) -> dict[str, Any]:
    """The code being authorised, plus the evidence behind it.

    Approving a description of generated code is a signature on an unread
    document. This returns the source, a diff against the installed
    version when there is one, the sandbox result and the evaluator's
    verdict.
    """
    return review_package(request_id)


@app.get("/approvals/pending")
def pending_approvals() -> dict[str, Any]:
    pending = firestore_store.list_pending_approvals()
    return {"count": len(pending), "pending": pending}


@app.post("/approvals/{request_id}/decide", dependencies=[Depends(require_owner)])
def decide_approval(
    request_id: str,
    body: ApprovalDecision,
) -> dict[str, Any]:
    try:
        request = approval_manager.decide(
            request_id,
            body.approved,
            body.decided_by,
        )
    except KillSwitchActive:
        return {
            "status": "BLOCKED",
            "reason": "Kill switch is active.",
            "request_id": request_id,
        }
    except KeyError:
        return {"status": "NOT_FOUND", "request_id": request_id}
    except ValueError as error:
        return {"status": "ALREADY_DECIDED", "error": str(error)}

    return {
        "status": "APPROVED" if request.approved else "REJECTED",
        "request_id": request_id,
        "decided_by": request.decided_by,
        "decided_at": request.decided_at,
    }


@app.post("/killswitch", dependencies=[Depends(require_owner)])
def set_kill_switch(body: KillSwitchRequest) -> dict[str, Any]:
    if body.active:
        kill_switch.activate(body.reason)
    else:
        kill_switch.deactivate()

    return {
        "kill_switch_active": kill_switch.is_active(),
        "reason": body.reason if body.active else None,
    }


@app.get("/killswitch")
def get_kill_switch() -> dict[str, Any]:
    return {"kill_switch_active": kill_switch.is_active()}


# --- Beastmode: additive governance narration -----------------------------
#
# Everything below reads real signals from the pipeline above and returns
# them; nothing here can execute, approve or block anything. See
# app/beastmode/ and docs/AXON_BEASTMODE_AUDIT.md for what each module
# does and does not do.

@app.get("/beastmode/red-team")
def beastmode_red_team() -> dict[str, Any]:
    """Runs the REAL AST screen and Guardian against real attack payloads,
    right now, on this request. Not a cached or canned result."""
    from app.beastmode.red_team import _run

    results, contained = _run()
    genuine_misses = sum(
        1 for r in results if not r["blocked"] and not r.get("expected_miss_here")
    )
    return {
        "results": results,
        "total": len(results),
        "contained_at_layer_tested": contained,
        "genuine_misses": genuine_misses,
    }


@app.get("/beastmode/ledger/verify")
def beastmode_ledger_verify() -> dict[str, Any]:
    """Re-hashes the REAL live evolution ledger and compares it to the
    last seal on disk. See app/beastmode/ledger_chain.py for exactly what
    this can and cannot prove."""
    from app.beastmode.ledger_chain import verify

    events = firestore_store.list_evolution_events()
    return verify(events)


@app.post("/beastmode/ledger/seal", dependencies=[Depends(require_owner)])
def beastmode_ledger_seal() -> dict[str, Any]:
    """Writes a new seal over the CURRENT real ledger state. Owner-gated:
    unlike verify, this changes what future verifications compare against."""
    from app.beastmode.ledger_chain import seal

    events = firestore_store.list_evolution_events()
    return seal(events)


@app.get("/beastmode/contract/{capability}")
def beastmode_contract(capability: str) -> dict[str, Any]:
    """Assembles the declared contract for an ALREADY-ACQUIRED capability
    from its real passport -- the AST findings and risk it was actually
    screened and approved under, not a fresh re-screen."""
    from app.beastmode.contracts import build_contract

    passport_body = skill_passport(capability)  # reuses the existing endpoint's own logic
    passport = (passport_body.get("passport") or {})

    if not passport:
        return {"status": "NOT_FOUND", "capability": capability}

    contract = build_contract(
        name=capability,
        entrypoint=(passport.get("candidate") or {}).get("entrypoint", capability),
        risk=(passport.get("candidate") or {}).get("risk", "LOW"),
        ast_safe=(passport.get("safety") or {}).get("safe", False),
        ast_findings=(passport.get("safety") or {}).get("findings", []),
    )
    return {"status": "OK", "contract": contract.to_dict()}


@app.get("/beastmode/quarantine")
def beastmode_quarantine() -> dict[str, Any]:
    """Which capabilities are quarantined right now, derived from the real
    audit trail -- not a new write path. See app/beastmode/quarantine.py."""
    from app.beastmode.quarantine import compute_quarantine, to_dict

    events = firestore_store.list_audit_events(limit=1000)
    entries = compute_quarantine(events)
    return {"count": len(entries), "quarantined": [to_dict(e) for e in entries]}


@app.get("/beastmode/lineage/{capability}")
def beastmode_lineage(capability: str) -> dict[str, Any]:
    """A real version history, reconstructed from the real evolution
    ledger. No new write path -- every acquisition and rollback was
    already recorded by app/synapse/engine.py; this only groups, sorts
    and numbers them per capability."""
    from app.beastmode.lineage import build_lineage, current_version, to_dict

    events = firestore_store.list_evolution_events()
    steps = build_lineage(capability, events)

    return {
        "capability": capability,
        "current_version": current_version(capability, events),
        "currently_installed": current_version(capability, events) > 0,
        "history": [to_dict(s) for s in steps],
    }


@app.get("/beastmode/approval/{request_id}/explain")
def beastmode_explain_approval(request_id: str) -> dict[str, Any]:
    """WHY does this need a human? Assembled from the same real signals
    the review endpoint already exposes -- a risk score and a contract
    layered on top, not a second source of truth. Read-only: this cannot
    approve, reject or install anything, unlike /approvals/{id}/decide."""
    from app.beastmode.contracts import build_contract
    from app.beastmode.risk_score import compute_risk_score

    review = review_approval(request_id)
    if review.get("status") == "NOT_FOUND":
        return review

    safety = review.get("safety") or {}
    tests = review.get("tests") or {}
    evaluation = review.get("evaluation") or {}

    risk = compute_risk_score(
        ast_finding_count=len(safety.get("findings") or []),
        sandbox_passed=bool(tests.get("passed")),
        evaluator_score=evaluation.get("score"),
    )

    contract = build_contract(
        name=review.get("capability", ""),
        entrypoint=review.get("entrypoint", ""),
        risk=review.get("risk", "LOW"),
        ast_safe=safety.get("safe", False),
        ast_findings=safety.get("findings", []),
    )

    return {
        "status": "OK",
        "request_id": request_id,
        "capability": review.get("capability"),
        "why_human": {
            "risk_score": risk.to_dict(),
            "declared_contract": contract.to_dict(),
            "sandbox_result": {
                "passed": tests.get("passed"),
                "exit_code": tests.get("exit_code"),
            },
            "evaluator_result": {
                "status": evaluation.get("status"),
                "reason_code": evaluation.get("reason_code"),
                "score": evaluation.get("score"),
                "verdict": evaluation.get("verdict"),
                "reason": evaluation.get("reason"),
            },
            "policy_id": review.get("policy_id"),
        },
    }


class MemoryQuery(BaseModel):
    # Public, unauthenticated endpoint (read-only, no LLM call -- see the
    # route's own docstring) -- max_length bounds the local lexical-match
    # work an anonymous caller can trigger per request, not a cost/quota
    # concern like the LLM-facing fields above.
    need: str = Field(
        ..., max_length=4000,
        description="Free-text capability need to check against memory.",
    )


@app.post("/beastmode/memory/query")
def beastmode_memory_query(body: MemoryQuery) -> dict[str, Any]:
    """What does memory already know about this need? Read-only: this
    NEVER generates, screens, sandboxes, evaluates, approves or installs
    anything -- it is lexical-overlap search plus the real quarantine and
    audit history, exactly the same real records the rest of Beastmode
    already exposes. See app/beastmode/memory.py's module docstring for
    why the recommendation carries no authorization."""
    from app.beastmode.memory import recommend

    capabilities = firestore_store.list_capabilities()
    events = firestore_store.list_audit_events(limit=1000)

    result = recommend(body.need, capabilities, events)
    return {"need": body.need, **result.to_dict()}


@app.get("/beastmode/memory/{capability}")
def beastmode_memory_history(capability: str) -> dict[str, Any]:
    """The real audit history for ONE named capability -- every
    SYNAPSE_* outcome it has ever produced, oldest first."""
    from app.beastmode.memory import capability_history

    events = firestore_store.list_audit_events(limit=1000)
    history = capability_history(capability, events)
    stored = firestore_store.get_capability(capability)

    return {
        "capability": capability,
        "known": stored is not None,
        "state": (stored or {}).get("state"),
        "implemented": bool((stored or {}).get("implemented")),
        "attempts": len(history),
        "history": [h.to_dict() for h in history],
    }


class PlanQuery(BaseModel):
    # Same rationale as MemoryQuery.need above: public, read-only, no LLM
    # call (see app/synapse/planner.py's own docstring).
    need: str = Field(
        ..., max_length=4000, description="Free-text capability need to plan for.",
    )


@app.post("/beastmode/plan")
def beastmode_plan(body: PlanQuery) -> dict[str, Any]:
    """The memory-informed plan for `need`: REUSE_EXISTING_CAPABILITY /
    ACQUIRE_NEW (with a strategy, informed by real retry-recovery
    history) / ESCALATE. Read-only, deterministic given the same
    underlying data -- see app/synapse/planner.py's module docstring for
    why a plan cannot authorize anything the real pipeline wouldn't
    already require."""
    from app.synapse.planner import plan as build_plan

    capabilities = firestore_store.list_capabilities()
    events = firestore_store.list_audit_events(limit=1000)

    result = build_plan(body.need, capabilities, events)
    return {"need": body.need, **result.to_dict()}


@app.get("/beastmode/security/report")
def beastmode_security_report() -> dict[str, Any]:
    """A judge-facing summary of what's actually been tested and what
    remains a known limitation. Read-only and zero-side-effect: the only
    thing it does beyond reading two module constants is call the real
    red-team suite (the same _run() GET /beastmode/red-team calls) --
    see app/beastmode/security_report.py's module docstring for the
    honest-status-model this follows."""
    from app.beastmode.security_report import build_report

    return build_report()


@app.get("/beastmode/mission/readiness")
def beastmode_mission_readiness() -> dict[str, Any]:
    """Is AION Axon ready for one real owner-authorized mission? Never
    itself creates a capability, approval, ledger event, or evolution
    event -- see app/beastmode/mission_readiness.py's module docstring."""
    from app.beastmode.mission_readiness import build_readiness

    return build_readiness()


@app.get("/beastmode/state-machine")
def beastmode_state_machine() -> dict[str, Any]:
    """The formal capability-lifecycle transition table, for direct
    inspection -- this IS the proof that AI cannot self-authorize a
    promotion, not a description of it. Pure constants (states and legal
    transitions); nothing here is computed from live data or secret.

    Read-only, existed as app/beastmode/state_machine.py before this
    endpoint -- see that module's docstring for exactly what it can and
    cannot prove (it's a compatibility mapping FROM the real pipeline's
    own status strings, validated against an explicit transition table;
    the real enforcement lives in app/synapse/engine.py and
    app/governance/approval.py, which this table describes rather than
    replaces)."""
    from app.beastmode.state_machine import (
        CANONICAL_STATES,
        FAILURE_STATES,
        SUCCESS_PATH,
        TERMINAL_STATES,
        _TRANSITIONS,
    )

    return {
        "success_path": list(SUCCESS_PATH),
        "failure_states": list(FAILURE_STATES),
        "terminal_states": sorted(TERMINAL_STATES),
        "transitions": {
            state: sorted(targets) for state, targets in _TRANSITIONS.items()
        },
        "invariant": (
            "A state not listed as a legal target from its current state "
            "is unreachable -- there is no default 'allow' path. In "
            "particular: nothing transitions directly to INSTALLED except "
            "from INSTALLING, which itself is only reachable from APPROVED, "
            "which is only reachable from AWAITING_APPROVAL via a real "
            "human decision (see POST /approvals/{id}/decide, owner-gated)."
        ),
    }
