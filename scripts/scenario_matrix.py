"""Scenario matrix A-G — the governed spine, end to end, offline.

One command, no mocks of the spine, no Gemini required:

    python -m scripts.scenario_matrix

Every scenario drives the real MissionEngine, ExecutionGate, Guardian and
ToolRegistry. Nothing is asserted-and-died-on: it prints EXPECTED vs
ACTUAL for each row so the run is readable as evidence rather than as a
pass/fail bit.

WHY THIS FILE EXISTS. An earlier pass recorded a scenario matrix as
VERIFIED, citing harnesses named graph_e2e*.mjs. Those files were never
committed to any branch (`git log --all --diff-filter=A -- '*graph_e2e*'`
returns nothing), so the evidence could not be re-run by anyone -- which,
under this project's own "no PASS without evidence" rule, means it was
not evidence. This file is committed precisely so the next person can
reproduce the claim instead of trusting it.

SCOPE. Planner-driven scenarios are deliberately absent: they need a real
Gemini credential, and a scenario that cannot run offline does not belong
in a matrix that claims to be reproducible offline. Those stay live
probes (scripts/live_planner_probe.py).
"""
import os
os.environ["AXON_FIRESTORE_MODE"] = "memory"

from app.agents.plan_schema import MissionPlan, MissionStep
from app.capabilities.registry import registry
from app.capabilities.seed import SEED_CAPABILITIES
from app.governance.approval import approval_manager
from app.memory.firestore_store import firestore_store
from app.missions.engine import mission_engine
from app.workflows.state import WorkflowState
from app.tools.calculator import calculate

RESULTS = []


def record(name, expected, actual, ok):
    RESULTS.append((name, expected, actual, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"       expected: {expected}")
    print(f"       actual  : {actual}")


def fresh_workflow(goal):
    return WorkflowState(user_request=goal)


def step(**kw):
    kw.setdefault("kind", "READ_ANALYZE")
    kw.setdefault("risk", "LOW")
    kw.setdefault("args", [])
    return MissionStep(**kw)


# ---------------------------------------------------------------- A
def scenario_a():
    registry.register("calculator", "arith", "LOW", calculate)
    plan = MissionPlan(
        goal="Calculate 50 plus 50",
        steps=[step(step=1, description="Add 50 and 50",
                    tool="calculator", args=["50 + 50"],
                    action="calculate")],
    )
    wf = fresh_workflow("Calculate 50 plus 50")
    out = mission_engine.run(wf, plan)
    res = out["step_results"][0].get("result") if out["step_results"] else None
    ok = (out["status"] == "COMPLETED"
          and out["steps_completed"] == 1
          and str(res).find("100") != -1)
    record("A calculator 50+50 -> COMPLETED, 100",
           "status=COMPLETED, steps 1/1, result contains 100",
           f"status={out['status']}, steps {out['steps_completed']}/"
           f"{out['steps_total']}, result={res!r}", ok)
    return out


# ---------------------------------------------------------------- B
def scenario_b():
    # Genuinely remove web_research so the gap is real, not simulated.
    registry._tools.pop("web_research", None)
    plan = MissionPlan(
        goal="Tell me about Nepal",
        steps=[step(step=1, description="Research Nepal",
                    tool="web_research", args=["Nepal"],
                    action="research")],
    )
    wf = fresh_workflow("Tell me about Nepal")
    out = mission_engine.run(wf, plan)
    blocked = out.get("blocked_on") or {}
    reason = blocked.get("reason", "")
    ok = (out["status"] == "BLOCKED"
          and "web_research" in reason
          and "not registered" in reason
          and out["steps_completed"] == 0)
    record("B Nepal, web_research unregistered -> BLOCKED",
           "status=BLOCKED, reason names web_research as not registered, "
           "0 steps executed, no research text",
           f"status={out['status']}, reason={reason!r}, "
           f"steps={out['steps_completed']}", ok)
    return out


# ---------------------------------------------------------------- C/D
def scenario_c_d():
    def payer(amount):
        return {"status": "OK", "paid": amount}

    registry.register("send_payment", "sends money", "MEDIUM", payer)
    plan = MissionPlan(
        goal="Pay a supplier",
        steps=[step(step=1, description="Send a supplier payment",
                    tool="send_payment", args=["100"], risk="MEDIUM",
                    kind="EXTERNAL_EFFECT", action="pay")],
    )

    # C: pauses for approval
    wf = fresh_workflow("Pay a supplier")
    out = mission_engine.run(wf, plan)
    rid = out.get("approval_request_id")
    pending = firestore_store.list_pending_approvals()
    ok_c = (out["status"] == "AWAITING_APPROVAL"
            and rid is not None
            and out["steps_completed"] == 0
            and any(p.get("request_id") == rid for p in pending))
    record("C approval-required -> pauses, enters approval queue",
           "status=AWAITING_APPROVAL, request_id issued, 0 executed, "
           "visible in pending queue",
           f"status={out['status']}, request_id={rid}, "
           f"steps={out['steps_completed']}, in_queue="
           f"{any(p.get('request_id') == rid for p in pending)}", ok_c)

    # D: rejection must not execute
    approval_manager.decide(rid, approved=False, decided_by="phase4-test")
    rec = firestore_store.get_approval(rid)
    executed = [e for e in firestore_store.list_audit_events()
                if e.get("event_type") == "ACTION_EXECUTED"
                and e.get("action") == "pay"]
    ok_d = rec.get("status") == "REJECTED" and len(executed) == 0
    record("D rejection -> NO execution",
           "approval REJECTED, zero ACTION_EXECUTED audit events for 'pay'",
           f"approval_status={rec.get('status')}, "
           f"ACTION_EXECUTED count={len(executed)}", ok_d)


# ---------------------------------------------------------------- E
def scenario_e():
    from pydantic import ValidationError
    try:
        MissionPlan(steps=[{"step": "not-an-int", "description": "x"}])
        actual, ok = "accepted a malformed plan", False
    except ValidationError as exc:
        n = len(exc.errors())
        actual = f"pydantic ValidationError with {n} field error(s)"
        ok = True
    except Exception as exc:
        actual, ok = f"unexpected {type(exc).__name__}: {exc}", False
    record("E malformed plan -> safe, typed failure",
           "rejected at the schema boundary, no crash, no execution",
           actual, ok)


# ---------------------------------------------------------------- F
def scenario_f():
    def boom(*_a, **_k):
        raise ZeroDivisionError("division by zero")

    registry.register("faulty_tool", "always raises", "LOW", boom)
    plan = MissionPlan(
        goal="Trigger a real tool failure",
        steps=[step(step=1, description="Divide by zero",
                    tool="faulty_tool", args=["1/0"], action="divide")],
    )
    wf = fresh_workflow("Trigger a real tool failure")
    out = mission_engine.run(wf, plan)
    rec0 = out["step_results"][0] if out["step_results"] else {}
    reason = rec0.get("reason") or rec0.get("result")
    ok = (out["status"] == "FAILED"
          and out["steps_completed"] == 0
          and "division by zero" in str(reason))
    record("F real tool failure -> FAILED with the real reason",
           "status=FAILED, 0 completed, reason carries 'division by zero'",
           f"status={out['status']}, steps={out['steps_completed']}, "
           f"reason={reason!r}", ok)


# ---------------------------------------------------------------- G
def scenario_g():
    registry.register("calculator", "arith", "LOW", calculate)
    plan = MissionPlan(
        goal="Calculate 50 plus 50",
        steps=[step(step=1, description="Add 50 and 50",
                    tool="calculator", args=["50 + 50"],
                    action="calculate")],
    )
    outs = []
    for _ in range(3):
        wf = fresh_workflow("Calculate 50 plus 50")
        outs.append(mission_engine.run(wf, plan))
    statuses = {o["status"] for o in outs}
    counts = {o["steps_completed"] for o in outs}
    ok = statuses == {"COMPLETED"} and counts == {1}
    record("G repeated execution -> consistent state",
           "3 identical runs all COMPLETED with 1/1",
           f"statuses={statuses}, steps_completed={counts}", ok)


def main():
    for cap in SEED_CAPABILITIES:
        if not cap.implemented:
            registry.declare(cap.name, cap.description, cap.risk)

    print("=" * 68)
    print("SCENARIO MATRIX A-G - REAL LOCAL E2E (no Gemini required)")
    print("=" * 68)
    scenario_a()
    scenario_b()
    scenario_c_d()
    scenario_e()
    scenario_f()
    scenario_g()

    print()
    print("=" * 68)
    passed = sum(1 for *_x, ok in RESULTS if ok)
    print(f"SCENARIO MATRIX RESULT: {passed}/{len(RESULTS)} passed")
    for name, _e, _a, ok in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print("=" * 68)


if __name__ == "__main__":
    main()
