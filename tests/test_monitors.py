"""Background monitors — the agent working unattended.

This is the least-supervised part of the system, so the tests are about
governance, not scheduling arithmetic: a monitor must not become a
scheduled way around the Guardian.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

from datetime import datetime, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402

import app.capabilities.bootstrap  # noqa: E402,F401
from app.governance.kill_switch import kill_switch  # noqa: E402
from app.memory.firestore_store import firestore_store  # noqa: E402
from app.monitors.service import (  # noqa: E402
    MAX_CONSECUTIVE_FAILURES,
    monitor_service,
)


@pytest.fixture(autouse=True)
def clean():
    firestore_store.monitors.clear()
    kill_switch.deactivate()
    yield
    firestore_store.monitors.clear()
    kill_switch.deactivate()


def make(capability="calculator", args=None, interval=60):
    return monitor_service.create(
        name="watch totals",
        capability=capability,
        args=args if args is not None else ["2 + 2"],
        interval_minutes=interval,
    )


def test_monitor_is_created_and_due_immediately():
    result = make()

    assert result["status"] == "CREATED"
    assert len(monitor_service.due()) == 1


def test_monitor_on_an_unimplemented_capability_is_refused():
    """Refuse at creation rather than failing silently on every tick."""
    result = make(capability="write_brief")

    assert result["status"] == "REJECTED"
    assert "not implemented" in result["error"]
    assert monitor_service.list_all() == []


def test_interval_floor_is_enforced():
    assert make(interval=0)["status"] == "REJECTED"


def test_run_executes_and_reschedules():
    make()

    outcome = monitor_service.run_due()

    assert outcome["ran"] == 1
    assert outcome["results"][0]["status"] == "EXECUTED"

    monitor = monitor_service.list_all()[0]

    assert monitor["run_count"] == 1
    assert monitor["consecutive_failures"] == 0
    assert monitor_service.due() == [], "should not be due again immediately"


def test_kill_switch_halts_scheduled_work():
    """A monitor must not be a scheduled way around the Guardian.

    Batch 2.5 monitor governance audit: status changed from the raw
    execution_gate "BLOCKED" to the monitor-specific
    "SKIPPED_KILL_SWITCH_ACTIVE" -- see
    test_killswitch_blocked_runs_never_count_toward_consecutive_failures
    for why this distinction exists and matters. The underlying property
    this test protects -- the capability never actually runs while
    halted -- is unchanged; only the status label is more precise now.
    """
    make()
    kill_switch.activate("stop everything")

    outcome = monitor_service.run_due()

    assert outcome["results"][0]["status"] == "SKIPPED_KILL_SWITCH_ACTIVE"
    assert outcome["results"][0]["result"] is None


def test_killswitch_blocked_runs_never_count_toward_consecutive_failures():
    """Batch 2.5 monitor governance audit: reproduced live before this
    fix -- 3 real consecutive due-ticks while the kill switch stayed
    active auto-DISABLED a perfectly healthy monitor, purely because the
    owner had their own emergency stop engaged. The capability was never
    actually attempted (execution_gate blocked it before the tool ran),
    so there was nothing that failed -- counting it as a failure
    punished the owner's own halt. A kill-switch-blocked run must leave
    the monitor's failure count and ACTIVE state untouched, and must not
    advance next_run_at (so it's re-checked on the very next tick once
    the switch is off, not stuck waiting out a full interval it never
    got to use)."""
    make(interval=1)
    monitor_id = monitor_service.list_all()[0]["monitor_id"]

    kill_switch.activate("extended halt")

    for _ in range(MAX_CONSECUTIVE_FAILURES + 2):
        firestore_store.save_monitor(monitor_id, {
            "next_run_at": datetime.now(timezone.utc).isoformat(),
        })
        monitor_service.run_due()

    monitor = monitor_service.get(monitor_id)

    assert monitor["state"] == "ACTIVE"
    assert monitor["consecutive_failures"] == 0
    assert monitor["last_status"] == "SKIPPED_KILL_SWITCH_ACTIVE"
    assert monitor["run_count"] == 0

    # And it resumes normally once the switch is off, on the very next
    # tick -- not delayed by a full interval it never actually used.
    kill_switch.deactivate()
    firestore_store.save_monitor(monitor_id, {
        "next_run_at": datetime.now(timezone.utc).isoformat(),
    })
    monitor_service.run_due()

    monitor = monitor_service.get(monitor_id)
    assert monitor["last_status"] == "EXECUTED"
    assert monitor["run_count"] == 1


def test_repeated_failures_disable_rather_than_retry_forever():
    """Failures are recorded, never loop-retried.

    A monitor failing silently every few minutes for a week is worse than
    one that stops and says why.
    """
    make(args=["not-arithmetic!!"])

    for _ in range(MAX_CONSECUTIVE_FAILURES):
        monitor = monitor_service.list_all()[0]
        monitor["next_run_at"] = datetime.now(timezone.utc).isoformat()
        firestore_store.save_monitor(monitor["monitor_id"], monitor)
        monitor_service.run_due()

    monitor = monitor_service.list_all()[0]

    assert monitor["state"] == "DISABLED"
    assert "consecutive failures" in monitor["disabled_reason"]


def test_disabled_monitor_is_never_due():
    make()
    monitor_id = monitor_service.list_all()[0]["monitor_id"]

    monitor_service.disable(monitor_id, "owner stopped it")

    assert monitor_service.due() == []


def test_not_yet_due_monitor_does_not_run():
    make()
    monitor = monitor_service.list_all()[0]

    future = datetime.now(timezone.utc) + timedelta(hours=1)
    firestore_store.save_monitor(
        monitor["monitor_id"], {"next_run_at": future.isoformat()},
    )

    assert monitor_service.run_due()["ran"] == 0


def test_a_tool_that_returns_an_error_payload_counts_as_a_failure():
    """Regression: "the gate ran it" is not "it worked".

    Tools report failure in their return value rather than by raising, so
    a monitor checking only the gate status reported healthy forever while
    every run errored.
    """
    make(args=["not-arithmetic!!"])

    outcome = monitor_service.run_due()

    assert outcome["results"][0]["status"] == "TOOL_ERROR"

    monitor = monitor_service.list_all()[0]

    assert monitor["consecutive_failures"] == 1
    assert monitor["last_result"] is None
