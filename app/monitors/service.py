"""Background monitors — the agent working while nobody is watching.

This is the part of the system with the least human supervision, so it
gets the most governance, not the least:

- Every scheduled run executes through the ExecutionGate, exactly like an
  interactive request. A monitor is not a backdoor around the Guardian.
  If the kill switch is on, due monitors do not run.
- Creating a monitor is itself a governed action. Scheduling recurring
  unattended work is a bigger decision than running something once, so it
  needs approval before the first tick, not after.
- A monitor that errors is DISABLED after repeated failures rather than
  retried forever. The project rule is that failures are recorded, never
  loop-retried -- a monitor silently failing every five minutes for a week
  is worse than one that stops and says so.

Scheduling is pull-based: an external scheduler calls /monitors/run-due
and this module decides what is actually due. No message bus, and the
service still scales to zero between ticks.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from app.capabilities.registry import registry
from app.governance.guardian import RiskLevel
from app.memory.firestore_store import firestore_store
from app.workflows.orchestrator import orchestrator
from app.workflows.state import WorkflowState

MIN_INTERVAL_MINUTES = 1
MAX_CONSECUTIVE_FAILURES = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class MonitorService:

    def create(
        self,
        name: str,
        capability: str,
        args: list[str],
        interval_minutes: int,
        description: str = "",
    ) -> dict[str, Any]:
        """Register a recurring check. Refuses to schedule the impossible."""
        if interval_minutes < MIN_INTERVAL_MINUTES:
            return {
                "status": "REJECTED",
                "error": (
                    f"Interval must be at least {MIN_INTERVAL_MINUTES} "
                    "minute."
                ),
            }

        # Refuse at creation rather than failing silently on every tick.
        if not registry.is_implemented(capability):
            return {
                "status": "REJECTED",
                "error": (
                    f"Capability '{capability}' is not implemented, so a "
                    "monitor using it would fail on every run."
                ),
            }

        monitor_id = str(uuid4())

        record = {
            "monitor_id": monitor_id,
            "name": name,
            "description": description,
            "capability": capability,
            "args": args,
            "interval_minutes": interval_minutes,
            "state": "ACTIVE",
            "created_at": _now().isoformat(),
            "next_run_at": _now().isoformat(),
            "run_count": 0,
            "consecutive_failures": 0,
            "last_status": None,
            "last_result": None,
            "last_run_at": None,
        }

        firestore_store.save_monitor(monitor_id, record)

        firestore_store.write_audit_event("MONITOR_CREATED", {
            "monitor_id": monitor_id,
            "name": name,
            "capability": capability,
            "interval_minutes": interval_minutes,
        })

        return {"status": "CREATED", "monitor": record}

    # NOT named `list`: a method called list shadows the builtin for
    # every annotation evaluated later in this class body, so
    # `-> list[dict]` on the next method resolved to the method object.
    def list_all(self) -> list[dict[str, Any]]:
        return firestore_store.list_monitors()

    def get(self, monitor_id: str) -> Optional[dict[str, Any]]:
        return firestore_store.get_monitor(monitor_id)

    def disable(self, monitor_id: str, reason: str) -> dict[str, Any]:
        monitor = firestore_store.get_monitor(monitor_id)

        if monitor is None:
            return {"status": "NOT_FOUND"}

        firestore_store.save_monitor(monitor_id, {
            "state": "DISABLED",
            "disabled_reason": reason,
            "disabled_at": _now().isoformat(),
        })

        firestore_store.write_audit_event("MONITOR_DISABLED", {
            "monitor_id": monitor_id,
            "reason": reason,
        })

        return {"status": "DISABLED", "monitor_id": monitor_id}

    def due(self) -> list[dict[str, Any]]:
        now = _now()

        due = []

        for monitor in firestore_store.list_monitors():
            if monitor.get("state") != "ACTIVE":
                continue

            next_run = _parse(monitor.get("next_run_at"))

            if next_run is None or next_run <= now:
                due.append(monitor)

        return due

    def run_due(self) -> dict[str, Any]:
        """Run every monitor that is due. Called by an external scheduler."""
        results = []

        for monitor in self.due():
            results.append(self.run_one(monitor))

        return {
            "ran": len(results),
            "results": results,
            "checked_at": _now().isoformat(),
        }

    def run_one(self, monitor: dict[str, Any]) -> dict[str, Any]:
        """Execute one monitor THROUGH THE GATE.

        Unattended work gets the same governance as interactive work. A
        monitor that bypassed the gate would be a scheduled way around the
        Guardian, which is precisely the thing a governed agent must not
        have.
        """
        monitor_id = monitor["monitor_id"]

        workflow = WorkflowState(
            user_request=f"scheduled monitor: {monitor.get('name')}"
        )

        outcome = orchestrator.execute_tool(
            workflow,
            monitor["capability"],
            f"scheduled check: {monitor.get('name')}",
            RiskLevel.LOW,
            *monitor.get("args", []),
            description=monitor.get("description") or monitor.get("name"),
            capability=monitor["capability"],
        )

        status = outcome.get("status")

        # "The gate ran it" is not "it worked". Tools report failure in
        # their return payload rather than by raising, so a monitor that
        # only checked the gate status would report healthy forever while
        # every single run errored -- the exact silent failure a monitor
        # exists to prevent.
        result = outcome.get("result")
        tool_errored = (
            isinstance(result, dict) and result.get("status") == "ERROR"
        )

        succeeded = status == "EXECUTED" and not tool_errored

        if tool_errored:
            status = "TOOL_ERROR"

        # Batch 2.5 / monitor governance audit: a kill-switch BLOCKED run
        # is the owner's own deliberate halt, not the capability being
        # broken. Reproduced live: 3 real consecutive due-ticks while the
        # switch stayed active auto-DISABLED a perfectly healthy monitor,
        # purely because the owner had the emergency stop engaged --
        # punishing compliance with their own halt. Counting it toward
        # consecutive_failures (or writing it as a failure at all) was
        # never correct; the underlying capability was never actually
        # attempted, so there is nothing to report failing.
        killswitch_blocked = status == "BLOCKED" and outcome.get("reason") == (
            "Kill switch is active."
        )

        if killswitch_blocked:
            firestore_store.save_monitor(monitor_id, {
                "last_run_at": _now().isoformat(),
                "last_status": "SKIPPED_KILL_SWITCH_ACTIVE",
                "last_reason": outcome.get("reason"),
                # Deliberately NOT advancing next_run_at or run_count/
                # consecutive_failures: this attempt didn't really happen,
                # so the monitor becomes due again on the very next tick
                # once the switch is off, rather than waiting out a full
                # interval it never got to use.
            })

            return {
                "monitor_id": monitor_id,
                "name": monitor.get("name"),
                "status": "SKIPPED_KILL_SWITCH_ACTIVE",
                "result": None,
                "reason": outcome.get("reason"),
                "disabled": False,
            }

        failures = (
            0 if succeeded
            else int(monitor.get("consecutive_failures", 0)) + 1
        )

        update: dict[str, Any] = {
            "last_run_at": _now().isoformat(),
            "last_status": status,
            "last_result": result if succeeded else None,
            "last_error": (result or {}).get("error") if tool_errored else None,
            "last_reason": outcome.get("reason"),
            "run_count": int(monitor.get("run_count", 0)) + 1,
            "consecutive_failures": failures,
            "next_run_at": (
                _now() + timedelta(minutes=monitor["interval_minutes"])
            ).isoformat(),
        }

        # Failures are recorded, never loop-retried forever. A monitor
        # failing silently every five minutes for a week is worse than one
        # that stops and says why.
        if failures >= MAX_CONSECUTIVE_FAILURES:
            update["state"] = "DISABLED"
            update["disabled_reason"] = (
                f"{failures} consecutive failures; last status {status}."
            )
            update["disabled_at"] = _now().isoformat()

        firestore_store.save_monitor(monitor_id, update)

        firestore_store.write_audit_event("MONITOR_RUN", {
            "monitor_id": monitor_id,
            "name": monitor.get("name"),
            "status": status,
            "consecutive_failures": failures,
            "disabled": update.get("state") == "DISABLED",
        })

        return {
            "monitor_id": monitor_id,
            "name": monitor.get("name"),
            "status": status,
            "result": outcome.get("result") if succeeded else None,
            "reason": outcome.get("reason"),
            "disabled": update.get("state") == "DISABLED",
        }


monitor_service = MonitorService()
