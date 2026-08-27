"""Mission lifecycle, persisted so approval-resume survives a restart.

Cloud Run is multi-instance and scales to zero. An in-memory mission store
would make the approval demo fail the moment the request that approves a
mission lands on a different instance than the one that created it, so
mission state goes to Firestore alongside the approval record.

This layer NEVER executes anything itself. Every execution goes through
the orchestrator and therefore through the Unified Execution Gate.
"""
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import app.capabilities.bootstrap  # noqa: F401 - registers default tools
from app.agents.mission_planner import plan_mission
from app.agents.plan_schema import MissionPlan
from app.governance.guardian import RiskLevel
from app.memory.firestore_store import firestore_store
from app.missions.engine import mission_engine
from app.workflows.orchestrator import orchestrator
from app.workflows.state import WorkflowState


class MissionService:

    def start(
        self,
        request: str,
        tool: str,
        action: str,
        risk: str,
        args: Optional[list[Any]] = None,
    ) -> dict[str, Any]:

        args = args or []
        risk_level = RiskLevel(risk)

        workflow = orchestrator.create_workflow(request)

        result = orchestrator.execute_tool(
            workflow,
            tool,
            action,
            risk_level,
            *args,
            # The planned path passed these and the direct path did not,
            # so G-07 autonomy supervision was silently skipped whenever a
            # capability was invoked directly. A governance check that
            # depends on which endpoint the caller used is not a check.
            description=request,
            capability=tool,
        )

        mission_id = str(uuid4())

        self._persist(mission_id, workflow, tool, action, risk, args, result)

        return {
            "mission_id": mission_id,
            "workflow_id": workflow.workflow_id,
            "status": workflow.status,
            "result": result,
            "approval_request_id": workflow.approval_request_id,
            "plan": self._plan_of(workflow),
        }

    def start_planned(self, request: str) -> dict[str, Any]:
        """Plan a messy request, then execute the plan through the gate."""
        workflow = WorkflowState(user_request=request)
        mission_id = str(uuid4())

        plan, error = plan_mission(request)

        if plan is None:
            workflow.update_status("FAILED")
            workflow.error = error

            firestore_store.save_mission(mission_id, {
                "mission_id": mission_id,
                "workflow_id": workflow.workflow_id,
                "request": request,
                "mode": "planned",
                "status": "FAILED",
                "error": error,
                "created_at": workflow.created_at,
            })

            return {
                "mission_id": mission_id,
                "status": "FAILED",
                "error": error,
            }

        return self.start_from_plan(plan, request)

    def start_from_plan(self, plan: MissionPlan, request: str) -> dict[str, Any]:
        """Execute an already-built MissionPlan through the real gate.

        The second entry point into the same engine `start_planned()`
        uses -- not a second engine. `start_planned()` gets its plan from
        the Gemini-backed planner reasoning over free text;
        `create_mission_from_graph()` (app/api.py) gets an equally real
        `MissionPlan` compiled directly from a user-authored graph
        (real capability names, real risk levels, real `$STEP_N`
        dependency edges). From this point on -- governance, sandbox,
        approval, persistence, resume -- the two are indistinguishable to
        the engine, because they produce the identical validated schema.
        """
        workflow = WorkflowState(user_request=request)
        mission_id = str(uuid4())

        workflow.plan = [step.model_dump() for step in plan.steps]
        workflow.update_status("EXECUTING")

        summary = mission_engine.run(workflow, plan)

        self._persist_planned(mission_id, workflow, request, plan, summary)

        return {
            "mission_id": mission_id,
            "workflow_id": workflow.workflow_id,
            "goal": plan.goal,
            "plan": [step.model_dump() for step in plan.steps],
            **summary,
        }

    def blocked_step_input(self, mission_id: str) -> Optional[str]:
        """A sample of what the BLOCKED step will actually be handed.

        SYNAPSE was being asked to build a capability from a sentence
        describing the job and nothing else, so it had to guess the shape
        of its own input. On 22 Aug it guessed `{date, value}` records for
        a step that receives `{year, total}` rows straight out of
        BigQuery. The candidate was safe, its own tests passed, and Gemma
        scored it 100 — every check answered a question that was not
        "will this fit the data?", and the capability was unusable.

        Resolving the blocked step's own args against the steps that
        already ran gives the real thing rather than a description of it.
        Truncated, because the need travels into a prompt and a thousand
        rows would crowd out the instruction.
        """
        mission = firestore_store.get_mission(mission_id)

        if mission is None or not mission.get("plan_document"):
            return None

        try:
            plan = MissionPlan.model_validate(mission["plan_document"])
        except Exception:  # noqa: BLE001 - a malformed plan is not fatal here
            return None

        index = mission.get("next_step_index", 0)

        if not (0 <= index < len(plan.steps)):
            return None

        completed = [
            r for r in mission.get("step_results", [])
            if r.get("status") == "EXECUTED"
        ]

        if not completed:
            return None

        resolved = mission_engine._resolve_args(plan.steps[index].args, completed)

        # An arg that still carries its own placeholder resolved to
        # nothing, and a sample of nothing would mislead the generator
        # more than no sample at all.
        usable = [a for a in resolved if isinstance(a, str) and "$STEP_" not in a]

        if not usable:
            return None

        sample = max(usable, key=len)

        return sample[:1200] + (" …(truncated)" if len(sample) > 1200 else "")

    def resume_blocked(
        self, mission_id: str, capability_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Continue a mission that BLOCKED on a missing capability.

        This is what closes the loop. Without it, "the agent hit a gap,
        acquired the capability, and then finished the job" has a human
        performing that last clause by re-running the mission by hand.

        The engine re-evaluates the gap from the live registry, so calling
        this before the capability actually exists blocks again rather
        than proceeding. Nothing here assumes the acquisition succeeded.

        `capability_name` backfills the blocked step's `tool` field when
        it was `null` in the plan. The planner leaves `tool: null` when it
        found no registered capability at all for a step -- that step can
        never name a tool on its own, so nothing the engine does moves it
        off BLOCKED unless the caller that just installed a capability for
        this exact gap tells it what to call. Only a `null` tool is ever
        overwritten: a step that already names a declared-but-unimplemented
        capability keeps that name, since SYNAPSE's candidate is presumed
        to have been proposed to fill that exact gap.

        The same backfill covers `args`. The planner's instructions only
        explain arg format for capabilities that already exist -- for a
        `tool: null` step, the capability does not exist yet at planning
        time, so there is no signature to follow and args stays `[]`.
        Found live 21 Aug: this let the freshly installed capability run
        with zero arguments and crash on its own required parameter. The
        mission's original free-text request is the only material that
        was ever given for this step, so it becomes the sole positional
        arg -- only when the step's args are still empty, never
        overwriting an explicit one.
        """
        mission = firestore_store.get_mission(mission_id)

        if mission is None:
            return {"status": "FAILED", "error": "Unknown mission."}

        if mission.get("mode") != "planned":
            return {"status": "FAILED", "error": "Not a planned mission."}

        if mission.get("status") != "BLOCKED":
            return {
                "status": "FAILED",
                "error": (
                    "Mission is not blocked. "
                    f"Current status: {mission.get('status')}"
                ),
            }

        plan = MissionPlan.model_validate(mission["plan_document"])

        index = mission.get("next_step_index", 0)

        if (
            capability_name
            and 0 <= index < len(plan.steps)
            and plan.steps[index].tool is None
        ):
            plan.steps[index].tool = capability_name

            if not plan.steps[index].args:
                plan.steps[index].args = [mission["request"]]

        workflow = WorkflowState(
            user_request=mission["request"],
            workflow_id=mission["workflow_id"],
        )
        workflow.status = "EXECUTING"

        completed = [
            r for r in mission.get("step_results", [])
            if r.get("status") == "EXECUTED"
        ]

        summary = mission_engine.run(
            workflow, plan, start_at=index, completed=completed,
        )

        self._persist_planned(
            mission_id, workflow, mission["request"], plan, summary,
        )

        firestore_store.write_audit_event("MISSION_RESUMED_AFTER_GAP", {
            "mission_id": mission_id,
            "resumed_at_step": index,
            "status": summary["status"],
        })

        return {"mission_id": mission_id, "goal": plan.goal, **summary}

    def resume_planned(self, mission_id: str) -> dict[str, Any]:
        """Continue a planned mission from the step that suspended it.

        BUG-005 (AION_AXON_BUG_AND_PROBLEM_REGISTER.md): this method built
        its WorkflowState with `status = "EXECUTING"` and never set
        `approval_request_id` on it, while `approve_and_resume()` requires
        `workflow.status == "AWAITING_APPROVAL"` AND a matching
        `approval_request_id` before it will do anything -- so this route
        failed 100% of the time for every mid-mission approval, silently,
        for as long as it existed. Nothing ever exercised it: the sibling
        single-tool `resume()` sets both correctly (compare its own
        `workflow.status = "AWAITING_APPROVAL"` / `workflow
        .approval_request_id = ...` two lines below), and this method was
        apparently written without copying them. Found by writing the
        test this bug's own docstring says should have existed.
        """
        mission = firestore_store.get_mission(mission_id)

        if mission is None:
            return {"status": "FAILED", "error": "Unknown mission."}

        if mission.get("mode") != "planned":
            return {"status": "FAILED", "error": "Not a planned mission."}

        if mission.get("status") != "AWAITING_APPROVAL":
            return {
                "status": "FAILED",
                "error": (
                    "Mission is not awaiting approval. "
                    f"Current status: {mission.get('status')}"
                ),
            }

        plan = MissionPlan.model_validate(mission["plan_document"])

        workflow = WorkflowState(
            user_request=mission["request"],
            workflow_id=mission["workflow_id"],
        )
        workflow.status = "AWAITING_APPROVAL"
        workflow.approval_request_id = mission["approval_request_id"]

        index = mission.get("next_step_index", 0)
        completed = [
            r for r in mission.get("step_results", [])
            if r.get("status") == "EXECUTED"
        ]

        # Resume the suspended step through the approved path, then let
        # the engine carry on with the rest. Args are re-resolved against
        # what already ran -- the plan document stores the step's
        # ORIGINAL, unresolved args (e.g. "$STEP_1"), and the engine's own
        # per-step loop only resolves them right before the first
        # execution attempt. Without doing the same here, a step that
        # both needs approval AND depends on an earlier step's real
        # output would resume with the literal placeholder string instead
        # of that output.
        step = plan.steps[index]
        resolved_args = mission_engine._resolve_args(step.args, completed)

        approved = orchestrator.approve_and_resume(
            workflow,
            step.tool,
            step.action,
            RiskLevel(step.risk),
            mission["approval_request_id"],
            *resolved_args,
        )

        if approved.get("status") != "EXECUTED":
            summary = {
                "status": approved.get("status", "UNKNOWN"),
                "steps_completed": len(completed),
                "steps_total": len(plan.steps),
                "next_step_index": index,
                "step_results": completed,
                "approval_request_id": mission["approval_request_id"],
                "blocked_on": None,
                # approve_and_resume()'s various guard/failure paths use
                # "error" or "reason" depending on which one fired -- read
                # both so a real message is never silently dropped
                # (BUG-005's second half: this used to read only
                # "reason", which is None on every guard-failure path,
                # turning an explained FAILED into an unexplained one).
                "reason": approved.get("reason") or approved.get("error"),
            }
        else:
            completed.append({
                "step": step.step,
                "description": step.description,
                "tool": step.tool,
                "action": step.action,
                "risk": step.risk,
                "kind": step.kind,
                "status": "EXECUTED",
                "result": approved.get("result"),
                "approved": True,
                "at": datetime.now(timezone.utc).isoformat(),
            })

            summary = mission_engine.run(
                workflow, plan, start_at=index + 1, completed=completed,
            )

        self._persist_planned(
            mission_id, workflow, mission["request"], plan, summary,
        )

        return {"mission_id": mission_id, "goal": plan.goal, **summary}

    def _persist_planned(
        self,
        mission_id: str,
        workflow: WorkflowState,
        request: str,
        plan: MissionPlan,
        summary: dict[str, Any],
    ) -> None:
        firestore_store.save_mission(mission_id, {
            "mission_id": mission_id,
            "workflow_id": workflow.workflow_id,
            "request": request,
            "mode": "planned",
            "goal": plan.goal,
            "status": summary["status"],
            "plan_document": plan.model_dump(),
            "step_results": summary["step_results"],
            "next_step_index": summary["next_step_index"],
            "steps_completed": summary["steps_completed"],
            "steps_total": summary["steps_total"],
            "approval_request_id": summary.get("approval_request_id"),
            "blocked_on": summary.get("blocked_on"),
            "created_at": workflow.created_at,
        })

    def resume(self, mission_id: str) -> dict[str, Any]:
        mission = firestore_store.get_mission(mission_id)

        if mission is None:
            return {"status": "FAILED", "error": "Unknown mission."}

        if mission.get("status") != "AWAITING_APPROVAL":
            return {
                "status": "FAILED",
                "error": (
                    "Mission is not awaiting approval. "
                    f"Current status: {mission.get('status')}"
                ),
            }

        # Rebuild just enough workflow state to resume. The gate re-reads
        # the approval from Firestore regardless, so this cannot be used
        # to fake an approval.
        workflow = WorkflowState(
            user_request=mission["request"],
            workflow_id=mission["workflow_id"],
        )
        workflow.status = "AWAITING_APPROVAL"
        workflow.approval_request_id = mission["approval_request_id"]

        result = orchestrator.approve_and_resume(
            workflow,
            mission["tool"],
            mission["action"],
            RiskLevel(mission["risk"]),
            mission["approval_request_id"],
            *mission.get("args", []),
        )

        self._persist(
            mission_id,
            workflow,
            mission["tool"],
            mission["action"],
            mission["risk"],
            mission.get("args", []),
            result,
        )

        return {
            "mission_id": mission_id,
            "workflow_id": workflow.workflow_id,
            "status": workflow.status,
            "result": result,
        }

    def get(self, mission_id: str) -> Optional[dict[str, Any]]:
        return firestore_store.get_mission(mission_id)

    def _plan_of(self, workflow: WorkflowState) -> Optional[str]:
        for observation in workflow.observations:
            data = observation.get("data") or {}
            if observation.get("source") == "planner":
                return data.get("plan")
        return None

    def _persist(
        self,
        mission_id: str,
        workflow: WorkflowState,
        tool: str,
        action: str,
        risk: str,
        args: list[Any],
        result: dict[str, Any],
    ) -> None:
        firestore_store.save_mission(mission_id, {
            "mission_id": mission_id,
            "workflow_id": workflow.workflow_id,
            "request": workflow.user_request,
            "status": workflow.status,
            "tool": tool,
            "action": action,
            "risk": risk,
            "args": args,
            "approval_request_id": workflow.approval_request_id,
            "result": result,
            "plan": self._plan_of(workflow),
            "created_at": workflow.created_at,
            "persisted_at": datetime.now(timezone.utc).isoformat(),
        })


mission_service = MissionService()
