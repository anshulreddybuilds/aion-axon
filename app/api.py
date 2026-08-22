"""AION AXON core HTTP API.

Every route that can cause execution goes through MissionService ->
Orchestrator -> ExecutionGate. There is no route that executes a tool
directly, and adding one would break the governance guarantee.
"""
import os
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.capabilities.declarations import catalog_summary
from app.capabilities.registry import registry
from app.capabilities.rehydrate import rehydrate_capabilities
from app.governance.approval import approval_manager
from app.governance.autonomy_ledger import (
    SUPERVISION_THRESHOLD,
    autonomy_ledger,
)
from app.governance.ground_truth import all_facts, lookup, record_fact
from app.governance.kill_switch import kill_switch
from app.governance.owner_auth import require_owner
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=PREVIEW_CHANNEL_ORIGIN,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
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
    request: str = Field(..., description="The messy human request.")
    tool: str = Field(..., description="Registered tool name.")
    action: str = Field(..., description="Action being proposed.")
    risk: str = Field("MEDIUM", description="LOW | MEDIUM | HIGH")
    args: list[Any] = Field(..., description="Positional args for the tool.")


class ApprovalDecision(BaseModel):
    approved: bool
    decided_by: str = "owner"


class KillSwitchRequest(BaseModel):
    active: bool
    reason: str = "Human emergency stop"


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


class PlannedMissionRequest(BaseModel):
    request: str = Field(..., description="The messy human request.")


@app.post("/missions/planned", dependencies=[Depends(require_owner)])
def create_planned_mission(body: PlannedMissionRequest) -> dict[str, Any]:
    """Plan a messy request with Gemini, then run it through the gate."""
    return mission_service.start_planned(body.request)


@app.post("/missions/{mission_id}/acquire", dependencies=[Depends(require_owner)])
def acquire_for_mission(mission_id: str) -> dict[str, Any]:
    """Propose the capability a BLOCKED mission is missing.

    Reads the gap off the mission itself rather than making the caller
    restate it, and ties the acquisition back to the mission so that
    installing it finishes the original job.
    """
    mission = mission_service.get(mission_id)

    if mission is None:
        return {"status": "NOT_FOUND", "mission_id": mission_id}

    if mission.get("status") != "BLOCKED":
        return {
            "status": "FAILED",
            "error": f"Mission is {mission.get('status')}, not BLOCKED.",
        }

    gap = mission.get("blocked_on") or {}

    need = gap.get("capability_description") or gap.get("description")

    if not need:
        return {"status": "FAILED", "error": "Mission records no gap."}

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

    return synapse.propose(need, mission_id).to_dict()


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
    key: str = Field(..., description="Short identifier for the fact.")
    statement: str = Field(..., description="What the fact is about.")
    value: str = Field(..., description="The independently known value.")
    source: str = Field(..., description="Where it came from. Required.")
    recorded_by: str = Field("owner", description="Who recorded it.")


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
def match_ground_truth(query: str) -> dict[str, Any]:
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
    need: str = Field(..., description="The capability AION Axon lacks.")
    mission_id: Optional[str] = Field(
        None,
        description="Mission this acquisition should unblock, if any.",
    )


@app.post("/synapse/propose", dependencies=[Depends(require_owner)])
def synapse_propose(body: AcquisitionRequest) -> dict[str, Any]:
    """Run the acquisition loop up to — and stopping at — human approval.

    This route can never install anything. It ends at AWAITING_APPROVAL
    at best; installation requires a separate call after a real decision.
    """
    return synapse.propose(body.need, body.mission_id).to_dict()


@app.post("/synapse/install/{capability}", dependencies=[Depends(require_owner)])
def synapse_install(capability: str) -> dict[str, Any]:
    """Install an approved capability. Re-reads the approval from
    Firestore, so calling this without a decision changes nothing."""
    return synapse.install(capability)


class RollbackRequest(BaseModel):
    reason: str = Field(..., description="Why the capability is removed.")


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
    name: str
    capability: str
    args: list[str] = Field(default_factory=list)
    interval_minutes: int = Field(60, ge=1)
    description: str = ""


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
    reason: str = "Disabled by owner"


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
