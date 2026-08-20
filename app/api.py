"""AION AXON core HTTP API.

Every route that can cause execution goes through MissionService ->
Orchestrator -> ExecutionGate. There is no route that executes a tool
directly, and adding one would break the governance guarantee.
"""
from typing import Any, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.capabilities.declarations import catalog_summary
from app.capabilities.registry import registry
from app.governance.approval import approval_manager
from app.governance.autonomy_ledger import (
    SUPERVISION_THRESHOLD,
    autonomy_ledger,
)
from app.governance.kill_switch import kill_switch
from app.memory.firestore_store import firestore_store
from app.missions.service import mission_service

app = FastAPI(
    title="AION AXON Core",
    description="Governed, self-evolving background agent.",
    version="0.2.0",
)


class MissionRequest(BaseModel):
    request: str = Field(..., description="The messy human request.")
    tool: str = Field("calculator", description="Registered tool name.")
    action: str = Field("run tool", description="Action being proposed.")
    risk: str = Field("MEDIUM", description="LOW | MEDIUM | HIGH")
    args: list[Any] = Field(default_factory=list)


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
    return catalog_summary()


class PlannedMissionRequest(BaseModel):
    request: str = Field(..., description="The messy human request.")


@app.post("/missions/planned")
def create_planned_mission(body: PlannedMissionRequest) -> dict[str, Any]:
    """Plan a messy request with Gemini, then run it through the gate."""
    return mission_service.start_planned(body.request)


@app.post("/missions/{mission_id}/resume-planned")
def resume_planned_mission(mission_id: str) -> dict[str, Any]:
    return mission_service.resume_planned(mission_id)


@app.post("/missions")
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


@app.post("/missions/{mission_id}/resume")
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
    tracked = firestore_store.list_capabilities()

    return {
        "supervision_threshold": SUPERVISION_THRESHOLD,
        "tracked_count": len(tracked),
        "capabilities": tracked,
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


@app.get("/evolution")
def evolution_events() -> dict[str, Any]:
    events = firestore_store.list_evolution_events()
    return {"count": len(events), "events": events}


@app.get("/approvals/pending")
def pending_approvals() -> dict[str, Any]:
    pending = firestore_store.list_pending_approvals()
    return {"count": len(pending), "pending": pending}


@app.post("/approvals/{request_id}/decide")
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


@app.post("/killswitch")
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
