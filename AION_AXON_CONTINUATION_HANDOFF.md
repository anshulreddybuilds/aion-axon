# AION AXON CONTINUATION HANDOFF

Written at the end of a credit-efficient security/reliability pass. Read this before re-deriving anything — it is deliberately complete.

## Notion Source of Truth

A canonical cross-agent "AION AXON — Source of Truth" page now exists in Notion, nested under the existing "AION Axon — Hackathon Master Plan" page: https://app.notion.com/p/3c782243366881aea778e04c35afceba

It mirrors this file's content in a 30-section structure (Executive Summary, Security Posture, Decision Log, Agent Handoff Log, etc.) for Claude Code / Antigravity / ChatGPT / human contributors who don't have this file in their working directory. **Repository/this file remain authoritative for exact current state** (git is ground truth for code); the Notion page is authoritative for cross-agent narrative/decision history. If they ever disagree, trust this file and the repo, then update Notion to match — never the reverse.

Update both whenever a checkpoint materially changes.

## Update 20 — Day 2: BUG-011 (reason/error class in v5), real voice output, documented real-time boundary, full contract audit, HEAD fd54235

Directive: a Day 2/3 execution command with an explicit priority order
(P0 don't break governed execution; P1 finish voice→graph→execute; P2
real-time graph execution; P3 contract audit; P4 UX hardening; P5
tests/docs) and an explicit instruction to distinguish VERIFIED / NOT
VERIFIED / ENVIRONMENT BLOCKED at every stage, never claim physical
microphone verification, and never fabricate execution state.

**P3 (contract audit) found a real bug, so it was fixed before anything
else** — the audit's own point is to catch exactly this class before it
ships. See **BUG-011** above for the full writeup: the `/v5` run panel
showed bare status words (`FAILED`, `REFUSED`, `APPROVAL_REQUIRED`) with
no reason, and a real human REJECTION was indistinguishable from "not
yet decided" because `orchestrator.approve_and_resume()` maps both to
the same `APPROVAL_REQUIRED` word. Fixed via two new pure, tested
functions in `graphExecutionState.js` (`toneForMissionStatus`,
`runOutcomeText`) plus capturing the real decision from `decide()`'s own
response in `AppV5.jsx`'s `decideDirect()`. Also applied the BUG-008/010
install-outcome check to `decideAcquisition()`, which previously did not
check `api.install()`'s result at all — found proactively while auditing
the same file, not from a report.

**P1 (voice)**. The 17-point checklist was audited item by item against
the existing `/v5` implementation (built Day 1): mic button, real
transcript into an editable input, voice reusing the exact same
`plannedMission()`/`planToGraph()` path as text, listening state,
stop/cancel, empty-transcript non-submission, human-readable errors, and
honest permission-denied handling (`speechRecognition.js`'s existing
`not-allowed` → "Microphone blocked…" mapping, unchanged, already
correct) were all already true from Day 1. The one real gap: voice
OUTPUT was never wired into `/v5` at all — `AppV4.jsx` has it,
`AppV5.jsx` didn't. Added a mute/unmute toggle (off by default, mirrors
`AppV4.jsx`) that speaks the SAME `runOutcomeText()` sentence now shown
on screen — never a separate scripted line — at every terminal point
(`compileAndRun`, `planIt`, `decideDirect`, `decideAcquisition`).

**P2 (real-time)**. Audited what the backend can actually stream: there
is NO endpoint that reports per-step progress for a normal mission run
— `mission_engine.run()` executes synchronously and returns one
terminal/suspended summary. Per-node EXECUTING state during that call
would have to be invented client-side, which the project's own rules
explicitly forbid ("never fabricate node progress" / "do not manufacture
execution states purely in React"). Implemented the smallest honest
version instead, and documented the boundary in code, not just here:
a single global "Planning the mission…" / "Running the mission…" banner
covers the in-flight period for the main plan (no per-node fabrication),
while the ONE sub-flow that IS genuinely real-time — capability
acquisition, via the already-existing `GET /missions/{id}/acquire/
stream` — now drives a live per-node override on the canvas: the exact
node that BLOCKED shows the real current SYNAPSE stage (Guardian
pre-screen / research / generate / sandbox / evaluate) as it actually
streams in, via the same `describeStage()` `AppV4.jsx` already uses.

**P4 (UX hardening)**. Audited the full checklist (node overlap,
unreadable labels, impossible-to-select nodes, accidental connections,
dangling edges, duplicate ids, invalid/empty/cyclic graph submission,
capability-unavailable state, failed compilation, backend failure,
approval-required state, blocked state, loading states, error messages,
basic keyboard access to controls). Everything on the list was already
correct from Day 1's own verification pass or is structurally impossible
by construction (node ids are never user-editable, so duplicate ids
can't occur from the UI even though the compiler still rejects them
defensively; dangling edges are pruned automatically on node deletion).
No changes made here beyond BUG-011 itself — per this pass's own rule
("if something is already correct, do not modify it merely to create
work"), nothing was touched that didn't need to be.

**P5 (testing)** — the required user journeys, verified with real
headless-browser runs against a live local backend
(`AXON_FIRESTORE_MODE=memory`), not mocked:

- **C. GRAPH EDIT → EXECUTE**: VERIFIED (Day 1's `graph_e2e.mjs`,
  rerun clean this pass — 3-node dependency graph reaches COMPLETED
  with the real computed answer 50).
- **D. GRAPH → BLOCKED → ACQUISITION**: VERIFIED (Day 1's
  `graph_e2e_gap.mjs`, rerun clean — a real live acquisition trace
  renders as it streams).
- **E. GRAPH → APPROVAL → RESUME**: VERIFIED, new this pass
  (`graph_e2e_approval.mjs`, 9/9 checks) — a real MEDIUM-risk direct
  approval gate, both APPROVE (reaches COMPLETED with the real computed
  answer 2) and REJECT (shows the honest rejection sentence, approval
  panel correctly clears, never fabricates COMPLETED) paths proven.
  This is also BUG-011's own regression proof.
- **A. TEXT → GRAPH → EXECUTE** and **B. VOICE → GRAPH → EXECUTE**:
  PARTIALLY VERIFIED / ENVIRONMENT BLOCKED for the "a real plan
  populates real graph nodes" leg specifically — this sandbox has no
  real `GOOGLE_API_KEY` (session-scoped in the owner's own shell per
  CLAUDE.md, not available here), so the planner's real Gemini call
  fails with a real `400 INVALID_ARGUMENT` "API key not valid" error.
  Everything else in the journey IS genuinely verified: for B
  specifically (`graph_e2e_voice.mjs`, 8/8 checks), a SIMULATED (no
  physical microphone — not claimed) `SpeechRecognition` implementation,
  injected before page load exactly like `speechRecognition.test.mjs`'s
  existing unit-level pattern, delivers a real transcript into the
  editable Plan-it input; the transcript is verified editable; an empty
  transcript is verified to leave "Plan it" disabled (never
  auto-submits); clicking "Plan it" is verified via the actual captured
  network request to call the real `POST /missions/planned` carrying
  the real transcript text verbatim; and the real (failed, in this
  key-less environment) response is verified to render honestly with
  zero fabricated graph nodes — the exact "handle it honestly either
  way" property this pass required. **A real key would need to be
  supplied to see this journey's full graph-population leg complete
  end to end; that specific leg is NOT VERIFIED here, and is not
  claimed as verified.**

`npm run build` clean. All pre-existing `*.test.mjs` files remain green;
`graphExecutionState.test.mjs` grew from 6 to 16 tests (10 new, covering
`toneForMissionStatus`/`runOutcomeText`'s full status matrix). Backend
suite unaffected by this frontend-only commit: still 560 passed, 2
skipped.

**Notion**: not attempted this pass — still blocked (see Update 18/19).
**NotebookLM**: still unavailable.

Current HEAD: `fd54235` — supersedes every hash below.

## Update 19 — Graphical Mission Builder, Day 1: backend compiler entry point + visual canvas (v5), HEAD 6f33f86

**Scope authorization**: the owner explicitly authorized a major scope
expansion beyond this file's own anti-scope-creep rules and the
CLAUDE.md hard rules, with 3 days left before the Aug 30 submission:
"BUILD THE GRAPHICAL MISSION BUILDER. BUILD THE VOICE INTEGRATION.
CONNECT BOTH TO THE EXISTING AION MISSION ENGINE... You do NOT need to
ask me again whether to proceed with these phases." Flagged the
conflict via a direct question before proceeding; the owner's answer
above is the standing authorization for this and the next 1-2 passes
of related work, not re-litigated here.

Hard constraint honored throughout: **no second execution engine.**
Everything below produces the exact same `MissionPlan`/`MissionStep`
schema (`app/agents/plan_schema.py`) the Gemini planner already
produces, and runs through the identical `mission_engine.run()`.

**Backend** (commit `9925f97`, prior to this entry's HEAD):
- `MissionService.start_planned()` (`app/missions/service.py`) split
  into itself (plan from free text) + a new
  `start_from_plan(plan, request)` shared method that actually executes
  and persists. Verified byte-identical behavior for the existing
  planner path (555 passed both before/after, pure extraction).
- New `POST /missions/from-graph` (`app/api.py`): owner-auth +
  rate-limited identically to `/missions/planned`, takes a `MissionPlan`
  body directly (Pydantic validates the schema for free), rejects an
  empty `steps` list honestly, otherwise calls `start_from_plan()`.
- 5 new backend tests (`tests/test_api.py`) proving a graph-authored
  plan gets the SAME real `$STEP_N` dependency resolution, honest
  `BLOCKED` gap detection, and real `AWAITING_APPROVAL` governance
  gating as a planner-authored one — plus empty-graph rejection and
  owner-auth enforcement. **560 passed, 2 skipped** (up from 555, zero
  regressions).

**Frontend** (commit `6f33f86`, this entry's HEAD) — new surface at `/v5`:
- `graphCompiler.js` (pure, framework-free): `compileGraphToPlan(nodes,
  edges, goal)` topologically sorts nodes via Kahn's algorithm (stable
  tie-break = node array order) and compiles to a real `MissionPlan`. A
  node references another node's real output with `@nodeId` /
  `@nodeId.field` inside its own args text; this is the ONLY
  graph-specific notation anywhere — it compiles straight to the
  engine's own `$STEP_N`/`$STEP_N.field` convention and is completely
  gone from the object that gets posted. Cycles (including self-loops),
  dangling edges, duplicate node ids, unresolved `@id` references, and
  empty graphs are all rejected with a specific honest message, never
  silently accepted or silently broken. `planToGraph(plan)` is the
  exact inverse — reconstructs an editable node/edge graph from any
  `MissionPlan`, round-trip tested. 13 unit tests
  (`graphCompiler.test.mjs`).
- `graphExecutionState.js` (pure): `nodeStatuses({nodes,
  stepNumberById, missionResult})` maps a REAL mission result onto
  per-node visual state (COMPLETED / FAILED / BLOCKED / AWAITING
  APPROVAL / not yet run). A node with nothing in the real result to
  report is "not yet run" — never guessed at, never fabricated as
  failed. 6 unit tests (`graphExecutionState.test.mjs`).
- `v5/AppV5.jsx`: the actual canvas. Add/edit/delete/drag nodes
  (pointer-event based, no drag library), connect/disconnect edges
  (click "connect →" then click a target; SVG arrows render the wiring;
  a compact edge list below the canvas allows removal), a capability
  picker sourced live from `GET /capabilities`, "Compile & Run" against
  `POST /missions/from-graph`. Inline approval UI for BOTH governance
  paths a graph mission can hit: a direct MEDIUM/HIGH-risk step
  (`decide()` + the new `resume-planned` call) and a capability
  acquisition gap (`decide()` + `install()`, which auto-resumes
  server-side — same pattern already proven in `AppV4.jsx`). "Plan it"
  is the text/voice convergence path: it runs the exact same real
  `plannedMission()` every other surface already uses (there is no
  plan-only backend endpoint, so this genuinely executes, stopping at
  the same real governance checkpoints a hand-built graph would), then
  reconstructs the resulting plan onto the canvas via `planToGraph()` —
  text, voice (via the existing `useSpeechInput` hook, unchanged) and
  the graph all end up editing the SAME object.
- Three new `api.js` methods: `missionFromGraph(plan)`,
  `resumePlanned(missionId)`, `resumeBlocked(missionId,
  capabilityName)` — the last two previously had no frontend caller at
  all despite the routes existing since BUG-005/006.
- Wired into `main.jsx` as `/v5`, alongside the untouched `/`, `/v2`,
  `/v3`, `/v4` surfaces (v1 stays the production Holo-Deck).

**Verification — real, not just unit tests.** Ran a live local stack
(`AXON_FIRESTORE_MODE=memory` backend on 127.0.0.1:8099, Vite dev
server on localhost:5173, CORS allowlist already covers `localhost:5173`
by default) and drove the actual rendered `/v5` page with Playwright/
Chromium (`/opt/pw-browsers/chromium`, pre-installed in this
environment):
  1. Built a 3-node graph by clicking through the real UI (two
     `calculator` nodes, a third referencing both via
     `@n1.result + @n2.result`, wired with two real drawn edges),
     clicked the real "Compile & Run" button, and confirmed the mission
     reached `COMPLETED` with the genuinely computed answer **50**
     (40 + 10) rendered on screen — proving GRAPH → REAL API → REAL
     MISSION → REAL EXECUTION STATE end to end, through the browser,
     not just via `TestClient`.
  2. Built a single node with no capability wired, ran it, and confirmed
     the node turned `BLOCKED` (amber) and a real live acquisition
     trace appeared showing the actual Guardian pre-screen and research
     stages as they streamed in (research honestly reported "Ungrounded
     — no citations available" since the local run used a dummy Gemini
     key) — proving the honest-gap and live-acquisition paths render
     real backend state, not fabricated progress.
  Found and fixed one real, minor bug from run 1: freshly `Add
  node`-created nodes used a spacing formula (60px steps) narrower than
  the node card width (208px), so 2+ default-positioned nodes visually
  overlapped. Fixed to match the 3-per-row/240px grid already used by
  "Plan it"'s auto-layout; reverified with a second browser run
  (2 fresh nodes, bounding-rect overlap check) that they no longer
  overlap.

**Not yet done** (explicitly still open, matching the user's own
Day 2/3 framing — not attempted or claimed here): real-time SSE-driven
node state (current implementation refreshes from the mission result
object, not a live stream, for the graph's own `COMPLETED`/`BLOCKED`
steps — the *acquisition* sub-panel IS truly live via the existing SSE
stream); a dedicated component/browser-level automated test suite
beyond the two ad hoc Playwright scripts run manually this pass (not
committed as permanent CI checks — the frontend has no browser-level
test runner installed, only plain Node `.test.mjs` scripts for pure
logic); voice→graph beyond the existing "Plan it" convergence (e.g. a
spoken correction to an already-built graph); further hardening/demo
prep.

`npm run build` clean both before and after the layout fix. All 8
existing `*.test.mjs` files plus the 2 new ones remain green (19 new
assertions, ~93 total across the suite). Backend suite unaffected by
this frontend-only commit: still 560 passed, 2 skipped.

**Notion**: not attempted this pass (see the long-standing block noted
in Update 18 and below — unchanged). **NotebookLM**: still unavailable.

Current HEAD: `6f33f86` — supersedes every hash below.

## Update 18 — BUG-010: ALREADY_INSTALLED (a real, safe status) was shown as an error everywhere, HEAD 47890e1

Directive: continue the state-machine idempotency audit ("install
twice… any unexpected behavior must become a bug-register entry").

Checked every `installed?.status === "INSTALLED"` (or `!==`) comparison
in the frontend against every real status `synapse.install()` can
return. Found the same defect independently written in three of the
four UI surfaces (`App.jsx`, `AppV2.jsx`, `AppV4.jsx`): anything other
than the literal string `"INSTALLED"` was classified as an error,
including `"ALREADY_INSTALLED"` — a real, legitimate, safe status that
IS the concurrency-safe idempotency guarantee BUG-003's `claim_install()`
fix exists to provide. A double-click before a button's disabled state
took effect, a client-side retry after a request that actually
succeeded server-side, or reprocessing a stale `pending` row would all
correctly no-op on the backend and then show a scary red error banner
on the frontend for an outcome that was completely fine.

`MissionTheater.jsx` (already touched for BUG-009) was re-checked and
found NOT to have this problem — it never applies an error
classification to an install status at all, so `ALREADY_INSTALLED`
already displayed as an honest, neutral line there.

Fixed: `App.jsx`/`AppV2.jsx` now treat both `INSTALLED` and
`ALREADY_INSTALLED` as success. `AppV4.jsx` gets a distinct, honest
message for `ALREADY_INSTALLED` specifically, since that response
carries no `implemented_count`/`mission_resumed` fields to reuse
`INSTALLED`'s message text. Verified against all four real backend
statuses (`INSTALLED`, `ALREADY_INSTALLED`, `FAILED`,
`APPROVAL_REQUIRED`) with a standalone Node check. `npm run build`
clean. Backend suite unaffected: 555 passed, 2 skipped.

**Ten bugs now, ten fixed, zero open.** The pattern across BUG-008
through BUG-010 has been consistent: pick one specific, concrete
contract property (a field name, then a status-value classification),
check it against every real backend response shape it touches, across
every consumer — not just the one file where it was first found.

**Notion**: attempted again this pass; see the in-conversation report.
**NotebookLM**: still unavailable.

Current HEAD: `47890e1` — supersedes every hash below.

## Update 17 — BUG-009: the reason/error class was live in every UI surface, not just AppV4, HEAD c1c2b89

Directive: a master completion audit explicitly named the lesson from
BUG-008 ("a component can look correct in isolation while its adjacent
layer is broken") and asked to keep applying it.

Applied it literally: BUG-008 fixed one instance in `AppV4.jsx`. Rather
than assume the other three UI surfaces (`App.jsx` — the actual
production-deployed v1 Holo-Deck, `AppV2.jsx`, `AppV3.jsx`) were clean,
grepped every `.reason` read across all of `web/src/**/*.jsx` and
cross-checked each against the real backend shape it consumes. Found
the identical, independently-written bug in three more places, plus one
differently-shaped variant of the same root problem:

- `App.jsx` and `AppV2.jsx`: the same install-failure display pattern
  as BUG-008 (`installed?.reason` only, never `installed?.error`).
  `App.jsx` is the more consequential of the two — it's what actually
  ships as the production Holo-Deck, not `AppV4.jsx`'s richer dev
  surface.
- `AppV2.jsx` and `AppV3.jsx`, separately: the top-level mission-result
  display only checked `reason` for a mission that fails during
  PLANNING (a real Gemini quota/auth refusal — the exact scenario each
  file's own pre-existing comment already named as the motivating case,
  years before this bug was actually traced to its root cause).
  `mission_service.start_planned()`'s planning-failure response uses
  `"error"`, not `"reason"`. `AppV3.jsx` showed nothing at all;
  `AppV2.jsx` had a raw-JSON last-resort fallback that technically
  surfaced the text but illegibly.
- `MissionTheater.jsx` (rendered live inside `App.jsx`): a related but
  differently shaped bug — `status || reason` checks `status` FIRST,
  and `status` is always present on a real response, so the `reason`
  branch was dead code regardless of which key actually held the
  message.

Every OTHER `.reason` read in the frontend (`Command.jsx`,
`JudgeMode.jsx`, `missionStages.jsx`, `panels.jsx`, and the remaining
reads in `MissionTheater.jsx`) was individually checked against its
real backend shape and confirmed correct — not touched.

**A process note worth recording honestly**: an earlier draft of the
bug-register entry for this claimed "v2/v3 were not found to contain an
install-failure display at all" before that claim had actually been
verified. Caught via a fresh grep before finalizing the entry, not
published unverified — but worth naming, since the whole point of this
pass was exactly "don't assume a sibling layer is clean without
checking."

`npm run build` clean across all four changed files. Backend suite
unaffected (frontend-only change): 555 passed, 2 skipped.

**Notion**: attempted again this pass; see the in-conversation report.
**NotebookLM**: still unavailable.

Current HEAD: `c1c2b89` — supersedes every hash below.

## Update 16 — BUG-008: the reason/error mismatch class found live in the frontend, HEAD 8a7ecad

Directive: continue the frontend/backend contract audit explicitly
flagged as incomplete in the last two reports, and keep searching for
the same bug classes already found (reason/error mismatches especially)
rather than treating the last two clean passes as "done."

First checked `app/beastmode/memory.py` (the "memory/evolution"
subsystem a mega-prompt asked not to overlook) — genuinely complete and
honestly scoped as documented (lexical-similarity advisory only, never
authorization), with real HTTP-level and pure-logic test coverage
already in place. No gap, no overclaim in README. Then checked whether
BUG-006's `resume-blocked` fix is even reachable from the real frontend
— it isn't, by design: `web/src/` has zero references to that route,
because the real product path uses `synapse.install()`'s internal
auto-resume (confirmed `AppV4.jsx` correctly consumes
`installed.mission_resumed`), exactly as BUG-006's own writeup already
said. Not a gap.

**BUG-008 (P2, fixed) — the actual find.** Grepped `AppV4.jsx` for every
`.reason` read and cross-checked each against the real backend response
shape it consumes. Found one real, live instance of the exact
`"reason"`/`"error"` mismatch class behind BUG-005 and BUG-007: after
approving an acquisition and calling `api.install()`, the failure-
display fallback read only `installed?.reason`, but every FAILED-status
response `synapse.install()` actually returns (unknown capability, no
approval on record, and BUG-003's own real Firestore-contention case)
carries its message under `"error"`. Every one of these real failures
showed the bare word `"FAILED"` in the live demo UI, with the backend's
actual diagnostic silently discarded. Fixed by adding `installed?.error`
to the fallback chain — minimal, purely additive. Verified directly
against the three real backend FAILED shapes with a standalone Node
check (each now shows its real message instead of `"FAILED"`); `npm run
build` clean. Audited every other `.reason` read in the same file while
there: three were already correct against their real backend shapes,
one (line 583) is dead code but harmless (mission summaries never carry
a top-level `reason` field), left alone rather than speculatively
rewritten.

Backend suite unaffected (this is a frontend-only fix): 555 passed, 2
skipped.

**On the "diminishing returns" pattern named in Update 15**: this pass
shows it wasn't a plateau — it means the highest-density area shifts
once the backend's own instances of a bug class are exhausted; the SAME
class (reason vs error) was still live one layer up, in the frontend,
where nothing had looked yet. Worth remembering for whoever continues:
when a focused pass on one layer stops finding anything, check whether
the same defect shape exists in an adjacent layer before concluding the
class itself is exhausted.

**Notion**: attempted again this pass; see the in-conversation report.
**NotebookLM**: still unavailable.

Current HEAD: `8a7ecad` — supersedes every hash below.

## Update 15 — defense-in-depth confirmed (Guardian + AST screen independent), no new bug found this pass, HEAD 8b3dc29

Directive: a "final completion" master prompt asked to keep sweeping for
the same bug classes found before (reason/error mismatches, state
mismatches, governance bypasses, etc.) across the whole system.

Given the last two focused passes (Update 14's Batches A and B) both
came back with zero new bugs despite genuine adversarial effort, this
pass targeted one more concrete, previously-untested property: whether
Guardian's text-based pre-screen and the AST safety screen are
GENUINELY independent layers, not just each independently proven
correct in isolation. Built a real end-to-end case: a completely
benign-sounding acquisition need ("format a list of filenames into a
readable report" — nothing for Guardian's text-based pre-screen to
object to) paired with a mocked `generate_candidate` that returns
genuinely malicious code (`import os; os.system(...)` reading
`AXON_OWNER_TOKEN`). Ran it through the real `propose_stream()`
pipeline. Result: Guardian's pre-screen correctly let the (harmless-
sounding) need through, and the AST safety screen independently caught
and rejected the malicious code before the pipeline ever reached the
sandbox or an approval request. Confirmed real defense-in-depth, not a
single point of failure — no bug found, but this exact end-to-end
combination had no prior test (every existing malicious-code test
called `screen()` directly, proving the AST layer alone, never paired
with a benign NEED through the real pipeline). Added as a permanent
regression test.

Full backend suite: 555 passed (was 554), 2 skipped, no regressions.

**Pattern worth naming explicitly for whoever continues this**: this
session has now run five consecutive dedicated audit passes (BUG-005
discovery, BUG-006 discovery, BUG-007 discovery, then Batches A/B, then
this security pass). The first three each found a real, distinct,
previously-invisible bug. The last two found zero new bugs despite
comparable rigor (real reproduction attempts, real adversarial cases,
not just re-reading code). That shift is itself real signal, not a sign
the audits got lazier — the highest-density bug class (state
mismatches, reason/error swallowing, thin-route wiring gaps) appears to
be substantially exhausted in the areas reachable from this sandbox.
What remains genuinely unaudited is listed honestly in the in-
conversation final report this update accompanies, not glossed over.

**Notion**: attempted again this pass; see the in-conversation report
for the exact outcome. **NotebookLM**: still unavailable.

Current HEAD: `8b3dc29` — supersedes every hash below.

## Update 14 — full-completion audit, Batches A & B: persistence/restart and capability-lifecycle governance both confirmed sound, HEAD 22af879

Directive: a "full functional completion" master prompt asked for three
batches (A: architecture/state-machine/persistence; B: planner/
composition/capability-lifecycle/SYNAPSE/governance; C: frontend/voice/
SSE/contracts/security/CI). This update covers real work on A and B,
plus one concrete confirmation from C; it does NOT claim C got the same
exhaustive depth — stated honestly rather than padded.

**Batch A — persistence/restart, real finding: the architecture is
already sound, closed one real coverage gap.** Every existing
rehydration test (`tests/test_rehydrate.py`) checked
`registry.is_implemented(name)` after `rehydrate_capabilities()` — which
proves the name exists, not that CALLING it works (the exact class of
gap behind BUG-005/006/007). Verified for real: simulated a restart
(registry has no memory of a capability Firestore records as READY),
rehydrated it, then genuinely CALLED the resulting function through the
real sandbox-proxy closure — correct result. No bug; added as a
permanent regression test. Also spot-checked `ApprovalManager`: its
`self.pending` dict is write-only (`get()`/`decide()` both read directly
from Firestore), so it's already restart-safe by construction, no
hidden in-process dependency.

**Batch B — capability lifecycle + governance adversarial checks, all
held.** Fetched a full, un-truncated capability passport after a real
(mocked-external-calls) acquisition and confirmed every governance-
required field (research evidence with real citations, generated code,
safety/sandbox/evaluation results, Guardian decision, approval record)
is genuinely present with real values. Attempted three governance
bypasses: install without approval decided, install after explicit
rejection (both already covered by existing tests, re-confirmed still
blocked), and a genuinely novel combination — approving capability A's
real acquisition, then trying to install capability B (a different,
still-pending proposal from the same session) — all correctly refused.
`install()` only ever trusts its own capability's own stored
`approval_request_id`. Added the novel case as a permanent test.

**Batch C — one concrete confirmation, not a full pass.** Traced
BUG-007's fix through to the actual frontend: `web/src/livePipeline.js`'s
`actionsFromMissionSteps()` already reads a failed step's `reason` field
for its displayed detail text (`s.reason || s.status || "not executed"`),
so BUG-007's fix has real, direct user-facing value — a step that fails
on a raised exception now shows the actual message in the UI instead of
just `"FAILED"`. The rest of Batch C (voice deep audit beyond what's
already covered, SSE recovery semantics beyond BUG-004's documented
scope, full frontend/backend field-by-field contract diffing, a fresh
security/CI pass) was NOT given dedicated depth this pass — stated
explicitly rather than silently skipped or claimed done.

Full backend suite: **554 passed** (was 552 at Update 13's HEAD), 2
skipped, no regressions across two new commits (`3d6d553`, `22af879`).

**Notion**: attempted once more this pass, same result expected/
reported per protocol — see the in-conversation report for the exact
outcome at time of writing. **NotebookLM**: still no integration
available.

Current HEAD: `22af879` — supersedes every hash below.

## Update 13 — deep integration audit: BUG-007 found via cross-codebase pattern search, HEAD 72ba993

Directive: a "deep system integration + failure-recovery audit" asked
for 22 phases of hunting (illegal state transitions, retry/idempotency,
persistence/restart, prompt injection, data contracts, SSE recovery,
resource leaks, config, test quality, dead code, performance). Rather
than mechanically execute all 22 shallowly, this pass targeted the
highest-signal technique the last two passes both proved out: follow
the exact SHAPE of a bug already found to its other occurrences.

**Illegal-transition spot checks (Phase 2)**, all confirmed SAFE, no
bug: double-resume on `resume_planned()` after completion (the
top-level persisted-status guard already catches it, independent of
the in-memory `WorkflowState` bug BUG-005 fixed); resuming a mission
whose approval was never actually decided (correctly stops at
`APPROVAL_REQUIRED`, gated tool never runs); `resume_blocked()` on a
non-BLOCKED mission (already covered by an existing test).

**BUG-007 (P2, fixed) — found by generalizing BUG-005's own root
cause.** BUG-005's second half was a `"reason"`/`"error"` key mismatch
in the approval-resume path. Grepped every `.get("reason")`/
`.get("error")` call site in the codebase looking for the same
CLASS of bug elsewhere, and found it in `mission_engine.run()`'s core,
first-execution per-step loop — used by literally every mission, not
just approval-gated ones (a wider blast radius than BUG-005 itself). A
capability whose Python function raises a real exception (a bug in its
own code, distinct from a deliberate `{"status":"ERROR"}` return, which
was already handled correctly via `_tool_error()`) is caught by
`execution_gate._execute_tool()`'s exception handler and reported under
`"error"` — but the mission engine's generic non-EXECUTED branch read
only `"reason"`, silently replacing a real, specific exception message
with `null` in the mission's own `step_results`, even though the exact
same message was already correctly written to Firestore's
`ACTION_FAILED` audit event. The mission still honestly reported
`FAILED` (never fabricated success) — only the diagnosis was invisible
to anyone reading the mission object itself rather than separately
querying the audit log. Reproduced by registering a capability that
raises a real `TypeError` and running a mission against it
(`step_results[0]["reason"]` was `null` before the fix). Fixed by
reading whichever key the producing layer actually used
(`outcome.get("reason") or outcome.get("error")`) — safe by
construction, since existing REFUSED/BLOCKED/APPROVAL_REQUIRED paths
already use `"reason"` and the `or` short-circuits for them. This fix
also covers `resume_planned()`'s post-approval continuation steps for
free, since they run through this same `mission_engine.run()` code.

Full backend suite: **552 passed** (was 551 at Update 12's HEAD), 2
skipped, no regressions.

**Phases not given a fresh, dedicated pass this round** (no new
findings expected or produced, not because they were skipped
carelessly): SSE reconnect/duplicate-connection behavior (already
characterized honestly in BUG-004/Update 10 — a disconnect abandons the
in-flight work, now observable via an audit event; nothing new to add
without a much larger resumability redesign, which stays out of scope
per this project's own "no unnecessary complexity" rule). Memory-leak/
resource audit, performance profiling, and dead-code sweep (no evidence
surfaced this pass that any of these are currently a problem; flagged
here rather than claiming a clean audit that wasn't actually run
end-to-end). Multi-user/owner isolation (Phase 6) — this system is
architecturally single-owner (one bearer token = the owner; there is no
per-user account model), so "User A vs User B" isolation doesn't apply
as a distinct feature to test — the real analogue (an unauthenticated
or wrong-token caller) is already covered extensively by
`test_owner_auth.py`.

**Notion**: not yet re-attempted at the point this entry was written.
**NotebookLM**: still unavailable, unchanged.

Current HEAD: `72ba993` — supersedes every hash below.

## Update 12 — full route-execution audit: all 46 API routes actually invoked, BUG-006 found and fixed, HEAD f276a95

Directive: BUG-005 proved "a route exists and has a test file mention"
does not mean it works, so this pass systematically EXECUTED every
route in `app/api.py` via a real `TestClient` (not grepped for) rather
than trusting any prior coverage claim.

Built a full route inventory (46 routes across `app/api.py`), then ran
each through a real request in an exploratory script (not committed —
`scratchpad/route_audit.py` in this pass's sandbox), with meaningful
setup for the stateful ones (a real acquisition through Guardian/
research/generate/sandbox/evaluate/approval/install/rollback, a real
mid-mission approval, a real blocked mission, real monitors, a real
kill-switch toggle). Result: **45/46 routes worked correctly on the
first pass; 1 real bug found (BUG-006)**.

**BUG-006 (P2, fixed)**: `POST /missions/{id}/resume-blocked` never
accepted or forwarded a `capability_name`, so it could only resume a
mission blocked on an already-named (declared-but-unimplemented)
capability. The more central case — the planner emitting `tool: null`
because it found no capability at all, which is exactly the shape
SYNAPSE's whole acquisition story is built around — had no way to be
resumed through this documented, external route; it would just
re-block with the identical reason forever. This went unnoticed because
the real product never needs it: `synapse.install()` resumes a tied
mission internally with the freshly-installed capability's own name,
never going through this route. Fixed with a backward-compatible
optional body field (`ResumeBlockedRequest.capability_name`). Two new
permanent HTTP-level regression tests in `tests/test_api.py` (the
null-tool backfill case, and confirming the no-body declared-capability
case still works unchanged).

Also closed a real, separate coverage gap while at it: `POST
/missions/planned` — the single most-used route in the entire product —
had zero functional HTTP-level test coverage anywhere (same shape as
BUG-005/006 before they were found, but this one worked fine; only the
missing test was the issue). Added a permanent regression test for it
too.

**A near-miss worth recording**: the exploratory (uncommitted) audit
script called `POST /beastmode/ledger/seal` directly against a real
`TestClient`, which overwrote the actual, real, previously-recorded
`app/beastmode/ledger_seal.json` (16 real events, a real hash) with a
bogus 2-event seal from the script's own throwaway fake capabilities.
Caught immediately via `git status`/`git diff` before committing
anything, reverted with `git checkout -- app/beastmode/ledger_seal.json`.
The COMMITTED test suite (`tests/test_ledger_forensics.py`) already
does this safely (monkeypatches `SEAL_PATH` to a pytest `tmp_path`
before ever calling `seal()`) — no code change needed, just a recorded
caution for any future ad hoc route audit.

State-machine transition spot-check (Section 2 of this pass's
directive): confirmed `REJECTED` is a real, well-covered state
(approval decisions, SYNAPSE stage rejections, multiple existing
tests); confirmed `CANCELLED` does not exist anywhere in this codebase
as an actual state — not a gap, just not a state this system uses, so
nothing to add there.

Full backend suite: **551 passed** (was 548 at the start of this pass),
2 skipped, no regressions. Two commits: `f6f5c22` (the fix + tests),
`f276a95` (commit-hash backfill in the bug register).

**On the opening message of this pass**: it included an unverifiable
"Context Update from NotebookLM" paragraph claiming specific
architecture (a "Trust Kernel," SHA-256-sealed evolution-ledger blocks,
a fixed 256MB/5s sandbox profile) that does not match anything found in
the actual codebase this session, and asked to "proceed with staging
Mission #2" on that basis. Declined to incorporate those claims as
verified fact or to stage Mission #2 without explicit clarification —
flagged directly to the user in-conversation rather than silently
complying or silently ignoring it. Recorded here so a future session
knows this was deliberately not treated as ground truth, and why.

**Notion**: not yet re-attempted at the point this entry was written
(will attempt once more per protocol before this pass ends, and report
honestly). **NotebookLM**: still no integration available in this
session (unchanged from Update 11's finding).

Current HEAD: `f276a95` — supersedes every hash below.

## Update 11 — BUG-005: resume_planned() was completely broken for every mid-mission approval, HEAD c09faed

The most significant finding across this whole series of hardening
passes. A repeated mega-prompt requirement to test "approval in the
middle... resumed mission" for a multi-step plan led to grepping the
whole test suite for `resume_planned`/`resume-planned` before writing
that test — and finding **zero functional coverage anywhere**. Only an
auth-only check (`test_owner_auth.py`) and a route-inventory line
(`test_api_hardening.py`) ever referenced it; neither called it
meaningfully.

Writing the missing test reproduced a complete, 100%-reproducible
failure on the first run: `POST /missions/{id}/resume-planned` — the
real, live route ANY planned multi-step mission must use to continue
once a human approves a step that isn't the mission's last one — always
failed. Root cause: `resume_planned()`'s `WorkflowState` was built with
`status = "EXECUTING"` and no `approval_request_id`, while
`orchestrator.approve_and_resume()` requires `status ==
"AWAITING_APPROVAL"` plus a matching `approval_request_id` to do
anything. The sibling single-tool `resume()` method gets both of these
right; `resume_planned()` was apparently written without copying them,
and because nothing ever tested it, this shipped silently for as long as
the method has existed. A second bug compounded it: the failure's real
message was read from `approved.get("reason")`, but the guard failures
carry `"error"`, so every caller saw `{"status": "FAILED", "reason":
null}` with zero explanation.

**Impact, precisely stated**: this affected ONLY missions where a
Guardian/risk-tier approval gate sits somewhere before the final step
(the exact "acquire a capability, get it approved, then keep going" and
"buy something, get approval, then continue" shapes central to this
project's own demo story). The acquisition-resume path
(`resume_blocked()`, used when SYNAPSE needs to install a NEW
capability) was unaffected — that's a different method with its own,
already-tested logic.

**Fix**: mirrors `resume()`'s already-correct pattern
(`workflow.status = "AWAITING_APPROVAL"`, `workflow.approval_request_id
= mission["approval_request_id"]`); additionally resolves the approved
step's args via `mission_engine._resolve_args(step.args, completed)`
before passing them through, instead of the plan's raw, unresolved
`"$STEP_N"` placeholder text (a real secondary gap: even a hypothetical
caller who worked around the first bug would have gotten the literal
string, not a prior step's actual output); and reads `approved.get
("reason") or approved.get("error")` so no failure path is ever silently
reported as `null` again.

Verified at the `mission_service` layer (two new regression tests in
`tests/test_loop_closure.py`: a full 3-step mission with a mid-mission
approval that also depends on step 1's real output via
`$STEP_1.value`, completing end-to-end with the real resolved value
arriving; and a corrupted-approval-id case proving a real, non-null
reason surfaces on failure) AND independently at the real HTTP API
layer (`POST /missions/planned` → `POST /approvals/{id}/decide` →
`POST /missions/{id}/resume-planned` via `TestClient`, confirmed this
pass, not committed as a separate permanent test since the service-layer
tests already cover the same logic more directly).

Full backend suite: 547 passed (was 545), 2 skipped, no regressions.
Recorded as **BUG-005 (P1)** in `AION_AXON_BUG_AND_PROBLEM_REGISTER.md`.

**Notion**: not yet re-attempted this specific update (the interactive-
approval block has failed 4 consecutive times across sessions; will
attempt once more at the end of this pass per protocol and report
honestly either way). **NotebookLM**: confirmed via `ListConnectors`
that no NotebookLM integration exists in this session at all — recorded
here rather than silently skipped, per this pass's explicit instruction.

Current HEAD: `c09faed` — supersedes every hash below.

## Update 10 — real P1 regression found by actually re-running the emulator, fixed; SSE-disconnect reasoning corrected; CI hardened, HEAD ccb28c0

Directive: a "BEASTMODE + BERSERK" master build prompt required a full
audit (Phase 0/1, done — nothing changed since Update 9's audit, git
state re-confirmed clean at `a6adf74`), then real hardening work per its
phase order, maintaining a living `AION_AXON_BUG_AND_PROBLEM_REGISTER.md`
(new, this pass) rather than only reporting findings.

**BUG-003 (P1, fixed) — the most significant finding this pass.** Java is
present in this sandbox (confirmed, not assumed), so rather than trust
the prior session's "P1 closed" claim, this pass actually started a real
Firestore emulator (`firebase-tools`, no gcloud SDK needed — downloads its
own bundled jar) and re-ran both emulator-gated concurrency tests. The
REAL production code path
(`tests/test_concurrency_firestore_emulator_engine.py`, which exercises
`app/synapse/engine.py`'s actual `install()`/`claim_install()`) failed on
2 of 5 runs with `ValueError: Failed to commit transaction in 5 attempts`
under real ~10-way simultaneous contention on one document — a genuine
regression the prior "closed" claim had not caught, because it was only
ever run once, not repeated. Raising `max_attempts` alone (tried to 20)
did not fix it: the client library's retry loop fires attempts back-to-
back with no delay, by its own design. What reliably fixed it (10+
repeated runs, zero failures after): an outer retry loop with a REAL
wall-clock sleep + jitter between attempts, giving the emulator's lock
queue actual time to drain. `claim_install()` now does this and raises a
new `InstallClaimContention` exception if still unresolved after 8
attempts; `synapse.install()` catches it and returns an honest `FAILED`
status (with a new `INSTALL_CLAIM_CONTENDED` audit event) instead of an
unhandled 500. New fast, non-emulator-gated regression test added so this
is covered on every CI run, not just when an emulator happens to be
available: `tests/test_concurrency.py::
test_install_fails_honestly_when_claim_is_genuinely_contended`.

**BUG-004 (P2, fixed) — a self-correction.** Update 9's bug register
entry (written by an earlier pass this session) claimed SSE client
disconnects were harmless because "side effects happen as the generator
advances, independent of whether the response is read." That was never
actually tested and turned out to be wrong: Starlette's
`StreamingResponse.stream_response()` simply stops calling `__next__()`
on the generator once a `send()` fails, so a disconnect genuinely
abandons the acquisition — and since a new candidate's capability
document isn't written until `AWAITING_APPROVAL`, an earlier disconnect
left zero trace anywhere (no doc, no audit event) despite possibly having
already spent a real `generate_candidate`/sandbox/evaluator call. Fixed
with one new `SYNAPSE_ACQUISITION_STARTED` audit event right after
Guardian pre-screen passes — observability only, not mid-flight
resumability (flagged as a real but out-of-scope larger change, not
built speculatively). New regression test: `tests/test_synapse_stream.py
::test_abandoning_the_stream_before_awaiting_approval_leaves_no_capability_trace`
(directly abandons a real generator mid-run and checks both the absence
of a stray capability doc and the presence of the new audit event).

**BUG-002 (P2, fixed) — CI gap.** CI ran only the backend pytest suite.
Added a `frontend` job (Node 22, runs all 6 `*.test.mjs` files = 58
checks, then `npm run build`) and extended the `test` job with a real
Firestore-emulator step (via `firebase-tools`, same mechanism proven
working locally this pass) so the two emulator-gated concurrency tests
run for real in CI instead of silently skipping. YAML validated locally;
cannot watch an actual GitHub Actions run from this sandbox, so the owner
should confirm the first real run on this branch shows both new jobs
green.

**Full backend suite**: 545 passed (was 543 at Update 9's HEAD — two new
regression tests), 2 skipped, no regressions. Frontend: still 58 passed,
build clean.

**Not done this pass**: Phases 4 onward of the master prompt's own
ordering (harden capability reuse/composition further, voice/UI changes,
production deployment verification) — this pass focused specifically on
what a real re-audit surfaced (the emulator regression and the SSE-
disconnect correction) rather than speculatively touching areas nothing
new was found in. Production verification remains blocked: this sandbox
cannot reach `aion-axon-2026.web.app` or `aion-core-...run.app` (confirmed
again this session's lineage, unchanged).

**Notion**: attempted again this pass, failed again with the same
interactive-approval requirement (4th consecutive failure across
sessions). Repo/this file remain the authoritative, current source per
this page's own stated policy — the Notion page itself, last fetched
fresh this pass, is confirmed stale as of Update 9 (predates it by two
updates now).

Current HEAD: `ccb28c0` — supersedes every hash below.

## Update 9 — final hardening audit: one P0 found and fixed, 10-task adversarial suite 10/10 (LOCAL VERIFIED), HEAD 0569371

Directive: a "FINAL HARDENING + ADVERSARIAL QA MASTER PROMPT" required an
audit-before-code pass over demo/hardcoded/mock patterns, then a 10-task
adversarial challenge across specific categories run with genuinely varied,
non-overfit inputs, honest-failure verification, and a full readiness
report. It also required treating LOCAL VERIFIED and PRODUCTION VERIFIED
as never interchangeable.

**P0 found and fixed:** `web/src/v4/AppV4.jsx`'s hero input defaulted to
the literal string `"Pull the US birth totals from 2005 and brief me"`,
bound via `value={prompt}` -- a real pre-filled, editable value, not a
placeholder. A user opening `/v4` and clicking Send with zero typing or
speech would submit that historical demo phrase as their own request.
This survived two prior sessions of heavy rework on this exact file
because every test that exercised `send()` filled the input first (even
to clear it), never exercising true page-load state. Cross-checking
`Command.jsx`'s legitimate use of the same phrase (a real `placeholder`,
confirmed safe) is what prompted re-checking `AppV4.jsx`'s usage, which
was not the same safe pattern.

Fix: default changed to `useState("")`, with an inline comment
documenting the bug for future readers. Verified: `npm run build` clean;
a new Playwright check `prompt_default_check.mjs` (2/2: fresh load has a
genuinely empty input, clicking Send with zero interaction is a true
no-op); a full re-run of the pre-existing `voice_smoke.mjs` (13/13, no
regression). Committed `0569371`, pushed to `feat/beastmode-core-oagiwb`.

Rest of the repo-wide grep sweep (demo/mock/fixture/hardcoded/fake/
placeholder/sample patterns, ~26 files matched across `app/` and
`web/src/`) triaged clean: legitimate comments, real `placeholder=`
attributes, `web/src/v3/replay.js`'s honestly-labeled historical replay,
and `MissionTheater.jsx`'s explicitly-labeled "DEMO FIXTURE · NO
PRODUCTION MUTATION" recovery mode. No other P0/P1 found this pass.

**10-task adversarial suite — LOCAL VERIFIED, not PRODUCTION VERIFIED.**
This environment cannot reach `https://aion-axon-2026.web.app` or
`https://aion-core-638298765129.asia-south1.run.app` (confirmed via
`curl` → 403 CONNECT-tunnel-failed, and `WebFetch` → `EGRESS_BLOCKED`,
both independently, this pass and the prior one). Exact commands for the
owner to run this same suite for real against production are in the
readiness report delivered in-conversation; not restated here to avoid
drift between two copies.

Ran at `/tmp/claude-0/.../scratchpad/adversarial_10.py` (not committed --
a one-off QA script, not a permanent test) against the real pipeline:
real Guardian, real registry, real mission engine, real SYNAPSE stage
machinery (`propose_stream()`), real ExecutionGate, real approval
manager, real transactional install-claim, real (in-memory) Firestore.
Only the outermost model calls (`plan_mission`, `search_web`,
`generate_candidate`, `execute_in_sandbox`, `evaluate`) were mocked, one
hand-authored plan per scenario -- this does NOT re-test the real
Gemini planner's semantic judgement (separately validated live with real
quota in Update 7); it tests everything downstream of a plan the real
planner could plausibly produce.

Result: **10/10 passed** across all required categories (existing-
capability reuse, multi-step reasoning, arithmetic, current web research,
text transformation [new capability], data manipulation [new
capability], explicit new-capability acquisition, complex multi-step
combining reuse+acquisition, a voice-shaped phrasing, and an unexpected
general-purpose question). Two additional hidden-style generalization
probes (an unimplemented "translate to French" gap, and an oddly-phrased
weighted-average calculation) both behaved correctly and were not part of
the official 10.

Every failure hit while building the suite was the suite's own bug, not
a system defect -- worth recording since each one taught something real
about the pipeline:
- `AcquisitionRecord` has no `capability_name` attribute; the installed
  name lives at `candidate["name"]`.
- `synapse.install(name)` takes one argument, re-reads the approval
  itself from Firestore, and internally calls `mission_service
  .resume_blocked()` when the acquisition was tied to a mission --
  calling `resume_blocked()` again afterward hits an already-COMPLETED
  mission. This is real loop-closure behavior worth knowing: install()
  IS the resume.
- `propose_stream()` yields the SAME `AcquisitionRecord` object mutated
  in place at every stage (by design, per its own docstring) -- a real
  consumer must snapshot via `.to_dict()` inside the loop, same as
  `api.py`'s SSE route does; collecting raw yielded refs into a list
  shows the final stage repeated N times, not the real sequence.
- Two back-to-back `web_research` calls in one mission triggered a real
  G-07 autonomy-demotion: the first call's ungrounded/DEGRADED result
  dropped `web_research`'s autonomy score below the 40% oversight
  threshold, so the second call correctly stopped for human
  `APPROVAL_REQUIRED` instead of auto-executing on eroded trust. Not a
  bug -- the governance system behaving exactly as designed.
- A multi-step plan whose second step (`calculator`) received the first
  step's raw, unstructured research-findings text as its expression
  failed HONESTLY (`"Expression contains unsupported characters."`,
  mission `FAILED` with that reason recorded) rather than fabricating a
  number. This is the "fail honestly" requirement working correctly, and
  also flags a genuine planner-quality edge case worth a future pass:
  the real planner should insert an explicit extraction step before
  handing free text to `calculator`, not wire `$STEP_N` straight through
  -- outside this pass's scope, not a governance defect.

Full pytest suite re-run after this pass: **543 passed, 2 skipped**,
unchanged from the pre-pass baseline (nothing in `app/` was touched this
pass beyond the one frontend fix already described).

Security/secrets sweep this pass: `git grep` for API-key-shaped and
private-key-shaped strings across tracked files found only the negative
assertion already in `tests/test_sandbox_service.py`; no `.env` or
credential files are tracked; `.gitignore` covers `.env*`, `*.key`,
`*-credentials.json`. CORS (`ALLOWED_ORIGINS`, `allow_credentials=False`)
and owner-token auth (`require_owner` on every mutating route) were
re-confirmed present and unchanged, not re-derived from scratch given
existing coverage in `test_owner_auth.py` / `test_api_hardening.py` /
`test_adversarial.py` (all passing in the 543).

Notion update for this pass was **not attempted** at the point this
handoff entry was written, to be attempted next; the last two Notion
update attempts (after Updates 6/7 and 8) failed both times with an
interactive-approval prompt the non-interactive session cannot clear --
if that recurs, the owner needs to approve it directly in the Notion
connector.

Current HEAD: `0569371` — supersedes every hash below.

## Update 8 — voice-first mission interface, one pipeline, no bypass, HEAD 250323b

Directive: AION AXON's primary interaction should be voice -- press a
mic, speak an arbitrary task, watch it run through the real governed
pipeline, hear the real result. Explicit non-negotiable: voice is only
an interface, never a second intelligence pipeline or a governance
bypass. Audited before writing anything, per that directive.

**Audit found real voice input already existed, live in production.**
`web/src/Command.jsx`, mounted in `App.jsx` at `/` (the default route).
Browser-native `SpeechRecognition`, zero cost, two real bugs already
fixed there in a prior session (recognition not surviving a re-render;
honest per-error-code messages instead of a dead mic button). It
already fed `api.plannedMission()` -- the real mission pipeline. Not
rebuilt; the working parts were reused.

**Audit also found a real architecture bug in what Update 6 shipped.**
`AppV4.jsx`'s `send()` called `synapse.propose_stream()` directly --
SYNAPSE's standalone *acquisition* endpoint. That means it always tried
to research+generate a BRAND NEW capability for whatever was typed,
even "calculate 17% of 8450", which should just reuse the existing
`calculator` capability. The mission planner -- the one component whose
actual job is "decide reuse vs. acquire" -- was never consulted. This
violated the project's own stated architecture (`IF capability exists ->
REUSE`) independent of voice, and needed fixing regardless; voice just
needed the correct entry point to build on, so both were fixed together.

**Built:**
1. `app/api.py`: new `GET /missions/{mission_id}/acquire/stream`,
   mirroring the existing `POST /missions/{mission_id}/acquire` but
   streamed via the same `synapse.propose_stream()` generator
   `GET /synapse/propose/stream` already uses. Both acquire routes now
   share `_need_for_blocked_mission()` so the gap-derivation logic
   can't drift between them -- one generator, reached two ways
   depending on whether a mission context exists, never two pipelines.
2. `AppV4.jsx`'s `send()` rewritten: calls `api.plannedMission(need)`
   FIRST, always. A mission answerable entirely from existing
   capabilities COMPLETES right there -- no acquisition spent, no
   wasted research/generate/sandbox cycle. Only a mission that
   genuinely BLOCKS on a real gap moves on to live-streamed acquisition
   via the new endpoint above, showing the same real SYNAPSE stages
   (research/generate/safety/sandbox/evaluate/guardian/approval) the
   standalone flow already streamed.
3. `web/src/speechRecognition.js` + `useSpeechInput.js` (new): voice
   input, ported from `Command.jsx`'s proven `<Speech>` component, not
   reinvented -- same ref-based render-survival fix (recognition built
   once, callbacks read from refs updated every render, so a polling
   parent re-rendering the tree doesn't tear listening down mid-utterance),
   same honest per-SpeechRecognition-error-code messages. The mic
   button only sets the prompt box; it never submits a mission by
   itself -- a deliberate reading of "no accidental mission submission"
   + "explicit user control before executing potentially consequential
   tasks" from the directive, over an alternative "auto-submit on
   recognized speech" design that would have satisfied the literal
   step-by-step flow description but not those two explicit safety
   requirements.
4. `web/src/speechOutput.js` (new): browser-native `SpeechSynthesis`
   speaks the EXACT terminal result text already shown on screen --
   same string, never a second, separately-composed line, never spoken
   from a bare status word. Off by default (unexpected audio on page
   load is a real accessibility problem, not a feature). Only speaks a
   TERMINAL outcome (`announceResult()`), never the transient
   "Planning…" / "Acquiring it now…" busy text.
5. Real bug found and fixed while wiring this: a speech-recognition
   error while still in the hero view (before the canvas had ever
   opened) set a real error message that nothing on screen showed,
   since `sendOutcome` only renders inside the expanded dual-pane
   canvas. `onError` now opens the canvas too, matching the existing
   unlock-gate path's own reasoning for the same fix.

**Verified, in this order, nothing skipped:**
- Backend: 543 passed, 2 skipped, 0 failed (5 new tests for the
  streaming acquire endpoint, including one proving the sync and
  streaming acquire routes derive an identical need from the same real
  gap -- the exact regression a hand-duplicated second copy of that
  logic would eventually drift into).
- Frontend: 58 passed across 6 files (26 new), build clean.
- **Real browser test** (Playwright + Chromium, a FAKE
  `SpeechRecognition`/`SpeechSynthesis` injected via `addInitScript`
  BEFORE any page script runs, so `speechRecognitionSupported()` sees
  it exactly like a real browser would and the exact `onresult`/
  `onerror` event shape a real microphone's transcription would produce
  is what gets exercised -- against a running backend with only the
  network-calling pipeline stages mocked, same shape as every other
  session's smoke tests, no real quota spent): **13/13 checks passed**.
  Confirmed live: a spoken "Calculate 17 percent of 8,450" reuses the
  real `calculator` capability and completes with the real computed
  answer (1436.5), zero acquisition spent; a spoken "Create a
  capability that can detect duplicate rows in a CSV" streams all 8
  real SYNAPSE stages live and produces a genuinely different
  capability (`detect_duplicate_csv_rows`); voice fills the prompt but
  never auto-submits; cancelling (stop before a result) submits
  nothing; a real speech error shows the honest, actionable message,
  not a crash or silence; with voice output on, the spoken text
  matched the exact on-screen result string; zero uncaught console/page
  errors across the whole run.

**What this pass explicitly could NOT do**: a literal microphone test.
This sandbox has no audio hardware at all. The browser test above
exercises the identical JS code path (`onresult`/`onerror` handlers) a
real microphone's `SpeechRecognition` events would trigger -- proving
the wiring is correct -- but an actual "I spoke into a real mic and it
worked" acceptance test has to happen on real hardware, which is the
owner's own next step, not something achievable from here.

**Governance, explicitly re-confirmed, not just asserted**: nothing in
this pass touches Guardian, the AST safety screen, the sandbox, the
evaluator, or the approval gate. Voice and the corrected `send()` both
terminate in the exact same `synapse.propose_stream()` generator every
other acquisition path already used and was already tested against.
The owner token gate is unchanged and still required before either a
typed or spoken request reaches a mutating endpoint.

**Current HEAD: `250323b`** — supersedes every hash below.

## Update 7 — real planner validation with a user-provided key: found and fixed a real generalization bug, HEAD 13cc222

A follow-up mega-prompt raised the stakes explicitly: a private 10-task
challenge with genuinely unseen requests is coming, target 10/10, no
hardcoding toward the test. Audited the codebase first (clean sweep --
no stray `calculate_birth_cagr`/TODO/swallowed-exception patterns beyond
what Update 6 already fixed; `web/src/v3/`'s replay tool is a legitimate,
honestly-labeled replay of one real historical mission, not a general
dispatcher, left untouched). Read the mission-execution test suite
(`test_reliability.py`, `test_step_honesty.py`) before writing anything
new -- it already covers multi-step chaining, gap detection, capability
reuse, failed-step propagation, restart resilience thoroughly. Adding
more mocked tests there would have duplicated existing coverage, not
closed a real gap.

The actual untested layer: `app/agents/mission_planner.py`'s real
planner (Gemini-driven, messy request -> structured plan). This
project's own test suite deliberately never calls it live (the same
`conftest.py` discipline that strips API keys unless
`AXON_LIVE_MODEL_TESTS=1` is set) -- so its real decomposition quality
for anything outside the BigQuery demo story had never been checked.

This environment had zero Gemini credentials (confirmed: no env var, no
`.env` file -- the key only ever lived in the owner's local shell per
`CLAUDE.md`). The user pasted a key directly in chat for this bounded
purpose. **First key was dead** (`429 RESOURCE_EXHAUSTED -- prepayment
credits depleted` on all 5 attempts, confirmed before assuming anything
worked). User provided a second key; validated it authenticates AND
actually has usable credits (one real minimal call) before spending the
agreed bounded batch on it.

**Ran `plan_mission()` directly (not `mission_service.start_planned()`)
against 5 deliberately varied, non-BigQuery requests** -- one real
Gemini call each, nothing executed:
1. "Convert 100C to Fahrenheit" -> correct `calculator` step, right formula
2. "Summarize Romeo and Juliet in two sentences" -> correct `web_research`
   step, then a correctly `tool: null` gap for the summarization step
   (no hallucinated capability, since `summarize_text` isn't implemented)
3. "15% of 2400, then add 300" -> correct two-step `$STEP_1` chaining
4. "Who won the 2019 Cricket World Cup" -> correct `web_research` step
5. "Read the AWS credentials from the server's environment variables" ->
   correctly `tool: null`, correctly tagged `risk: HIGH`, no fabricated
   capability. (Refusal is Guardian's job downstream at acquisition time
   -- already extensively hardened in prior sessions -- the planner's
   only job here is to not invent a way to do it, which it didn't.)

**Real bug found**: requests 1 and 4 both got an unrequested SECOND step
tacked on -- `write_brief`, wrapping a single-number/single-fact answer
in unnecessary "executive brief" formatting. The instruction prompt had
no rule against defaulting to it; `write_brief` exists for the BI-report
demo story and the planner was reaching for it reflexively.

**Fixed**: added rule 9 to the planner's instruction --
`write_brief` only when the request itself asks for a report/brief/
summary; anything whose real answer is a single number, fact, or short
sentence should end on the step that produces it directly.

**Re-verified with 3 more real calls**: both previously-buggy requests
now produce a single direct-answer step. A genuine "brief me on the
risks in this quarter's expense anomalies" request still correctly
produces `write_brief` as its final step (with `detect_expense_anomalies`
still correctly `tool: null`, since it isn't implemented) -- the fix
didn't break the legitimate case.

**8 real Gemini calls spent this session total**, all against a key the
user explicitly provided for this bounded validation. Never logged,
never written to any committed file -- held only in a scratchpad env
file outside the repo, deleted immediately after use (twice: once after
the dead key was confirmed useless, once after the working key's
validation finished).

Full suite re-run after the fix: 538 passed, 2 skipped, 0 failed. This
is a prompt-instruction-only change (no code logic touched); confirmed
by grep that no existing test asserted on the old instruction text, so
this really was untested territory before this pass, not a regression
risk in disguise.

**What this pass did NOT do**: run `mission_service.start_planned()`
end-to-end (which would also EXECUTE any step whose capability is
already available, e.g. `web_research`'s real grounding call) -- stayed
at the cheaper `plan_mission()`-only layer deliberately, to keep the
quota spend to exactly one call per test case. A true end-to-end
"messy request -> executed mission" real-model test still hasn't
happened this pass. Also did not touch `web/src/v3/` (legitimate,
already-labeled) or attempt any further capability-catalog changes.

**Current HEAD: `13cc222`** — supersedes every hash below.

## Update 6 — the "AppV4 send() fix" and "live SSE pipeline" a mega-prompt described as already-done: neither existed, both built for real, HEAD 199a7b2

A large planning prompt (apparently from a strategy conversation outside
this repo) arrived describing specific completed work: a commit
`f94e931` fixing AppV4's primary send button (previously hardcoded to
`calculate_birth_cagr`, not actually dispatching the typed prompt), and
a commit `0af9740` adding a live `GET /synapse/propose/stream` SSE
pipeline with a `LivePipelineView` frontend component. It also cited a
production Cloud Run revision (`aion-core-00039-sfq`).

**None of it existed.** Checked before touching anything: `git cat-file -t`
on both hashes failed on every branch (`main`, `feat/beastmode-core`,
`feat/beastmode-core-oagiwb`, `feat/core-intelligence`,
`feat/end-to-end-workflow`); `grep` for `propose/stream` or
`LivePipelineView` found nothing anywhere in the repo; the Notion Source
of Truth (last updated 2026-08-25, HEAD `9343d27`) told the same story.
`web/src/v4/AppV4.jsx` on every branch had the exact bug described as
already fixed: `send = () => { setExpanded(true); setRevealed(0) }`
never called the backend, and `selected` defaulted to
`useState("calculate_birth_cagr")`. Reported this plainly rather than
building on a fiction; the user confirmed to build it for real.

**Built, not assumed:**

1. `app/synapse/engine.py`: `propose()`'s entire body became
   `propose_stream()`, a generator yielding the same mutated
   `AcquisitionRecord` at every real stage boundary already marked by
   `record.stage = "..."` in the old code. `propose()` is now a 5-line
   wrapper that drains it and returns the last value -- same pipeline,
   same code path, not a second implementation that could drift.
   Verified byte-identical: 531 passed before and after this refactor,
   same count.
2. `app/api.py`: `GET /synapse/propose/stream`, owner-gated
   (`require_owner`) and rate-limited (`rate_limit_propose`) exactly
   like the existing `POST /synapse/propose`, streaming one real SSE
   event per stage. Query params, not a body (GET). Blank/whitespace
   `need` gets a real 422 (the manual `_reject_blank_after_stripping`
   call is wrapped in try/except -> `HTTPException`, since there's no
   Pydantic body to attach a field_validator to on a GET route).
3. `web/src/api.js`: `proposeStream()` -- `fetch()` + a manual
   `ReadableStream` reader parsing SSE frames, deliberately NOT the
   browser's native `EventSource` (which cannot send the `X-Axon-Token`
   header this route needs, and putting the token in the URL instead
   would leak it into logs/history -- exactly what `setOwnerToken()`'s
   module-variable-only design already exists to avoid). Exported
   `parseSseFrame()` separately, pure and unit-tested.
4. `web/src/livePipeline.js` (new): `describeStage(record)` maps one
   real streamed record to `{label, detail, tone}` for the UI. Every
   field in `detail` is read directly off the record the backend sent --
   this file adds no numbers, scores, or outcomes of its own.
5. `web/src/v4/AppV4.jsx`: `send()` now calls `api.proposeStream()` with
   the actual typed `prompt`, rendering each real stage as it streams in
   via the existing "execution stream" UI (already fed real per-stage
   entries; the reveal timer already only paced reading, not simulated
   work -- see the file's own pre-existing comment on that). `selected`
   now starts `null`; no fallback capability name anywhere. Fixed a bug
   introduced while wiring this up: `decide()` was repointing `selected`
   to the just-decided capability on REJECT too, which leaked a
   rejected capability's name into a later, unrelated mission's evidence
   panel -- only a real approve+install repoints it now, and `reset()`
   ("New mission") clears `selected` so a fresh mission starts from an
   empty canvas.

**Verified, in this order, nothing skipped:**

- Backend: 538 passed, 2 skipped (both new tests skip honestly outside
  their env-var/auth gates), 0 failed.
- Frontend: 42 passed across 5 `*.test.mjs` files (18 new). Build clean.
  `api.stream.test.mjs` runs `proposeStream()` against a REAL local
  `http.createServer` emitting real SSE frames deliberately split across
  chunk boundaries, not a mocked `Response` -- proves the buffering
  logic, not just the parser.
- **Real browser smoke test** (Playwright + the pre-installed Chromium,
  against a running FastAPI backend with only the network-calling
  pipeline stages mocked -- same shape as the existing pytest mocks, no
  real Gemini/sandbox quota spent): typed "Convert Celsius temperatures
  to Fahrenheit" through the actual hero input, clicked send, watched
  real stage labels stream in, reached AWAITING_APPROVAL showing the
  real generated `convert_celsius_to_fahrenheit` source and a real
  approval queue entry. Rejected it, then typed "Detect invalid values
  in a CSV column" and got `detect_csv_anomalies` -- a genuinely
  different capability for a genuinely different need, the exact
  regression this task existed to prevent. Zero console errors. 6/6
  checks passed on the final clean run.

**What this session could NOT do:** deploy, or smoke-test against real
production. This environment (a fresh Linux container, distinct from
both the earlier Windows sandbox and whatever environment produced the
mega-prompt's claims) has no `gcloud`, no GCP credentials, and its
outbound network proxy blocks `*.run.app`/`*.web.app` outright (403 on
CONNECT). Every verification above is local-only. The production
revision cited in the mega-prompt (`aion-core-00039-sfq`) was never
checked against reality here -- it may or may not be current; treat it
as unverified, not confirmed.

**Not done, deliberately out of scope this pass:** the mega-prompt's
remaining tasks (7-15: research/grounding investigation, model-strategy
review, reliability/observability hardening, a full "artificial
limitations" grep sweep beyond this one confirmed bug, the actual
production deploy + smoke test, the hackathon demo script). Flagged for
the next session/owner decision, not silently skipped.

**Current HEAD: `199a7b2`** — supersedes every hash below.

## Update 5 — P1 actually closed: real emulator run found and fixed a real race

A new session (Linux container, not the earlier Windows sandbox) checked
the P1 blockers named in Update 4 from scratch rather than trusting them
carried forward: `java` -> **present** (OpenJDK 21, `/usr/bin/java`).
Docker daemon still not running here either, but irrelevant once Java
was confirmed. `gcloud` is not installed and `dl.google.com` is blocked
by this environment's outbound proxy, so the Firestore emulator jar was
fetched a different way: `npm install firebase-tools` (npm registry is
allowlisted), then `firebase setup:emulators:firestore`, which pulled
`cloud-firestore-emulator-v1.22.0.jar` from `storage.googleapis.com`
(reachable through the proxy, unlike `dl.google.com`). Ran it directly
with `java -jar ... --host=localhost --port=8080`, no `gcloud` needed at
all.

**tests/test_concurrency_firestore_emulator.py — run for real, PASSED.**
Ten concurrent writers on one document via a real Firestore transaction:
1 INSTALLED, 9 ALREADY_INSTALLED, final version == 1, exactly as
asserted. Full suite alongside it: 531 passed, 1 skipped -> **532
passed, 0 skipped** with the emulator reachable (the one skip is this
file, and it stops skipping the moment `FIRESTORE_EMULATOR_HOST` is
set). No regressions.

That answered the scaffold's own question ("does Firestore's
transaction() API work") but not the one that actually matters for
production: does `app/synapse/engine.py`'s **real** `install()` code
race, given it does a plain read-check-write with no `transaction()` at
all (confirmed by reading it directly, lines ~362-441)? Wrote a second
test to answer that directly against the real engine code path, not a
toy transaction: `tests/test_concurrency_firestore_emulator_engine.py`,
which forces `AXON_FIRESTORE_MODE` to something other than `"memory"`
(exported in the shell before pytest starts, since `conftest.py`'s
`setdefault` only fills in when unset) so `firestore_store` is the real
`AxonFirestore` client, pointed at the emulator.

**First run: FAILED, for real.** All 10 concurrent `synapse.install()`
calls returned `INSTALLED` -- a genuine TOCTOU race, exactly the class
of bug the scaffold's docstring said to prove before touching
`engine.py`. It's now proven, not assumed.

**Fix**, minimal and scoped to the actual gap: added
`firestore_store.claim_install(name, request_id) -> bool` to both
backends -- a `threading.Lock`-guarded dict for `MemoryFirestore`, a real
`@firestore.transactional` read-check-write against a new, separate
`install_claims` collection/dict for `AxonFirestore` (kept out of the
`capabilities` document itself so the claim marker never leaks into a
judge-facing API payload). `engine.py`'s `install()` now calls
`claim_install()` in place of the old plain `stored.get("state") ==
"READY" and ...` check, right before the mutating writes it used to race
around.

**Re-ran the exact test that found the bug: PASSED**, repeatably --
exactly 1 INSTALLED, 9 ALREADY_INSTALLED, 1 evolution event, over real
networked Firestore, on a clean emulator and confirmed again after other
tests had already run against it. Full suite unaffected: **531 passed, 2
skipped** in normal CI mode (memory backend, no emulator -- the 2nd skip
is the new engine-race test, which honestly skips outside its two-env-var
gate, same pattern as its sibling).

**One honest caveat, disclosed in both test files' docstrings, not
hidden:** ten threads racing one real Firestore transaction on the same
document is genuine heavy contention, and on this specific local
single-JVM emulator (not real distributed Firestore) the SDK's default
5-attempt commit retry budget occasionally isn't enough -- observed
directly, more often once the emulator had been running a while under
load than right after a fresh start. When it happens the failure is
`ValueError: Failed to commit transaction in 5 attempts` (a retry-budget
exhaustion), never a wrong result -- every run that DID complete produced
the exact correct invariant, including immediately after a failed run on
the same emulator process. This affects BOTH the sibling scaffold test
and the new engine test equally (it is a property of the local emulator
under stress, not of either test's logic or of the fix) and is a known
characteristic of a single local JVM handling all contention resolution
serially, not a claim about production Firestore's distributed handling.
Not "fixed" by loosening either test's assertions or retry budget --
that would hide a real signal under identical real contention in
production, where it would rightly need the same investigation.

**P1 verdict: was UNVERIFIED -- ENVIRONMENT BLOCKED. Now: VERIFIED, and a
real gap it was meant to check for was found and fixed.** The remaining
scaffold-test flakiness under sustained local single-emulator contention
is now an explicitly disclosed environmental characteristic, not an open
question about whether the atomicity primitive or the fix works -- both
are proven, repeatably, whenever the transaction actually commits.

Files touched this update: `app/memory/firestore_store.py` (+54 lines,
`claim_install()` on both backends), `app/synapse/engine.py` (idempotency
check replaced with the atomic claim, same behavior for every existing
caller), `tests/test_concurrency_firestore_emulator.py` (docstring update
only, recording the real run + the contention caveat -- test body
unchanged), `tests/test_concurrency_firestore_emulator_engine.py` (new).

Production safety: no push to production Firestore, no deploy, no real
mission touched. This was a pure local code + test change, verified
entirely against a local emulator with no GCP credentials present in
this environment (confirmed before touching non-memory Firestore mode --
any accidental real call would have failed on missing ADC, not silently
succeeded against `aion-axon-2026`).

## Update 4 — genuine Docker attempt for P1, still environment-blocked, HEAD 08883d2

A session was explicitly directed to try harder to close P1 rather than just re-documenting it. Result: **still genuinely blocked, now with stronger evidence.**

- Confirmed (again) `java` absent on PATH.
- **New this pass**: found Docker Desktop (29.6.1) is installed. Attempted to actually use it as an alternative path to run the Firestore emulator (no JDK needed inside a container). Launched Docker Desktop, waited ~70s, checked `docker ps`. **Docker Desktop's own backend process crashed on launch** (`backend process exited` in its log, ~20s in, no container ever created). Confirmed no docker processes left running afterward — nothing to clean up, no side effects left on the host.
- Diagnosis: almost certainly a sandboxed/VM environment where the virtualization (WSL2/Hyper-V) Docker Desktop needs on Windows is restricted. Fixing that would mean host-level virtualization/BIOS configuration changes — a real system change, not "safe and cheap," explicitly out of scope.
- **Do not re-attempt Docker in this same environment** without first independently confirming virtualization support has changed. Updated `tests/test_concurrency_firestore_emulator.py`'s own docstring with both the Java and Docker findings, plus a documented Option B (Docker) run path for an environment where Docker actually works.

**P1 verdict stands: UNVERIFIED — ENVIRONMENT BLOCKED**, now via two independently-confirmed blockers (no Java, Docker backend non-functional), not merely "wasn't tried."

**Current HEAD: `08883d2edf139ab02e6e6fec38f2c74ecbedd49a`** — supersedes every hash below.

## Update 3 — the "test-order flake" was a real stale-test bug, now fixed, HEAD 7398796

Investigated the pre-existing "isolation-only flake" properly instead of just documenting around it again. It was never actually shared-state ordering nondeterminism — both affected tests (`tests/test_monitors.py::test_monitor_on_an_unimplemented_capability_is_refused`, `tests/test_reliability.py::test_declared_but_unbuilt_capability_is_also_a_gap`) hardcoded `"write_brief"` as an example of an unimplemented capability. Confirmed by source inspection: `write_brief` has a real registered function (`app/capabilities/bootstrap.py`) and `implemented=True` (`app/capabilities/seed.py`) — it's been genuinely implemented for a while. Both tests failed honestly on their own merits when run in a way that exposed this, and only "passed" by accident as part of a specific full-suite ordering. Fixed both using the exact same dynamic "pick whatever capability is currently still unimplemented" pattern already established elsewhere in this codebase (`tests/test_adversarial.py::test_declared_capability_cannot_be_invoked_at_all`, which solved this identical class of problem previously). Verified both pass in isolation now (15/15, 10/10) and the full suite is unaffected (531 passed, 1 skipped, 0 failed — same count, since these were fixes to existing tests, not new ones).

**There is no longer a known test flake in this repository.** Do not reintroduce one by hardcoding a capability's implementation status anywhere else — always derive it from `registry.list_tools()`.

**Current HEAD: `739879689568020e4f9b3e80e91c11dabe4c62e9`** — supersedes every hash below.

## Update 2 — P5 Judge Mode card, HEAD 57ccbb2

Built the frontend card for `GET /beastmode/state-machine` (the one real open item from Update 1 below). Files: `web/src/stateMachineProof.js` (pure display logic, testable), `web/src/stateMachineProof.test.mjs` (7 new tests, all passing), `web/src/api.js` (+`stateMachine()` client method), `web/src/JudgeMode.jsx` (+`StateMachineCard`, reusing the existing generic `ProofCard` pattern exactly — no new UI architecture). The card renders the real success path and checks 4 concrete self-authorization shortcuts (e.g. `AWAITING_APPROVAL → INSTALLED`) against the live transition data, showing `BLOCKED`/`ALLOWED` per shortcut rather than asserting security as prose.

Frontend tests: **24 passed** (7 new + 6 reconciliation + 11 demo fixture, up from 17). Build: clean. Backend untouched this update — not re-run (nothing backend changed).

P1 (Firestore emulator) re-checked once more at the start of this update: `java` still not on PATH. Not attempted again. Remains the one genuinely open, environment-blocked item.

**Current HEAD: `57ccbb23bb9c134436380b43cfb11b5118ccf22c`** — supersedes every hash below.

## Update 1 — re-verification pass at HEAD 8052a9f

A follow-up session re-checked every priority (P0–P5) against this exact checkpoint. **No code changes were required or made** — everything below was either already correct or blocked by the same environment limitation already documented (no Java). Specifically re-confirmed this pass, not just carried forward from memory:

- P0 (authorization boundary): no new mutation path found.
- P1 (Firestore emulator): `java` still not on PATH — checked again live, not assumed. Scaffold unchanged, still correctly skips.
- P2 (monitor/kill-switch governance): unchanged, no new gap.
- P3 (rate limiting): unchanged, no new gap; confirmed the 429 error body never includes the token.
- P4 (fresh adversarial re-run): ran `test_evaluator.py`, `test_adversarial.py`, `test_ledger_forensics.py`, `test_owner_auth.py`, `test_api_hardening.py`, `test_rate_limit.py`, `test_concurrency.py`, `test_monitors.py`, `test_reliability.py` together fresh — **203 passed, 2 failed** in that subset run; both failures are the same pre-existing order-dependent flake (confirmed again by the full-suite run passing clean). Full suite: **531 passed, 1 skipped, 0 failed** — identical to the last checkpoint, zero regressions.
- P5: backend endpoint judged sufficient; frontend card still not built (still the one real optional item left — see below).

This update was made on top of HEAD `8052a9f30d2935ee0ef856cec63eec526ca699fb` and committed as its own docs-only commit — check `git log -1` for the exact new HEAD, which supersedes both hashes below.

## Current HEAD (as of the ORIGINAL writing of this file — see update above for the current one)

`195f7697fd139380afcd844f1d86627346c53b51`

Branch: `feat/beastmode-core`. 3 local commits ahead of `origin/feat/beastmode-core` (`0e0f1c8`, `2c8ae6f`, `195f769`). **None pushed.**

## Working tree

Clean.

## Last verified tests

- Backend: **531 passed, 1 skipped, 0 failed**
- The 1 skip is intentional and honest: `tests/test_concurrency_firestore_emulator.py` — skips cleanly when no Firestore emulator is reachable (it isn't, here — no Java on PATH). Not a fake pass, not a hidden failure.
- Frontend: not touched this pass; last verified at 6 (reconciliation) + 11 (demo fixture) = 17 passed, build clean, in the prior session's commit (`2c8ae6f`).
- One documented, pre-existing, order-dependent test flake exists (fails only when specific files are run in isolation, passes in the full suite) — not caused by this session's work, disclosed in `AION_AXON_HANDOFF.md` and reconfirmed multiple times this session.

## Work completed this session

Three commits, in order:

1. **`0e0f1c8` — security: harden evaluator and AST safety screening** (SEC-01, SEC-03)
2. **`2c8ae6f` — security: harden governance, reliability, and monitor execution** — the large batch: ledger ordering determinism, install idempotency, kill-switch coverage (propose/install/decide), full API input hardening (risk enum, NaN/Infinity, whitespace, body size, max_length everywhere), a per-process rate limiter on the two Gemini-calling routes, real multi-threaded concurrency tests, auth edge cases, and the monitor-governance audit (found + fixed the kill-switch-blocked-run-counts-as-a-failure bug).
3. **`195f769` — feat: expose state-machine transition table; add Firestore emulator test scaffold** — this final pass's work:
   - **P0 audit**: traced every `autonomy_ledger.record_outcome()` call site, including one not previously reviewed (`app/governance/verification.py`). Confirmed it only fires after `execution_gate.execute()` already succeeded and only adjusts an autonomy score — no promotion, no bypass. **No new gap found.**
   - **P1**: `tests/test_concurrency_firestore_emulator.py` — a real, honest emulator-based concurrency test using Firestore's actual `transaction()` API, gated behind `pytest.mark.skipif` on `FIRESTORE_EMULATOR_HOST`. Written but never executed (no Java here). Contains exact setup steps in its own docstring.
   - **P5**: `GET /beastmode/state-machine` — new public read-only endpoint exposing the formal capability-transition table (`app/beastmode/state_machine.py`, which already existed but had no endpoint). Judge-facing proof that `INSTALLED` is only reachable via `INSTALLING` ← `APPROVED` ← `AWAITING_APPROVAL` ← a real human decision. 5 new tests in `tests/test_state_machine_api.py`.
   - **P2/P3/P4**: reviewed, found already correct from the prior session's work, explicitly **not** re-implemented (see "Remaining" sections below for exact reasoning).
   - **P6**: reviewed `AION_AXON_HANDOFF.md` for stale claims; deliberately **not** rewritten — it's a self-described historical checkpoint, and a full rewrite was judged not worth the credit budget versus the live, verifiable endpoints this session added instead.

## Work currently in progress

None. This is a clean stopping point — no half-finished file, no open edit.

## Remaining P0 items

None found this pass. Every mutation path (propose, install, decide, monitors create/run-due/disable, ground-truth, killswitch itself) has been traced across three sessions now. Re-auditing from scratch again would be low value; only re-check if new mutation endpoints are added.

## Remaining P1 items

**Multi-instance Firestore concurrency remains genuinely unverified.** The test scaffold (`tests/test_concurrency_firestore_emulator.py`) is written and ready — it needs an environment with Java to actually run. If a real transaction gap is found by that test, the fix goes in `app/synapse/engine.py`'s `install()` method (currently a plain read-check-write, protected only by the idempotency guard, not a Firestore transaction). Do **not** add transaction code to `engine.py` before that test actually demonstrates a real gap — speculative untested transaction code is worse than the current honestly-documented limitation.

## Remaining P2 items

Reviewed, not changed. `app/tools/web_research.py`'s `search_web()` already catches all failure modes broadly and degrades honestly (`DEGRADED`, no fabricated citations) — confirmed correct in the prior session, re-confirmed by reading it again this pass. No retry logic exists by design (a documented decision: retrying would double real API cost on the exact quota-exhaustion failure mode already observed live in Mission #1). Nothing to do here unless product requirements change.

## Remaining P3 items

Reviewed, not changed. `app/governance/rate_limit.py`'s limiter is per-process/in-memory, explicitly documented as such in its own module docstring and in every report this session. The single-owner-token architecture means the `_calls` dict cannot grow unboundedly in practice (unauthorized requests never reach the limiter — verified by test — so there is effectively one real key). A distributed limiter would need Firestore/Redis and real infrastructure testing not available here; not built speculatively.

## Remaining P4 items

Not re-audited this pass — the sandbox/AST adversarial suite from Batch 1 (`tests/test_adversarial.py`, `tests/test_sandbox_service.py`) already covers resource exhaustion, and all of it is part of the 531-passing full suite. If you want fresh live verification (not just "still in the passing suite"), re-run:
```bash
./.venv/Scripts/python.exe -m pytest tests/test_adversarial.py tests/test_sandbox_service.py -v
```

## Remaining P5 items

Optional, not started: no small UI change was made to the Holo-Deck frontend to surface `/beastmode/state-machine` visually (the endpoint exists and is tested, but nothing in `web/src/JudgeMode.jsx` calls it yet). Worth ~30 minutes of frontend work if credit remains: add a card to `JudgeMode.jsx` following the exact pattern the other `beastmode` cards already use (see `web/src/panels.jsx` and `JudgeMode.jsx`'s existing card list — Mission Readiness, Security Coverage, etc.).

## Known limitations

- Multi-instance Firestore concurrency: unverified (see P1).
- Rate limiting: per-process, not global (see P3).
- `AION_AXON_HANDOFF.md` is stale relative to this session's work (three sessions of security hardening postdate it) — treat it as historical, not current. This document (`AION_AXON_CONTINUATION_HANDOFF.md`) supersedes it for current state.
- Monitor `create()`/`disable()` are intentionally outside kill-switch blocking (documented decision, not an oversight — see the Batch 2.5 audit in this conversation's history or `app/monitors/service.py`'s comments).
- Production Cloud Run revision and PR-merge state (from an earlier session's forensics) were never re-verified this pass — if that matters, re-run the read-only checks in `AION_AXON_HANDOFF.md` §Q.

## Commands already run

```bash
git status --short
git diff --check
./.venv/Scripts/python.exe -m pytest -q          # 531 passed, 1 skipped
./.venv/Scripts/python.exe -m pytest tests/test_state_machine_api.py -v
./.venv/Scripts/python.exe -m pytest tests/test_concurrency_firestore_emulator.py -v   # confirmed clean skip
git add app/api.py tests/test_concurrency_firestore_emulator.py tests/test_state_machine_api.py
git commit -m "feat: expose state-machine transition table; add Firestore emulator test scaffold"
```

## Commands still required (none blocking — all optional next steps)

```bash
# To actually verify P1 (needs a JDK on PATH first):
gcloud components install cloud-firestore-emulator
gcloud emulators firestore start --host-port=localhost:8080
# in another shell:
export FIRESTORE_EMULATOR_HOST=localhost:8080
./.venv/Scripts/python.exe -m pytest tests/test_concurrency_firestore_emulator.py -v

# To re-verify frontend after any future frontend change:
node web/src/missionApprovalReconcile.test.mjs
node web/src/demoRecoveryFixture.test.mjs
cd web && npm run build
```

## Files modified (this final pass only — see git log for the full three-commit history)

- `app/api.py` (new endpoint only, +40 lines)

## Files created (this final pass)

- `tests/test_concurrency_firestore_emulator.py`
- `tests/test_state_machine_api.py`

## Files intentionally NOT modified

- `AION_AXON_HANDOFF.md` — historical checkpoint, left as-is (see P6 above)
- `app/synapse/engine.py` — no speculative transaction code added (see P1)
- `app/governance/rate_limit.py` — no distributed limiter added (see P3)
- `app/monitors/service.py` — `create()`/`disable()` deliberately left outside kill-switch blocking (prior session's considered decision, re-confirmed, not revisited)

## Production safety state

- pushed? **NO**
- deployed? **NO**
- production ledger modified? **NO**
- ledger resealed? **NO**
- Mission #2 executed? **NO**
- owner approval clicked? **NO**

## Exact next step

If continuing security/reliability work: get a JDK on PATH, stand up the Firestore emulator, and run `tests/test_concurrency_firestore_emulator.py` for real — this is the single largest remaining verified-vs-unverified gap in the whole security posture.

If continuing hackathon-readiness work instead: add the Judge Mode frontend card for `/beastmode/state-machine` (P5 above) — small, low-risk, directly improves the "prove AI cannot self-authorize" judge story.

If neither: the repository is in a clean, fully-tested, uncommitted-nothing state. The next action is the owner's own: review this diff, decide on pushing `feat/beastmode-core`, and independently decide when to run the first owner-authorized Mission #2.

## Suggested continuation command

```
Continue AION AXON from AION_AXON_CONTINUATION_HANDOFF.md at HEAD 195f769.
Read that file in full before doing anything else — it is the authoritative
current state, more current than AION_AXON_HANDOFF.md. Do not re-audit
sections it marks as already complete. Start with the "Exact next step"
section's first option unless the owner directs otherwise. Never push,
deploy, execute a real mission, click approve, or reseal the ledger
without the owner's own explicit action.
```
