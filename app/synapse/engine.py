"""SYNAPSE — the governed capability acquisition loop.

    gap -> RESEARCH -> generate -> safety screen -> sandbox test
        -> evaluate -> GUARDIAN screen -> owner approval
        -> install -> Evolution Event

Two properties this loop must never lose:

1. **Nothing installs without an explicit human yes.** The pipeline can
   run end to end and still stop, permanently, at approval. Acquisition
   is a proposal process, not an automation.

2. **Generated code never runs inside aion-core.** Not during testing, and
   not after installation. An installed capability is a proxy that calls
   the sandbox. Approval means the owner accepted the capability, not that
   the code earned a seat next to the credentials.

Every stage records what it saw, so the Skill Passport can answer "why
does this skill exist?" with provenance rather than assertion.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.capabilities.registry import registry
from app.governance.approval import approval_manager
from app.governance.autonomy_ledger import autonomy_ledger
from app.governance.guardian import Decision, RiskLevel, guardian
from app.memory.firestore_store import firestore_store
from app.synapse.evaluator import evaluate
from app.synapse.generator import Candidate, generate_candidate
from app.synapse.safety_screen import screen
from app.synapse.sandbox_client import execute_in_sandbox
from app.tools.web_research import search_web

MIN_EVALUATOR_SCORE = 50


@dataclass
class AcquisitionRecord:
    """The Skill Passport: NEED -> ... -> ROLLBACK."""

    need: str
    stage: str = "STARTED"
    status: str = "IN_PROGRESS"

    # The mission this acquisition exists to unblock, if any. Carrying it
    # is what lets install() finish the original job instead of leaving a
    # human to re-run it.
    mission_id: Optional[str] = None

    research: dict[str, Any] = field(default_factory=dict)
    candidate: Optional[dict[str, Any]] = None
    safety: dict[str, Any] = field(default_factory=dict)
    tests: dict[str, Any] = field(default_factory=dict)
    evaluation: dict[str, Any] = field(default_factory=dict)
    guardian: dict[str, Any] = field(default_factory=dict)
    approval_request_id: Optional[str] = None

    reason: Optional[str] = None
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "need": self.need,
            "stage": self.stage,
            "status": self.status,
            "mission_id": self.mission_id,
            "research": self.research,
            "candidate": self.candidate,
            "safety": self.safety,
            "tests": self.tests,
            "evaluation": self.evaluation,
            "guardian": self.guardian,
            "approval_request_id": self.approval_request_id,
            "reason": self.reason,
            "started_at": self.started_at,
        }


class SynapseEngine:

    def propose(
        self,
        need: str,
        mission_id: Optional[str] = None,
        allow_retry: bool = False,
    ) -> AcquisitionRecord:
        """Run every stage up to (and stopping at) human approval.

        `allow_retry` is OFF by default, matching every call site that
        existed before this parameter did (the live UI, stage_take.py, and
        every test in the suite) byte-for-byte. Passing True permits
        exactly ONE additional generate+screen+sandbox attempt if the
        first candidate fails its own sandbox test, feeding the real
        stderr back into generation. Bounded to one retry -- unbounded
        retrying on a real rejection would spend quota chasing something
        that may not be fixable, and would blur "the candidate was
        rejected" into "the system tried until it got lucky".
        """
        record = AcquisitionRecord(need=need, mission_id=mission_id)

        # --- GUARDIAN PRE-SCREEN --------------------------------------
        # Screen the NEED before spending a single token on it. A request
        # for a credential-reading capability must be refused at the
        # doorway, not researched, generated and then refused.
        pre = guardian.evaluate(
            f"acquire capability: {need}",
            RiskLevel.MEDIUM,
            description=need,
        )

        if pre.decision == Decision.REFUSE:
            record.stage = "GUARDIAN_PRESCREEN"
            record.status = "REFUSED"
            record.reason = pre.reason
            record.guardian = {
                "decision": pre.decision.value,
                "policy_id": pre.policy_id,
                "policy_title": pre.policy_title,
            }
            self._audit(record, "SYNAPSE_REFUSED")
            return record

        # --- RESEARCH --------------------------------------------------
        record.stage = "RESEARCH"
        research = search_web(
            f"How to implement in pure Python, standard library only: {need}"
        )

        record.research = {
            "status": research.get("status"),
            "grounded": bool(research.get("grounded")),
            "sources": research.get("sources") or [],
            "source_count": research.get("source_count") or 0,
            "findings": (research.get("findings") or "")[:4000],
            "degraded_reason": research.get("degraded_reason"),
        }

        # --- GENERATE / SCREEN / SANDBOX --------------------------------
        #
        # A plain loop of 1 (allow_retry=False) or up to 2 (allow_retry=True)
        # attempts. Every branch below is IDENTICAL to what existed before
        # this loop was added; the only new behaviour is that a sandbox
        # failure with attempts remaining feeds the real stderr back into
        # generation and tries once more, instead of returning immediately.
        max_attempts = 2 if allow_retry else 1
        prior_failure: Optional[str] = None
        candidate = None
        tests: dict[str, Any] = {}

        for attempt in range(1, max_attempts + 1):
            record.stage = "GENERATE"
            # Only pass prior_failure on an actual retry (attempt > 1).
            # The first attempt calls generate_candidate with exactly the
            # same 2 positional args as before this loop existed, so every
            # test (and any other caller) that mocks generate_candidate
            # with a 2-argument stub keeps working unchanged.
            if prior_failure is not None:
                candidate, error = generate_candidate(
                    need, record.research.get("findings"), prior_failure,
                )
            else:
                candidate, error = generate_candidate(
                    need, record.research.get("findings"),
                )

            if candidate is None:
                record.status = "FAILED"
                record.reason = error
                self._audit(record, "SYNAPSE_FAILED")
                return record

            record.candidate = candidate.model_dump()

            # --- SAFETY SCREEN -------------------------------------------
            record.stage = "SAFETY_SCREEN"
            screened = screen(candidate.code)
            record.safety = screened.to_dict()

            if not screened.safe:
                # A safety rejection is never retried -- retrying a policy
                # refusal until it stops triggering would be indistinguishable
                # from evading the screen.
                record.status = "REJECTED"
                record.reason = (
                    "Candidate failed the static safety screen: "
                    + "; ".join(screened.findings)
                )
                self._audit(record, "SYNAPSE_REJECTED")
                return record

            # --- SANDBOX TEST ----------------------------------------------
            record.stage = "SANDBOX_TEST"
            tests = execute_in_sandbox(candidate.code, candidate.test)
            record.tests = tests

            if tests.get("status") == "UNREACHABLE":
                # A sandbox outage is NOT a failing candidate. Installing on
                # an untested candidate because the tester was down is the
                # worst available outcome. Never retried -- the sandbox
                # being down is not something a different candidate fixes.
                record.status = "BLOCKED"
                record.reason = (
                    "Sandbox unreachable; candidate was never tested. "
                    f"{tests.get('reason')}"
                )
                self._audit(record, "SYNAPSE_BLOCKED")
                return record

            if tests.get("passed"):
                break  # a working candidate -- proceed to evaluation

            if attempt == max_attempts:
                record.status = "REJECTED"
                record.reason = (
                    "Candidate failed its own tests in the sandbox."
                    if max_attempts == 1
                    else "Candidate failed its own tests in the sandbox "
                         f"after {max_attempts} attempts."
                )
                self._audit(record, "SYNAPSE_REJECTED")
                return record

            # One attempt remains: carry the REAL stderr into the next
            # generation, not a generic "try again".
            prior_failure = (
                tests.get("stderr") or tests.get("reason")
                or "Sandbox test failed with no captured output."
            )

        # --- EVALUATE ---------------------------------------------------
        record.stage = "EVALUATE"
        record.evaluation = evaluate(
            candidate.name, candidate.description, candidate.code, tests,
        )

        score = record.evaluation.get("score")

        if score is not None and score < MIN_EVALUATOR_SCORE:
            record.status = "REJECTED"
            record.reason = (
                f"Evaluator scored {score}, below the "
                f"{MIN_EVALUATOR_SCORE} floor: "
                f"{record.evaluation.get('reason')}"
            )
            self._audit(record, "SYNAPSE_REJECTED")
            return record

        # An UNSCORED evaluation does not block the proposal -- it travels
        # to the owner clearly marked, so the human sees that no machine
        # opinion is available rather than a silent pass.

        # --- GUARDIAN SCREEN OF THE BUILT CAPABILITY --------------------
        record.stage = "GUARDIAN_SCREEN"
        decision = guardian.evaluate(
            f"install capability: {candidate.name}",
            RiskLevel(candidate.risk if candidate.risk in
                      ("LOW", "MEDIUM", "HIGH") else "MEDIUM"),
            description=candidate.description,
            capability=candidate.name,
        )

        record.guardian = {
            "decision": decision.decision.value,
            "reason": decision.reason,
            "policy_id": decision.policy_id,
            "policy_title": decision.policy_title,
        }

        if decision.decision == Decision.REFUSE:
            record.status = "REFUSED"
            record.reason = decision.reason
            self._audit(record, "SYNAPSE_REFUSED")
            return record

        # --- HUMAN APPROVAL ---------------------------------------------
        record.stage = "AWAITING_APPROVAL"
        record.status = "AWAITING_APPROVAL"

        request = approval_manager.create(
            action=f"install capability: {candidate.name}",
            risk=RiskLevel.MEDIUM,
            reason=(
                f"SYNAPSE proposes installing '{candidate.name}': "
                f"{candidate.description}"
            ),
            # Named so the approval can be traced back to the code it
            # authorises. An approval that cannot reach the source is a
            # signature on an unread document.
            policy_id="INSTALL",
            capability=candidate.name,
        )

        record.approval_request_id = request.request_id

        firestore_store.save_capability(candidate.name, {
            "name": candidate.name,
            "description": candidate.description,
            "risk": candidate.risk,
            "state": "VALIDATING",
            "implemented": False,
            "version": 0,
            "passport": record.to_dict(),
        })

        self._audit(record, "SYNAPSE_AWAITING_APPROVAL")

        return record

    def install(self, capability_name: str) -> dict[str, Any]:
        """Install an APPROVED capability. Refuses without a real approval."""
        stored = firestore_store.get_capability(capability_name)

        if stored is None:
            return {"status": "FAILED", "error": "Unknown capability."}

        passport = stored.get("passport") or {}
        request_id = passport.get("approval_request_id")

        if not request_id:
            return {"status": "FAILED", "error": "No approval on record."}

        approval = firestore_store.get_approval(request_id)

        # The approval is re-read from Firestore rather than trusted from
        # the passport: the passport is a record of what was proposed, not
        # evidence of what the owner decided.
        if approval is None or approval.get("status") != "APPROVED":
            return {
                "status": "APPROVAL_REQUIRED",
                "request_id": request_id,
                "reason": "Human approval has not been granted.",
            }

        candidate = passport.get("candidate") or {}

        registry.register(
            candidate["name"],
            candidate["description"],
            candidate.get("risk", "LOW"),
            self._sandbox_proxy(candidate),
        )

        before_count = registry.counts()["implemented"] - 1

        firestore_store.save_capability(capability_name, {
            "state": "READY",
            "implemented": True,
            "version": int(stored.get("version", 0)) + 1,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "approved_by": approval.get("decided_by"),
            # Kept so the NEXT version can be diffed against what is
            # actually running, rather than against the last thing that
            # happened to be proposed.
            "installed_code": candidate.get("code"),
        })

        event_id = firestore_store.write_evolution_event({
            "capability_id": candidate["name"],
            "before": (
                f"AION Axon could not: {passport.get('need')}. "
                f"Registry had {before_count} implemented capabilities."
            ),
            "change": f"Acquired capability '{candidate['name']}'.",
            "reason": passport.get("need"),
            "after": (
                f"AION Axon can now: {candidate['description']} "
                f"Registry has {registry.counts()['implemented']} "
                f"implemented capabilities."
            ),
            "research_citations": (
                passport.get("research", {}).get("sources") or []
            ),
            "grounded": passport.get("research", {}).get("grounded", False),
            "test_results": passport.get("tests"),
            "evaluation": passport.get("evaluation"),
            "safety_screen": passport.get("safety"),
            "approver": approval.get("decided_by"),
            "approved_at": approval.get("decided_at"),
        })

        # A human read the Skill Passport -- tests, evaluation, safety
        # screen -- and approved. That IS a verification event, and the
        # strongest kind this system has. Recording it seeds the ledger so
        # the capability starts above the supervision threshold.
        #
        # Without this, a freshly installed capability sat at the starting
        # 32% and G-07 demanded approval on its very first use, asking the
        # owner to approve the same thing twice in a row. Approval fatigue
        # is a governance failure, not a governance feature: an owner who
        # is asked constantly stops reading.
        promotion = autonomy_ledger.record_outcome(
            candidate["name"],
            verified=True,
            reason=(
                f"Human approved after reviewing the Skill Passport "
                f"({approval.get('decided_by')})."
            ),
        )

        result = {
            "status": "INSTALLED",
            "capability": candidate["name"],
            "evolution_event_id": event_id,
            "implemented_count": registry.counts()["implemented"],
            "autonomy_before": promotion.before,
            "autonomy_after": promotion.after,
        }

        # THE LOOP CLOSES HERE. If this acquisition existed to unblock a
        # mission, finish that mission now rather than leaving a human to
        # re-run it. "It hit a gap, acquired the capability, and then
        # finished the job" should be one action, not two.
        #
        # Imported locally: mission_service reaches the orchestrator, and a
        # module-level import here would form a cycle.
        mission_id = passport.get("mission_id")

        if mission_id:
            from app.missions.service import mission_service

            # The engine re-evaluates the gap against the live registry, so
            # this cannot skip a step that is still genuinely missing.
            # capability_name lets resume_blocked backfill a `tool: null`
            # step -- the planner could not name a capability that did not
            # exist yet, so nothing else ever tells the step what to call
            # now that this acquisition just installed one for it.
            result["mission_resumed"] = mission_service.resume_blocked(
                mission_id, capability_name=capability_name,
            )

        return result

    def rollback(self, capability_name: str, reason: str) -> dict[str, Any]:
        """Remove an installed capability and record why.

        The last step of the Skill Passport. Rollback is recorded as an
        Evolution Event of its own rather than by deleting the original:
        the acquisition really happened, and erasing it would make the
        chain of custody a story about successes only.
        """
        stored = firestore_store.get_capability(capability_name)

        if stored is None:
            return {"status": "FAILED", "error": "Unknown capability."}

        removed = registry.unregister(capability_name)

        firestore_store.save_capability(capability_name, {
            "state": "DISABLED",
            "implemented": False,
            "rolled_back_at": datetime.now(timezone.utc).isoformat(),
            "rollback_reason": reason,
        })

        event_id = firestore_store.write_evolution_event({
            "capability_id": capability_name,
            "before": f"Capability '{capability_name}' was installed.",
            "change": f"Rolled back '{capability_name}'.",
            "reason": reason,
            "after": (
                f"Capability '{capability_name}' is DISABLED. Registry has "
                f"{registry.counts()['implemented']} implemented "
                "capabilities."
            ),
            "rollback": True,
        })

        return {
            "status": "ROLLED_BACK",
            "capability": capability_name,
            "was_registered": removed,
            "evolution_event_id": event_id,
        }

    def _sandbox_proxy(self, candidate: dict[str, Any]):
        """Build a callable that runs the capability IN THE SANDBOX.

        Generated code never executes inside aion-core, before or after
        approval. This closure is what keeps the trust boundary permanent
        instead of a testing-time formality.
        """
        code = candidate["code"]
        entrypoint = candidate["entrypoint"]

        def invoke(*args: Any) -> dict[str, Any]:
            call_args = ", ".join(repr(str(a)) for a in args)

            harness = (
                "import json\n"
                f"print(json.dumps({entrypoint}({call_args})))\n"
            )

            outcome = execute_in_sandbox(code, harness)

            if not outcome.get("passed"):
                return {
                    "status": "ERROR",
                    "error": (
                        outcome.get("reason")
                        or (outcome.get("stderr") or "")[:500]
                        or "Sandbox execution failed."
                    ),
                }

            import json as _json

            try:
                return _json.loads((outcome.get("stdout") or "").strip())
            except Exception:  # noqa: BLE001
                return {
                    "status": "ERROR",
                    "error": "Capability returned unparseable output.",
                    "stdout": (outcome.get("stdout") or "")[:500],
                }

        invoke.__name__ = candidate["name"]

        return invoke

    def _audit(self, record: AcquisitionRecord, event: str) -> None:
        firestore_store.write_audit_event(event, {
            "need": record.need,
            "stage": record.stage,
            "status": record.status,
            "reason": record.reason,
            "capability": (record.candidate or {}).get("name"),
            "policy_id": record.guardian.get("policy_id"),
        })


synapse = SynapseEngine()
