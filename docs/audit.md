# AION Axon — Stage-by-Stage Implementation Audit

Generated from the codebase on 20 Aug 2026, branch `feat/core-intelligence`.
Every status below was checked against the actual files, and every "verified"
claim was observed against the **deployed** services, not locally.

Scale: 38 Python modules, ~4,950 lines in `app/`, **180 tests passing**.

---

## 1. Mission Input & Ingestion — **IMPLEMENTED**

| | |
|---|---|
| Files | `app/api.py`, `app/missions/service.py`, `app/agents/plan_schema.py` |
| Functions | `create_mission`, `create_planned_mission`, `MissionService.start`, `MissionService.start_planned` |
| Schemas | `MissionRequest`, `PlannedMissionRequest`, `MissionPlan`, `MissionStep` |
| GCP | Cloud Run, Firestore (`missions`) |

Two intake paths: a direct tool invocation and a planned mission where Gemini
turns a messy sentence into `MissionStep`s. Missions persist to Firestore
rather than process memory, because Cloud Run is multi-instance and an
in-memory mission breaks approval-resume when the two requests land on
different containers.

**Missing:** nothing blocking.

---

## 2. Orchestration Engine — **IMPLEMENTED**

| | |
|---|---|
| Files | `app/missions/engine.py`, `app/workflows/orchestrator.py`, `app/agents/mission_planner.py` |
| Functions | `MissionEngine.run`, `AxonOrchestrator.execute_tool`, `plan_mission` |
| GCP | Cloud Run, Gemini 3.6 Flash via **ADK 2.7 Runner** |

ADK is load-bearing: `Runner` + `InMemorySessionService` drive a planner agent
constrained by `output_schema=MissionPlan`. The engine walks steps one at a
time through the gate, suspends at the exact step needing approval, and
resumes from there rather than replaying — replaying an `EXTERNAL_EFFECT` step
would perform it twice.

**Missing:** no parallel step execution (sequential only). Not a blocker for
the locked demo.

---

## 3. Capability Gap Detection — **IMPLEMENTED**

| | |
|---|---|
| Files | `app/missions/engine.py`, `app/capabilities/registry.py`, `app/workflows/orchestrator.py` |
| Functions | `MissionEngine._gap_for`, `ToolRegistry.get`, `CapabilityNotImplemented` |
| GCP | Firestore (`audit_events` — `CAPABILITY_GAP`) |

Three gap shapes are detected: the planner returned `tool: null`, the
capability is unregistered, or it is DECLARED but unimplemented. The registry
distinguishes IMPLEMENTED from DECLARED precisely so the planner can see the
shape of a job it cannot do and report an honest gap instead of substituting
something else. Gaps are detected **before** execution, so a mission blocks
without partially running.

**Missing:** nothing blocking.

---

## 4. Autonomous Research — **PARTIALLY IMPLEMENTED (externally blocked)**

| | |
|---|---|
| Files | `app/tools/web_research.py` |
| Functions | `search_web`, `_generate_async`, `_receipts` |
| GCP | Gemini API with `GoogleSearch` grounding tool |

Google Search grounding is wired and returns source receipts when quota
allows. **Currently returns `DEGRADED` with zero citations** because Search
grounding is 429 quota-blocked on the free tier.

The fallback is deliberately incapable of looking sourced: `grounded` stays
false and `sources` stays empty even if the fallback response carries chunks.

**Blocker:** Gemini quota. Resolved by the \$150 credits (~25 Aug), not by
code. **No fabricated citation will be added to close this.**

---

## 5. Candidate Capability Generation — **IMPLEMENTED**

| | |
|---|---|
| Files | `app/synapse/generator.py` |
| Functions | `generate_candidate`, `Candidate` schema, `INSTRUCTION` |
| GCP | Gemini 3.6 Flash, structured output via `response_schema` |

The prompt hard-constrains the model to stdlib-only, no `os`/`subprocess`/
network/file access, one top-level function returning a status dict, and a
test covering a normal case **and** a bad-input case.

**Missing:** no retry-with-feedback loop when a candidate fails its tests.
Currently one attempt, then REJECTED.

---

## 6. Safety & AST Screening — **IMPLEMENTED**

| | |
|---|---|
| Files | `app/synapse/safety_screen.py` |
| Functions | `screen`, `_call_name`; `FORBIDDEN_IMPORTS`, `FORBIDDEN_CALLS` |
| GCP | none (pure static analysis) |

Real AST walk, not string matching, so it cannot be fooled by code that merely
*mentions* a dangerous call. Blocks `os`, `sys`, `subprocess`, `socket`,
`importlib`, `pickle`, `ctypes`, `google.*`; blocks `eval`, `exec`, `compile`,
`open`, `__import__`, `getattr`; blocks dunder attribute access. Runs
**before** the sandbox — the sandbox answers "does this work", the screen
answers "should we run it at all".

**Known limitation (documented, not hidden):** sufficiently indirect code can
evade it. This is why the sandbox holds nothing worth stealing — neither layer
is trusted alone.

---

## 7. Sandbox Testing & Execution — **IMPLEMENTED**

| | |
|---|---|
| Files | `sandbox/main.py`, `app/synapse/sandbox_client.py` |
| Functions | `execute` (POST `/execute`), `_limits`, `execute_in_sandbox`, `_identity_token` |
| GCP | **Cloud Run service #2**, OIDC via metadata server |

Ephemeral temp dir, stripped child environment, non-root, `python -I`, and
hard RLIMIT caps on address space, CPU, file size and **fork count**.

Critically, a failing candidate returns `COMPLETED / passed:false` while only
an outage returns `UNREACHABLE`. Collapsing those would let SYNAPSE install a
capability it never actually tested, so an outage **BLOCKS** the acquisition.

**Verified live:** core reaches the sandbox over OIDC and reads
`ZERO_CREDENTIALS`; the public internet gets **HTTP 403** on the same URL.

---

## 8. Gemma Evaluation — **IMPLEMENTED**

| | |
|---|---|
| Files | `app/synapse/evaluator.py` |
| Functions | `evaluate`, `_parse`, `_score` |
| GCP | Gemini API — `gemma-4-26b-a4b-it` |

Model id pinned from a live `models.list()` rather than guessed; the previous
guess (`gemma-3-27b-it`) 404'd at runtime. Chose the MoE variant over the
dense one because §4.2 asks for a *cheap* second opinion.

**Verified discriminating:** a real conversion scored 100/PASS; a fake that
ignores its inputs and returns a constant scored **0/FAIL**. Unavailable or
unparseable responses return `UNSCORED`, never a default pass — a fabricated
score is worse than a missing one, because a missing score makes a human look.

---

## 9. Guardian Security Screening — **IMPLEMENTED**

| | |
|---|---|
| Files | `app/governance/policies.py`, `app/governance/guardian.py`, `app/governance/execution_gate.py` |
| Functions | `find_policy`, `Guardian.evaluate`, `ExecutionGate.execute` |
| GCP | Firestore (`audit_events` — `GUARDIAN_DECISION`) |

Seven policies, deny-by-default, every refusal citing an ID. `PROHIBITED`
policies cannot be satisfied by approval. G-06 makes the override attempt
itself a refusal. Guardian **pre-screens the need** before any tokens are
spent, so a credential-reading request is refused at the doorway rather than
researched and then refused.

**Verified live:** G-04 on the credential request, G-06 on the override.

**Known limitation:** matching is lexical, not semantic. A missed match
degrades to "a human is asked", never "anything runs".

---

## 10. Human-in-the-Loop Approval — **IMPLEMENTED**

| | |
|---|---|
| Files | `app/governance/approval.py`, `app/api.py`, `scripts/approve.py`, `web/src/panels.jsx` |
| Functions | `ApprovalManager.create/decide/get`, `decide_approval`, `ApprovalCard` |
| GCP | Firestore (`approval_requests`), Cloud Run |

Three surfaces: HTTP, CLI, and the Holo-Deck approval card. Approvals persist
in Firestore, so approving on one instance and resuming on another works.
Deciding twice is refused and the first decision stands.

**Closed 21 Aug.** `GET /approvals/{id}/review` returns the source being
authorised, a unified diff against the installed version when there is one,
the sandbox result, the evaluator verdict and the research grounding. The
Holo-Deck approval card renders it behind an explicit "review the code before
approving" toggle -- collapsed by default, because an owner shown a wall of
source on every card learns to scroll past it, while one who clicks has made
a choice.

A first install shows the FULL source rather than a diff against nothing:
"no previous version" is information, not an empty diff to skim.

An approval that concerns no code (a G-02 payment) says so explicitly rather
than rendering blank, which would read as a loading failure.

---

## 11. Capability Installation & Registry — **IMPLEMENTED**

| | |
|---|---|
| Files | `app/synapse/engine.py`, `app/capabilities/registry.py`, `app/capabilities/rehydrate.py` |
| Functions | `SynapseEngine.install`, `_sandbox_proxy`, `rehydrate_capabilities` |
| GCP | Firestore (`capabilities`), Cloud Run |

`install()` re-reads the approval from Firestore rather than trusting the
proposal record. Installed capabilities are **sandbox proxies** — generated
code never executes inside `aion-core`, before or after approval.

Rehydration at startup reconciles the registry to Firestore. Without it, a
capability acquired at 09:26 was gone by 09:40 when Cloud Run recycled the
container — found by live testing, invisible to unit tests.

---

## 12. Evolution Event Execution — **IMPLEMENTED** (closed 21 Aug)

| | |
|---|---|
| Files | `app/synapse/engine.py`, `app/memory/firestore_store.py` |
| Functions | `write_evolution_event`, `SynapseEngine.install` |
| GCP | Firestore (`evolution_events`) |

Evolution events are written with BEFORE / CHANGE / REASON / AFTER, citations,
test results, evaluation and approver. **Verified live:** two events from two
real acquisitions.

**CLOSED.** An acquisition now carries the `mission_id` it exists to unblock,
and `install()` resumes that mission from its blocked step via
`MissionService.resume_blocked`. Routes: `POST /missions/{id}/acquire` and
`POST /missions/{id}/resume-blocked`.

Resume cannot skip a still-open gap: the engine re-evaluates against the live
registry, a rejected approval leaves the mission BLOCKED, and completed steps
are never replayed.

---

## 13. Evidence & Autonomy Ledger — **IMPLEMENTED (on Firestore, not BigQuery)**

| | |
|---|---|
| Files | `app/governance/evidence_engine.py`, `app/governance/autonomy_ledger.py`, `app/governance/verification.py` |
| Functions | `verify_research`, `AutonomyLedger.record_outcome`, `verify_outcome` |
| GCP | Firestore (`capabilities`, `audit_events`) |

SHA-256 output hashing is present (`evidence_engine.py:129`). The checklist
renders exists → readable → expected content → timestamp → hash →
CONFIDENCE %. Promotion +15, demotion −18, supervision threshold 40%, cap 95%.
Demotion has teeth: below threshold the Guardian demands human verification
citing G-07.

**Deliberate divergence:** the ledger lives in **Firestore, not BigQuery**.
Amendment 10 explicitly defers BigQuery analytics to §12 growth. BigQuery is
used as a *data source* (`app/tools/bigquery_public.py`), not as the ledger.
An external auditor expecting a BigQuery ledger will call this a gap; it is a
decision.

**Live-verified 21 Aug:** both capabilities moved 32% → 47% on human
verification (`Human verification under G-07 by anshul: approved`), cleared
the supervision threshold, and resumed executing. Promotion from GROUNDED
research evidence remains untested while grounding is quota-blocked.

---

## 14. Telemetry & Benchmark Tracking — **NOT STARTED** ⚠️

| | |
|---|---|
| Files | `app/observability/telemetry.py`, `app/governance/execution_gate.py` |
| Functions | `usage_of`, `record_model_call`, `timed`, `summarise`; `GET /telemetry` |
| GCP | Firestore (`audit_events`) |

`ExecutionGate._execute_tool` is timed with a monotonic clock -- the one place
a tool actually runs, so no execution path is missed. Model calls in the
generator, evaluator and research tool record real `usage_metadata`.

**Measure, never estimate.** A call that did not report usage is counted as
UNMEASURED rather than assigned a plausible number; `None` and `0` are kept
distinct because they mean opposite things. An inferred token count reads
exactly like a measured one and would quietly corrupt every cost figure
downstream.

Telemetry cannot change behaviour: a measurement failure is swallowed, because
an agent that crashes when its stopwatch breaks is worse than one with no
stopwatch. Failing tools are timed too -- a slow failure is the cost you most
want to see.

**Not captured:** ADK Runner planner tokens. The planner runs through ADK
rather than a direct genai call, so its usage is not yet surfaced.

---

## 15. Rollback & Demotion Engine — **IMPLEMENTED**

| | |
|---|---|
| Files | `app/synapse/engine.py`, `app/capabilities/registry.py`, `app/governance/autonomy_ledger.py` |
| Functions | `SynapseEngine.rollback`, `ToolRegistry.unregister`, `record_outcome` |
| GCP | Firestore |

One call removes a capability from the registry, marks it DISABLED, and emits
its **own** Evolution Event rather than deleting the install — erasing it would
make the chain of custody a story about successes only. Rehydration respects
DISABLED, so a rolled-back capability stays gone across restarts. Automated
demotion is separate and works on evidence.

**Missing:** no rollback button in the Holo-Deck (the API route exists).

---

# Top 3 Immediate Coding Priorities

### 1. Close the loop — auto-resume the blocked mission (Stage 12)
The single most valuable remaining change. Right now the acquisition and the
mission that needed it are joined by a human operator, not by code. The demo
narrates "the mission was blocked, so it acquired the capability, and then
**finished the job**" — and that last clause is currently done by hand.
Carry `mission_id` into the acquisition record and have `install()` resume
`MissionEngine.run` from `next_step_index`.

### 2. Telemetry on the execution gate (Stage 14)
Not started at all, and it is what turns "it works" into "here is what it
cost". A timer plus `usage_metadata` on each audit event unlocks the
before/after evidence the video's closing beat wants.

### 3. Code diff in the approval card (Stage 10)
The owner currently approves a *description*. For a project whose thesis is
accountable autonomy, the human should see the generated source before saying
yes. The data is already in the Skill Passport — this is a UI change, not a
backend one.

**Explicitly NOT priorities:** Search grounding (Stage 4) and the upward
autonomy arc (Stage 13) are blocked on Gemini quota, not on code. They are
fixed by the credits arriving, and no amount of engineering closes them today.
