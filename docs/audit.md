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

**CLOSED, corrected 21 Aug after a real live run exposed a gap the tests
missed.** An acquisition carries the `mission_id` it exists to unblock, and
`install()` resumes that mission from its blocked step via
`MissionService.resume_blocked`. Routes: `POST /missions/{id}/acquire` and
`POST /missions/{id}/resume-blocked`.

Resume cannot skip a still-open gap: the engine re-evaluates against the live
registry, a rejected approval leaves the mission BLOCKED, and completed steps
are never replayed.

**What "closed" missed, found live 21 Aug (`e9a44a5`):** every test only
covered the gap shape where the planner *names* an unimplemented declared
capability. The first real live run of the full loop (mission `75d24305`)
hit the OTHER gap shape — the planner leaves `tool: null` when it finds no
registered capability at all — and `install()`'s auto-resume fired
correctly (zero manual step) but the mission stayed BLOCKED forever,
because nothing wrote the newly installed capability's name back into
the step. Fixed: `resume_blocked` now backfills a null `tool` with the
capability `install()` just installed. Regression test added for this
specific gap shape, proven by reverting and watching it fail with the
exact live symptom. The lesson, not just the fix: "implemented and tested"
had not yet meant "run once for real" — this is why live verification
found a gap code review and CI both missed.

**Second finding, same live session, immediately after the tool-name fix
above was deployed (`aion-core-00015-rsb`) and confirmed working live:**
with the tool name now correctly backfilled, the mission (`3c60715b`,
capability `analyze_complaint_urgency`) tried to run for real — and
crashed. The freshly installed capability's function required an
argument (`complaint_text`) that was never supplied: a `tool: null`
step's `args` also stays `[]`, for the same root reason its `tool` stayed
`null` — the planner's instructions only cover arg format for
capabilities that already exist, and this one didn't exist at planning
time. Fixed the same way (`655102c`): `resume_blocked` now also backfills
empty `args` with the mission's original free-text request (the only
material ever supplied for that step), never overwriting an explicit
args list. Two regression tests added, one proven against a revert. Not
yet deployed or re-verified live as of this commit — next step is a
fresh gap so the already-installed `analyze_complaint_urgency` capability
doesn't mask whether the fix actually works.

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

## 14. Telemetry & Benchmark Tracking — **IMPLEMENTED** (21 Aug, `b330877`)

Live-verified same day: `GET /telemetry` on `aion-core` reports 453 audit
events examined, 4 real model calls (14,698 measured tokens across
`research_degraded` x2, `generate`, `evaluate`) and 1 tool execution
(260ms) from tonight's Acquisition #3 run. Numbers came from the model's
own `usage_metadata`, not inferred.

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

---

# Known defect — mission resume drops tool arguments (found 21 Aug, not fixed)

`POST /missions/{id}/resume` calls the mission's tool with whatever `args`
were stored on the mission at creation time — but a mission created from a
free-text `request` (rather than an explicit `tool`/`args` pair) never has
its plan text parsed into real arguments. The stored `args` stays `[]`.

Reproduced live: a mission built from `{"request": "Calculate 12.5 * 4 and
tell me the result"}` planned correctly (Gemini's own plan says "12.5 x
4 = 50"), went to `AWAITING_APPROVAL` on `calculator`/`run tool`, was
approved, then `resume` failed with `calculate() missing 1 required
positional argument: 'expression'` — because `args` was `[]` the whole
time.

**Impact:** any mission that reaches a tool via free-text planning rather
than an explicit `tool`+`args` call is unrunnable after approval. Missions
posted directly with `tool`/`args` (the pattern every other test in this
file uses) are unaffected — this is specifically the planner-to-tool-call
handoff.

**Not fixed tonight** — out of scope for the Acquisition #3 verification
pass that found it. Whoever picks this up next: the fix is parsing the
plan's `STEPS`/args intent into the mission's stored `args` before
`AWAITING_APPROVAL`, or having `resume` re-derive args from the plan at
resume time.

---

# Top 3 Immediate Coding Priorities — SUPERSEDED (21 Aug, corrected below)

All three items below were done as of this morning (`d451dcf`, `b330877`,
21 Aug ~05:00-05:15 IST) — Stage 12 auto-resume, Stage 14 telemetry, and
Stage 10's code diff all shipped together and this list was never updated
to say so. Left below for history rather than deleted, per the repo's
append-don't-rewrite rule; do not re-implement any of these.

### 1. ~~Close the loop — auto-resume the blocked mission (Stage 12)~~ DONE
`app/synapse/engine.py:367-375` — `install()` carries `mission_id` from
the acquisition record and calls `mission_service.resume_blocked(mission_id)`
directly. Verified live: Acquisition #3 (21 Aug) installed and its result
was checked separately by running the capability fresh, not by re-running
a blocked mission — this specific auto-resume path was not re-exercised
tonight, only confirmed present in code and history.

### 2. ~~Telemetry on the execution gate (Stage 14)~~ DONE
See section 14 above — live-verified 21 Aug with real token/latency data
from tonight's Acquisition #3 run.

### 3. ~~Code diff in the approval card (Stage 10)~~ DONE
Shipped in the same commit batch (`d451dcf`). Not independently
re-verified live tonight.

## Mission-resume args bug — FIXED (21 Aug, `3c6d488`)

`POST /missions/{id}/resume` used to drop tool arguments for any mission
created from a free-text `request` rather than an explicit `tool`+`args`
pair, because `MissionRequest.tool` defaulted to `"calculator"` and
`.args` defaulted to `[]`. Root cause: this endpoint never parsed
`request` into a real tool call — `POST /missions/planned` already does
that via the real planner — so the defaults let a caller skip the tool
call entirely, get a narrative Gemini plan describing real work, sail
through approval, then fail at resume with a bare `TypeError`. Fixed by
making `tool`/`action`/`args` required, not defaulted, so a caller who
omits them now gets a 422 at the door instead of a mission that fails
downstream. Regression test added and proven: reverted the fix, watched
the new test fail against the original defaults, restored the fix,
watched it pass. All 67 tests in `test_api.py`/`test_reliability.py`/
`test_owner_auth.py` green.

## Full-suite state leak — FIXED (22 Aug, found 21 Aug)

A bare `pytest -q` produced **121 errors** that never appeared file-by-file,
or in CI. Root cause was not a test bug: `app.memory.firestore_store` picks
its backend ONCE at import time from `AXON_FIRESTORE_MODE`, so the choice
belongs to whichever module imports it first. Every file under `tests/` sets
the variable itself, which looks like protection but is not — it only works
if a test file imports first.

It did not. **`scripts/test_approval_resume.py`** was a manual probe, not a
test, and matched pytest's `test_*.py` pattern; `scripts/` sorts before
`tests/`, so a bare run imported it first, built a real `AxonFirestore`, and
every later fixture calling `.capabilities.clear()` died with
`AttributeError` — 121 errors from one stray import.

**CI never saw it, because CI passes `tests` explicitly.** So the suite was
green for the maintainers and broken for anyone who cloned the repo and ran
`pytest`. That gap mattered more than the errors.

Fixed in three layers, deepest first:

1. **Rootdir `conftest.py`** sets `AXON_FIRESTORE_MODE=memory` (via
   `setdefault`, so a deliberate integration run can still override).
   pytest loads it before any test module, so import order stops mattering.
2. **`pytest.ini` with `testpaths = tests`** — a bare `pytest` now does what
   CI does instead of wandering into `scripts/` and `sandbox/`.
3. **`scripts/test_approval_resume.py` renamed to
   `scripts/probe_approval_resume.py`** so it cannot masquerade as a test
   again; the subprocess reference in `tests/test_approval_resume_e2e.py`
   was updated with it.

`tests/test_store_isolation.py` guards the guard, and deliberately does NOT
set the env var itself — it tests the conftest rather than its own preamble.
Proven by deleting `conftest.py` and watching it fail against a real
`AxonFirestore`.

**The property this protects is not a green suite.** It is that a test run
never reads or writes the live project's Firestore.

Result: **264 passed, 0 failed, 0 errors** on both `pytest -q` and
`pytest -q tests`. One genuine regression surfaced along the way and was
fixed: `test_declared_capability_cannot_be_invoked_at_all` hardcoded
`write_brief` as its declared-but-unbuilt example, and `write_brief` was
implemented in `7ac0125`. It now picks an unimplemented capability
dynamically, so it keeps testing the property as capabilities get built
rather than decaying as the codebase improves.

**Explicitly NOT priorities:** Search grounding (Stage 4) and the upward
autonomy arc (Stage 13) are blocked on Gemini quota, not on code. They are
fixed by the credits arriving, and no amount of engineering closes them today.
