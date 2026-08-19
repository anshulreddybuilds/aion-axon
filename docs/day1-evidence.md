# Day 1 Evidence — AION-AXON

Recorded 19 Aug 2026. Every claim here carries the run that produced it.
Anything without evidence is marked NOT VERIFIED rather than assumed.

## Governed execution loop — PASS

Full path: ADK/Gemini planning -> approval persistence -> execution gate
-> human approval -> gated resume -> execution.

- Approval requests persist to `approval_requests`; audit to `audit_events`.
- `execution_gate` re-checks the kill switch on BOTH the initial and the
  approved path (`app/governance/execution_gate.py:19,85`). Approval does
  not bypass the gate.
- Resume refuses unless status is `AWAITING_APPROVAL`, the approval id
  matches the workflow, and `approved is True`.

## Tests

- CI run `32252020824` (commit `35657a6`): 1 passed, 0 failed, 0 skipped.
- Local, offline (GOOGLE_API_KEY unset, ADC suppressed): 1 passed.

## CI — GREEN

First green: run `32250956121`, commit `f0ce0ec`.

Root cause of the preceding red streak: `kill_switch.py` constructed
`firestore.Client()` at module import time, outside the
`AXON_FIRESTORE_MODE` switch in `firestore_store.py`. Memory mode never
reached it, so the import chain died on `DefaultCredentialsError`.
The workflow's env-var syntax was never the problem.

Proven both directions: with credentials suppressed, memory mode passes
and non-memory mode fails with `DefaultCredentialsError`.

## Gemini — VERIFIED LIVE

- Model `gemini-3.6-flash`, confirmed present among the 37 models the key
  can list (`scripts/check_gemini_models.py`).
- `scripts/live_planner_probe.py` returned a full structured plan:
  `LIVE ADK + GEMINI PLANNER: PASS`.
- The generated plan respected the governance instruction: every step
  classified READ/ANALYZE, `APPROVALS_REQUIRED: None`.

Quota note: an earlier key on a prepay-billing project returned
`429 RESOURCE_EXHAUSTED` (credits depleted). That response still proved
auth, model name and transport were correct. Replaced with a free-tier
key. A 429 degrades to a `PLANNER_ERROR` observation; it does not crash
the governed loop.

## Google framework — google-adk 2.7.1, LOAD-BEARING

`planner_agent` is executed by an ADK `Runner` with an
`InMemorySessionService` (`app/agents/planner_runner.py`). Before this,
ADK was installed and declared but never invoked — the agent object was
read only for its `.name` and `.model` strings.

Planning is advisory: it produces text, never side effects. All execution
still passes the Unified Execution Gate, so a planner failure cannot
widen what AION AXON is permitted to do.

## Firestore — REAL WRITE VERIFIED

Real-backend run (no `AXON_FIRESTORE_MODE`), project `aion-axon-2026`:

- Approval `ec2877a1-f195-400b-956a-132e7c4f03e1`
- Workflow `92ab0d13-81e1-4e7e-9b7d-24b0b5745819`
- create -> update -> read round-trip returned `status=APPROVED`,
  `decided_by=anshul` from a real Firestore read.
- Result: `EXECUTED`, `1250 * 1.18 = 1475.0`, workflow `COMPLETED`.

Memory mode (`MemoryFirestore`, `MemoryKillSwitch`) exists only for
deterministic local/CI runs. Real Firestore remains the production
backend and is never replaced by a permanent mock.

## Hackathon eligibility

- Gemini: PASS
- Google framework: PASS
- Both: PASS

## Open items

1. Free-tier quota is the planner's ceiling.
2. `feat/end-to-end-workflow` is stale at `ee636dc`, behind main.
3. Only the calculator tool is exercised end to end; `web_research` is
   registered but has no e2e coverage.
4. CI covers the offline path only. No live Gemini or real-Firestore test
   runs in CI, by design — those stay manual probes.
