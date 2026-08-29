# AION AXON — Bug and Problem Register

Living inventory of every issue discovered during hardening passes, per the
"never silently discard a finding" rule. Newest entries at the top. Severity:
P0 = catastrophic/security-critical, P1 = major functional failure,
P2 = reliability/usability/engineering issue, P3 = minor/polish.

---

## BUG-014

**SEVERITY:** P1 (open, not yet fixed — freeze in effect; root cause now confirmed via code reading)
**AREA:** Mission execution — no argument/signature validation before invoking a capability. Confirmed in BOTH real mission-execution paths: `app/missions/engine.py` (`MissionEngine.run()`, used by `/missions/planned` and `/missions/from-graph` — i.e. the v5 graph builder) and `app/workflows/orchestrator.py` (`Orchestrator.execute_tool()`, the shared execution layer both paths funnel through).
**FILE(S):** `app/missions/engine.py` (`MissionEngine.run()`, lines ~59-66: `args = self._resolve_args(step.args, results)` then `orchestrator.execute_tool(..., *args, ...)`), `app/workflows/orchestrator.py` (`execute_tool()`, lines ~78-88: `execution_gate.execute(action, risk, tool.function, *args, **kwargs)`). NOT `app/synapse/generator.py` — the generated capability code itself is confirmed correct (see VERIFICATION).
**PROBLEM:** A real production mission (id truncated in the UI as `acdba94a`; full ID never captured — see below for why that stopped mattering) failed with:
```
Traceback (most recent call last):
  File "/tmp/tmpuhp21kkb/candidate.py", line 83, in <module>
    print(json.dumps(generate_nepal_crisis_image()))
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
TypeError: generate_nepal_crisis_image() missing 1 required positional argument: 'input_str'
```
Root cause, confirmed by reading the real execution code (not guessed): a mission step's `args` list — whatever was typed into it, wherever it came from — is passed straight through to the capability function as positional arguments, with **no check anywhere in the pipeline that the count or names match what the capability actually requires**. `MissionEngine.run()` resolves `$STEP_n` placeholders in `step.args` (`_resolve_args()`) but never validates the *count* of args against the tool's signature; `Orchestrator.execute_tool()` then calls `tool.function(*args, **kwargs)` directly. If a step's `args` is `[]` for a capability that requires one or more parameters, the raw Python `TypeError` from the function call propagates up as the mission's failure reason — exactly what was observed. This is not specific to `generate_nepal_crisis_image`: it will happen for **any** installed capability with required parameters, whenever a mission step supplies too few (or wrongly-named) args. The most likely real-world trigger is the v5 graph builder (`web/src/v5/AppV5.jsx`): its node editor is a free-text "Args (one per line)" box (line ~764) that shows the user nothing about what arguments the chosen capability actually needs — even though that schema already exists and is queryable (`GET /capabilities/{name}/passport`). A user (or an AI-assisted plan) can trivially create a node calling a capability and leave its args empty or wrong.
**HOW DISCOVERED:** Reported directly by the project owner, who ran a real mission against the live production deployment on 2026-08-29 and saw it fail. Root cause was then found this session by reading the real execution code end-to-end (`app/missions/engine.py` → `app/workflows/orchestrator.py` → `execution_gate.execute()` → `tool.function(*args)`), rather than by obtaining the specific failed mission's full ID — the full ID turned out to be unnecessary once the *general* code path was traced and shown to have no argument validation for any capability, not just this one.
**IMPACT:** Any capability with required parameters can fail with a raw, user-facing Python traceback instead of a clean governance-style rejection, whenever the mission step that calls it under-supplies arguments — this is a systemic gap in both mission-execution paths (`/missions/planned` and `/missions/from-graph`), not a one-off data problem with this one capability. It also means the v5 graph builder currently offers no protection against building a broken node: nothing stops you from wiring up a capability without its required inputs until the mission actually runs and fails.
**STATUS:** OPEN — root cause identified, NOT fixed. Per the active freeze instruction from the project owner ("no more changes on that thing which is already running smoothly until i give any permission to do changes"), no code has been changed. This entry is diagnosis-only.
**FIX:** Not attempted (blocked by freeze). Recommended once permission is given, in order of value: (a) in `Orchestrator.execute_tool()` or `MissionEngine.run()`, before calling `tool.function(*args, **kwargs)`, validate `len(args)` (and ideally names) against the capability's own declared signature/passport (already computed for `GET /capabilities/{name}/passport`, so the schema exists and just needs to be reused here) and return a clean `{"status": "BLOCKED", "reason": "..."}` instead of letting the raw `TypeError` propagate; (b) in the v5 graph builder's node editor (`AppV5.jsx`), show the selected capability's required argument names next to the Args textarea (fetched from the same passport endpoint) so a user can't build a node without knowing what it needs. (a) is the load-bearing fix — it protects every mission-creation path, including ones not yet built; (b) is the UX improvement that prevents most instances of (a) from ever firing.
**REGRESSION TEST:** Not written yet (blocked by freeze). Once unblocked: a test that builds a `MissionPlan` with a step whose `args` list is shorter than the target capability's required parameter count, runs it through `MissionEngine.run()`, and asserts the mission ends `BLOCKED` with a clear reason — never `FAILED` with a raw Python traceback as the reason.
**VERIFICATION:** Confirmed via read-only, no-token GET requests (`GET /capabilities`, `GET /capabilities/generate_nepal_crisis_image/passport`) that the capability's real installed signature is `generate_nepal_crisis_image(input_str: str) -> dict` and its own sandbox/passport tests (which always supply `input_str`) pass cleanly — ruling out the generated capability code as the cause. Root cause then confirmed by direct, read-only reading of `app/missions/engine.py` and `app/workflows/orchestrator.py`: no argument-count or signature check exists anywhere before `tool.function(*args)` is called, in either mission-execution path. No live mission ID, token, or mutating action was needed for this — it was traced entirely from the source code and the public passport endpoint.
**COMMIT:** None (diagnosis-only, no code changed).
**REMAINING WORK:** None to *find* the bug — root cause is confirmed structural, not specific to one mission or one capability. Remaining work is entirely the FIX above, which is blocked on the owner lifting the freeze. Optional, non-blocking: if the owner wants to confirm this exact historical mission's args were indeed empty (rather than just accepting the structural explanation), the full mission ID would still let `GET /missions/{full_id}` show the exact step that ran — but this is no longer necessary to act on the bug.

---

## BUG-013

**SEVERITY:** P1
**AREA:** Backend — real-network install-claim contention budget
(`app/memory/firestore_store.py`)
**FILE(S):** `app/memory/firestore_store.py`
**PROBLEM:** `AxonFirestore.claim_install()`'s retry budget (8 attempts,
0.05-0.2s backoff between them, added by BUG-003) reliably passed 8/8
against a real Firestore emulator in this project's own dev sandbox, but
genuinely failed the first time it ran against a real emulator on an
actual GitHub Actions runner — 9 of 10 real concurrent
`synapse.install()` callers exhausted the retry budget and got `FAILED`
instead of the correct `ALREADY_INSTALLED`
(`tests/test_concurrency_firestore_emulator_engine.py::
test_ten_concurrent_installs_against_real_networked_firestore_produce_exactly_one_install`).
This is not data corruption or a duplicate install (exactly one caller
still got `INSTALLED`, as required) — it is an honest `FAILED` result
for callers that should have safely resolved to a no-op — but it means
9 of 10 callers in a real high-contention scenario would see a
misleading "install failed" outcome for a capability that, in fact, a
sibling caller had already installed successfully.
**HOW DISCOVERED:** BUG-012's own CI fix, working exactly as intended,
finally let this test run to completion in CI for the first time — it
had never gotten this far before (always masked behind BUG-012's
missing-emulator-readiness-check or, before that, simply never wired
into CI at all per BUG-002). The failure was real, not environmental
noise: reproduced mechanistically in this sandbox by artificially
starving the SAME production code's retry budget (2 attempts / 20ms
instead of 8 / 0.05-0.2s) against this project's own real local Firestore
emulator, which reliably reproduced the identical 1-claimed/9-contended
pattern seen in CI — confirming the retry budget itself, not the
transactional-locking design, was the gap. A shared CI runner's real
I/O contention is measurably noisier than this project's own dev
sandbox, where the original 8-attempt budget was tuned and had always
passed.
**IMPACT:** Under real multi-instance Cloud Run contention (the exact
scenario this method exists to make safe — multiple instances racing to
install the same approved capability), most losers could see a false
"install failed" outcome instead of the safe, correct, idempotent
no-op, even though nothing was actually lost or corrupted. On a judge's
machine or a busier/noisier Cloud Run cold-start burst, this is a real,
visible reliability gap in exactly the concurrency-safety guarantee
BUG-003 was built to provide.
**STATUS:** FIXED
**FIX:** Widened the outer retry budget in `AxonFirestore.claim_install()`
from 8 attempts / 0.05-0.2s backoff to 20 attempts / 0.1-0.4s backoff —
verified 5/5 clean locally against a real emulator with an equivalent
synthetic starvation harness, then 6/6 clean with the actual production
method unmodified beyond this budget change. `MemoryFirestore.claim_install()`
(the in-process, GIL-serialized version used for local/CI in-memory
tests) is unaffected — this bug and fix are specific to the real
networked path.
**REGRESSION TEST:** No new test file needed — the EXISTING real-emulator
concurrency test (already present, already correct, never touched or
weakened) is the regression test; it now needs to pass reliably in CI
on every future run, which BUG-012's fix finally made observable. Locally
verified: the exact starved-budget reproduction harness reliably
reproduces the bug on demand (5/5), and the actual fixed production code
passes reliably against a real local emulator (6/6, both concurrency
test files).
**VERIFICATION:** LIVE CI VERIFIED — run #185
(https://github.com/anshulreddybuilds/aion-axon/actions/runs/33051465314),
commit `947352e`, completed **SUCCESS**, both jobs green, every step
green, `Run Firestore-emulator concurrency tests` passed in 6s. The
first genuinely green CI run this branch has ever had.
**COMMIT:** `947352e`
**REMAINING WORK:** None — closed and confirmed live.

---

## BUG-012

**SEVERITY:** P1
**AREA:** CI — Firestore emulator readiness check (`.github/workflows/ci.yml`)
**FILE(S):** `.github/workflows/ci.yml`
**PROBLEM:** The "Start Firestore emulator" step's readiness poll loop had
no check of its own outcome after the loop exited:
```bash
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8080 >/dev/null 2>&1; then break; fi
  sleep 1
done
cat /tmp/emulator.log || true
```
If the emulator never came up within the 30-second window (a cold JVM +
emulator-jar download on a fresh runner with no cache, easily longer
than 30s), the loop simply ran out and fell through to `cat` (which
always exits 0), so the step reported **success** for an emulator that
never actually started. The next step — the real Firestore-emulator
concurrency tests — then spent 6+ minutes retrying a connection that
was never going to succeed (the gRPC client's own internal retry/
timeout logic), before finally failing with an opaque
`grpc._channel._InactiveRpcError` / `ServiceUnavailable` stack trace
that points nowhere near the actual root cause.
**HOW DISCOVERED:** Inspected the latest GitHub Actions run on this
branch (run #182, commit `5c9c687`) via the GitHub Actions API per this
pass's directive to check CI status before anything else. The `test`
job's steps showed "Start Firestore emulator" as `success` but the very
next step, "Run Firestore-emulator concurrency tests," as `failure`
after running for 376.76s (6m16s) — a duration consistent with the
gRPC client's own 60s/300s internal retry deadlines being exhausted
against a server that was never listening, not with a genuine test
failure. Pulled the job's failed-step logs directly and confirmed:
`Failed to connect to remote host: Connection refused` on
`127.0.0.1:8080`, the exact port the emulator step was supposed to have
already verified was live.
**IMPACT:** Every CI run on every branch was burning ~6.5 minutes on a
guaranteed-to-fail step whenever the emulator didn't come up in time
(which, on an uncached runner, appears to be close to always), while
still reporting the emulator-start step itself as green — actively
misleading about where the real problem was. This is also the reason
this session had never observed a genuinely green CI run for any of
this branch's recent commits despite every local run being clean.
**STATUS:** FIXED (two rounds — see below)

**Round 1 fix:** the readiness loop now sets an explicit
`ready=""`/`ready=1` flag, checks it after the loop, prints the real
emulator log either way, and `exit 1`s with a clear `::error::` message
if the emulator never came up — failing loud, at the actual point of
failure, instead of several minutes later inside an unrelated test;
increased the ceiling from 30s to 120s. Added an `actions/cache@v4`
step for `~/.cache/firebase/emulators` (the Firebase CLI's own emulator
JAR download cache) so a slow first-time download only happens once.
Pushed as commit `55681dc`.

**Round 1 result — the fix worked exactly as designed, and immediately
surfaced a second, DEEPER pre-existing bug that Round 1 could not have
caused (it was there in the original script too, just always masked by
the missing readiness check):** run #183 (commit `55681dc`) failed fast
this time (2m15s instead of 6m16s) with a clean, specific error instead
of a downstream gRPC stack trace — proving the readiness check itself
now works — but the real emulator log it printed showed
`npm error could not determine executable to run`, not a timing
problem at all. Root cause: `(cd /tmp/emulator-cfg && npx firebase
emulators:start ...)` runs `npx` from `/tmp/emulator-cfg`, a completely
different directory than where `npm install --no-save firebase-tools`
had just installed it (the job's default working directory,
`$GITHUB_WORKSPACE`). `npx` resolves a locally-installed package by
walking up from the CURRENT directory, not from wherever the install
happened to run, and this runner has no global `firebase` to fall back
to — so `npx` could never find the binary, regardless of how long the
readiness loop waited. **Reproduced byte-for-byte in this sandbox**:
installing `firebase-tools` in one directory and running `npx firebase
--version` from an unrelated directory reproduces the identical
`npm error could not determine executable to run`; invoking
`<install-dir>/node_modules/.bin/firebase --version` directly from that
same unrelated directory works.

**Round 2 fix:** invoke the installed binary by its real, absolute path
(`$GITHUB_WORKSPACE/node_modules/.bin/firebase`) instead of going
through `npx`'s directory-sensitive resolution at all — the same
direct-path pattern already used successfully in this session's local
rehearsals. Pushed as commit (recorded below).
**REGRESSION TEST:** The regression test IS the CI workflow itself, run
on every future push — a real emulator that fails to start now fails
this step immediately and visibly rather than masking as a downstream
test failure or (Round 1's own residual gap) a confusing unresolved-
binary error with no obvious cause. Verified end-to-end in this sandbox
before pushing Round 2: installed `firebase-tools` in one directory,
started the emulator from a different directory using the exact fixed
script's logic (absolute binary path + firebase.json + firestore.rules
+ the readiness loop), and confirmed it was detected alive in 4s.
**VERIFICATION:** LIVE CI VERIFIED — run #185
(https://github.com/anshulreddybuilds/aion-axon/actions/runs/33051465314),
commit `947352e` (the next commit on this branch after Round 2),
completed **SUCCESS** with `Start Firestore emulator` green in 26s
(cache hit) and the concurrency step itself green — proving both this
fix and Round 1's readiness check genuinely hold end to end.
**COMMIT:** `fd4f802` (Round 2)
**REMAINING WORK:** None — closed and confirmed live. (This exact fix
immediately surfaced the next real thing, filed separately as
BUG-013 — see below.)

---

## BUG-011

**SEVERITY:** P2
**AREA:** Frontend — graphical mission builder run panel (`v5/AppV5.jsx`)
**FILE(S):** `web/src/v5/AppV5.jsx`, `web/src/graphExecutionState.js`
**PROBLEM:** The run panel's mission-status line showed only the bare
status word (`FAILED`, `REFUSED`, `APPROVAL_REQUIRED`) with zero
explanation, even when the real reason was sitting one field over in
`step_results[last].reason`/`.error` or the summary's own top-level
`reason`/`error` the entire time. The exact same contract-reading class
as BUG-005/007/008/009, just not yet checked in this brand-new surface.
Compounding it: `mission_service.resume_planned()` cannot distinguish a
human's real REJECTION from "not yet decided" in its own status word —
`orchestrator.approve_and_resume()` maps BOTH to `APPROVAL_REQUIRED` —
so a rejected direct-approval step was rendered bright red with the raw
word `APPROVAL_REQUIRED` and no indication a real decision had just been
made, exactly the kind of "valid backend state painted as a scary false
error" this pass's own directive named as the thing to hunt for.
**HOW DISCOVERED:** A full contract audit of every `/v5`-related backend
response shape (`POST /missions/from-graph`, `/resume-planned`,
`/resume-blocked`, `/synapse/install`, `/approvals/{id}/decide`),
checking each against what the new frontend actually read — not
assumed. Traced the complete real status vocabulary across
`app/missions/engine.py`, `app/missions/service.py` and
`app/workflows/orchestrator.py` (`COMPLETED`, `BLOCKED`,
`AWAITING_APPROVAL`, `FAILED`, `REFUSED`, and the resume-only
`APPROVAL_REQUIRED`) and found the run panel displayed the status word
alone for every one of them.
**IMPACT:** The single most demo-relevant surface for the newly
authorized graph builder would show an unexplained, alarming-looking
status word on any real failure or rejection — undermining exactly the
"the system explains itself" claim the whole project rests on, in the
newest and most visible part of it.
**STATUS:** FIXED
**FIX:** Added `toneForMissionStatus()` (COMPLETED→ok,
BLOCKED/AWAITING_APPROVAL/APPROVAL_REQUIRED→warn — cautionary, not a
failure — FAILED/REFUSED/REJECTED→danger, anything unrecognized→warn
rather than a fabricated red) and `runOutcomeText()` (reads
`step_results[last].reason ?? .error`, then the summary's own
`reason`/`error`, in that order) to `graphExecutionState.js`. The
run panel now shows this real sentence under the status word.
Separately, `decideDirect()` now captures the human's actual decision
from `api.decide()`'s own response — the one place a genuine REJECTED
signal exists — via a `rejected` flag passed into `runOutcomeText()`,
so a rejection reads "Not approved — this step was rejected" instead
of the ambiguous raw `APPROVAL_REQUIRED` word. Also applied the
BUG-008/010 install-outcome check to `decideAcquisition()`, which
previously did not check `api.install()`'s result at all.
**REGRESSION TEST:** 10 new unit tests in `graphExecutionState.test.mjs`
covering the full status matrix (`toneForMissionStatus` per status,
`runOutcomeText` reason vs. error fallback, REFUSED/BLOCKED reason
surfacing, rejected-vs-pending distinction, COMPLETED step count,
empty-input safety). Verified live via a real headless-browser run
(`graph_e2e_approval.mjs`): a real MEDIUM-risk graph node approved
end-to-end to COMPLETED with the real computed answer, and the same
node rejected end-to-end showing the honest rejection sentence with the
approval panel correctly cleared (not stuck re-asking, not fabricating
COMPLETED).
**VERIFICATION:** LOCAL VERIFIED — 16/16 `graphExecutionState.test.mjs`
tests pass, full backend suite unaffected (560 passed, 2 skipped), 9/9
real-browser approve/reject checks pass. Not yet PRODUCTION VERIFIED.
**COMMIT:** `fd54235`
**REMAINING WORK:** None.

---

## BUG-010

**SEVERITY:** P2
**AREA:** Frontend — install-outcome classification (v1 `App.jsx`, v2
`AppV2.jsx`, v4 `AppV4.jsx`)
**FILE(S):** `web/src/App.jsx`, `web/src/v2/AppV2.jsx`,
`web/src/v4/AppV4.jsx`
**PROBLEM:** After approving an acquisition and calling `api.install()`,
all three UI surfaces classified any status other than the literal
string `"INSTALLED"` as a failure — including `"ALREADY_INSTALLED"`, a
real, legitimate, SAFE status `synapse.install()` returns when the
capability is genuinely already installed (the exact idempotency
guarantee BUG-003's concurrency-safe `claim_install()` exists to
provide). A double-click before a button's disabled state took effect,
a client-side network retry after a request that actually succeeded
server-side, or re-processing a stale `pending` approval row would all
correctly and safely no-op on the backend, then show a scary red error
banner on the frontend for an outcome that was, in fact, completely
fine.
**HOW DISCOVERED:** Continuing the state-machine idempotency audit this
session's directives repeatedly called for ("install twice… any
unexpected behavior must become a bug-register entry"). Checked every
`installed?.status === "INSTALLED"` / `!== "INSTALLED"` comparison
across the frontend against every real status `synapse.install()` can
actually return (confirmed from `app/synapse/engine.py`:
`INSTALLED`, `ALREADY_INSTALLED`, `FAILED`, `APPROVAL_REQUIRED`).
`MissionTheater.jsx` (fixed for a related issue in BUG-009) was
re-checked and found NOT to have this problem — it never applies an
"error" classification to an install status, it just displays whatever
status is literally present, so `ALREADY_INSTALLED` shows as an honest,
neutral status line there already.
**IMPACT:** A real, plausible demo-day UX failure: the owner (or a
judge, if this were ever externally driven) double-clicking Approve, or
a slow network causing a client-side retry, would see an alarming error
for a mission that actually completed correctly.
**STATUS:** FIXED
**FIX:** Changed the classification from `status === "INSTALLED"` (or
`!== "INSTALLED"`) to `["INSTALLED", "ALREADY_INSTALLED"].includes
(status)` in `App.jsx` and `AppV2.jsx`. In `AppV4.jsx`, added a distinct
third branch — `ALREADY_INSTALLED` gets its own honest message
("already installed (version N) — nothing changed") rather than reusing
`INSTALLED`'s message (which references `implemented_count`/
`mission_resumed`, fields that don't exist on an `ALREADY_INSTALLED`
response) or falling into the error branch.
**REGRESSION TEST:** Verified directly against all four real backend
statuses (`INSTALLED`, `ALREADY_INSTALLED`, `FAILED`,
`APPROVAL_REQUIRED`) with a standalone Node check confirming the correct
OK/error classification for each. `npm run build` confirmed clean.
**VERIFICATION:** LOCAL VERIFIED (build clean, classification verified
against all four real backend statuses). Not yet PRODUCTION VERIFIED.
**COMMIT:** `9f2edf4`
**REMAINING WORK:** None.

---

## BUG-009

**SEVERITY:** P2
**AREA:** Frontend — every UI surface (v1 `App.jsx`, v2 `AppV2.jsx`, v3
`AppV3.jsx`, `MissionTheater.jsx`)
**FILE(S):** `web/src/App.jsx`, `web/src/v2/AppV2.jsx`,
`web/src/v3/AppV3.jsx`, `web/src/MissionTheater.jsx`
**PROBLEM:** BUG-008 fixed one instance (`AppV4.jsx`) of the
`"reason"`/`"error"` mismatch class in an install-failure display. A
full sweep of every `.reason` read across the whole frontend (initially
claimed complete for v2/v3 without actually checking — caught and
corrected before finalizing, see below) found the IDENTICAL,
independently-written bug in three more places, plus one differently-
shaped variant:
1. `App.jsx` (the actual production-deployed v1 "Holo-Deck" — more
   consequential than `AppV4.jsx`, which is the richer dev surface):
   `decide()`'s install-failure message read only `installed?.reason`.
2. `AppV2.jsx`: identical `decide()` pattern, same bug.
3. `AppV2.jsx` and `AppV3.jsx`, separately: the top-level mission-result
   display (`result?.reason` / `liveResult.reason`) — a mission that
   fails during PLANNING (e.g. a real Gemini quota refusal, the exact
   scenario each file's own existing comment names) returns
   `{"status": "FAILED", "error": ...}` from `mission_service
   .start_planned()`, not `"reason"`. `AppV2.jsx` had a raw-JSON last-
   resort fallback that technically surfaced the text illegibly; 
   `AppV3.jsx` had no fallback at all and showed nothing.
4. `MissionTheater.jsx` (used live by `App.jsx`): a differently-shaped
   version of the same root problem — `result.installResult?.status ||
   result.installResult?.reason` checks `status` FIRST, and `status` is
   always present on a real response, so the `reason` branch was dead
   code regardless of which key held the real message.
**HOW DISCOVERED:** Systematic grep of every `.reason` read across
`web/src/**/*.jsx`, cross-checked each against the real backend field
name it consumes (established this session for every backend response
shape involved: `synapse.install()`'s FAILED responses, `mission_service
.start_planned()`'s planning-failure response, `AcquisitionRecord`,
`ApprovalRequest`, `orchestrator.execute_tool()`'s gap dict, the memory/
plan advisory responses). Every OTHER `.reason` read found in
`Command.jsx`, `JudgeMode.jsx`, `missionStages.jsx`, `panels.jsx`, and
the remaining reads in `MissionTheater.jsx` were individually checked
and confirmed correct against their real backend shapes — not touched.
**IMPACT:** The install-failure instances (1, 2, 4) hid the real
diagnostic behind the bare word "FAILED" in every UI surface a user
could actually be looking at, including the production one. The
mission-level instances (3) hid the real reason for a planning-stage
failure specifically — a real Gemini quota/auth error, plausible in
production, would have shown nothing actionable in `AppV3.jsx` and an
illegible raw JSON blob in `AppV2.jsx`.
**STATUS:** FIXED
**FIX:** `App.jsx`/`AppV2.jsx` (install case): added `installed?.error`
to the fallback chain, matching BUG-008. `AppV2.jsx`/`AppV3.jsx`
(mission case): check `result?.error` alongside `result?.reason`
everywhere the mission-level failure is displayed, including the
"nothing else matched" fallback condition in `AppV2.jsx`.
`MissionTheater.jsx`: always show the real status, then append `reason`
or `error` (whichever is present) as a suffix, instead of an
either/or chain where `status` always wins.
**REGRESSION TEST:** Verified directly against the real backend FAILED
shapes with the same standalone Node check used for BUG-008 (install
case, before/after). `npm run build` confirmed clean across all changed
files.
**VERIFICATION:** LOCAL VERIFIED (build clean, every changed line's
logic verified against the real backend response shape it consumes).
Not yet PRODUCTION VERIFIED (environment egress blocked, as with every
frontend fix this session).
**COMMIT:** `caa9384`
**REMAINING WORK:** None. A note on process: an earlier draft of this
entry claimed "v2/v3 were not found to contain an install-failure
display at all" before that claim had actually been checked — caught
via a fresh grep before finalizing, not published un-verified. Recorded
here rather than silently corrected, per this project's own "never hide
a near-miss" discipline.

---

## BUG-008

**SEVERITY:** P2
**AREA:** Frontend / AppV4 / mission theater display
**FILE(S):** `web/src/v4/AppV4.jsx`
**PROBLEM:** After approving an acquisition and calling `api.install()`,
the UI's failure-display fallback read `installed?.reason ||
installed?.status || "unknown"` — but every FAILED-status response
`synapse.install()` actually returns (unknown capability, no approval on
record, and BUG-003's real Firestore-contention case) carries its
message under the key `"error"`, never `"reason"`. Every one of these
real failures displayed only the bare word `"FAILED"` in the live demo
UI, with the actual diagnostic the backend had already produced silently
discarded. The exact same `"reason"`/`"error"` mismatch class as
BUG-005/007 — this time live in the frontend, not the backend.
**HOW DISCOVERED:** Continuing the field-by-field frontend/backend
contract audit this session's reports had flagged as incomplete.
Grepped `AppV4.jsx` for every `.reason` read and cross-checked each
against the real backend response shape it consumes: line 424
(evaluator reason) and lines 523/527 (AcquisitionRecord reason) were
both genuinely correct; line 534 already defensively checks
`missionResult.error || missionResult.reason` (correct); line 375 (this
bug) checked only `reason`; line 583 turned out to be dead code (mission
summaries never carry a top-level `reason` field at all — harmless,
since it falls through to an honest generic message, left alone rather
than speculatively rewritten).
**IMPACT:** A real, user-facing UX defect in the actual hackathon demo
UI: an owner who tried to install a capability and hit any real failure
(most plausibly BUG-003's contention case under load, or a stale/replayed
approval) would see nothing more informative than "FAILED" — no
actionable next step, despite the backend having already produced one.
**STATUS:** FIXED
**FIX:** Added `installed?.error` to the fallback chain:
`installed?.reason || installed?.error || installed?.status ||
"unknown"`. Minimal, purely additive — cannot regress any case that
already worked, since `reason` is still checked first.
**REGRESSION TEST:** Verified directly against the three real backend
FAILED-status shapes (confirmed from `app/synapse/engine.py` this
session) with a standalone Node check: before the fix all three
produced `"FAILED"`; after, each produces its real message
("Unknown capability.", "No approval on record.", the contention
retry message). Not added as a browser-level Playwright test this pass
— the change is a one-line, mechanically-verified `||`-chain addition
in a callback with no dedicated component-test harness in this repo;
`npm run build` confirmed clean.
**VERIFICATION:** LOCAL VERIFIED (build clean, exact logic verified
against real backend shapes). Not yet PRODUCTION VERIFIED (environment
egress blocked, as with every frontend fix this session).
**COMMIT:** `29e8854`
**REMAINING WORK:** None functionally. A future session could add a
proper component-level test harness for `AppV4.jsx` if that becomes a
priority — none exists today for any of its logic, not just this fix.

---

## BUG-007

**SEVERITY:** P2
**AREA:** Mission engine / error observability
**FILE(S):** `app/missions/engine.py` (`MissionEngine.run`)
**PROBLEM:** A capability whose Python function raises a REAL exception
(a bug in its own code — e.g. an unhandled `TypeError`, as opposed to a
capability that deliberately returns `{"status": "ERROR", "error":
"..."}`) reaches `execution_gate._execute_tool()`'s exception handler,
which reports the real message under the key `"error"`. But
`mission_engine.run()`'s generic non-EXECUTED branch (the one that
handles REFUSED/BLOCKED/FAILED/UNKNOWN statuses coming straight from the
orchestrator, separate from the already-correct `_tool_error()` check
for a tool's own `{"status":"ERROR"}` return value) read only
`outcome.get("reason")` — so a real, specific exception message was
silently replaced with `"reason": null` in the mission's own
`step_results`, even though the exact same message was already sitting
under `outcome["error"]` and correctly written to the `ACTION_FAILED`
audit event in Firestore. The mission still honestly reported `FAILED`
(never fabricated success) — only the diagnosis was invisible to anyone
reading the mission object itself (`GET /missions/{id}`, the API's own
summary) rather than digging through the audit log.
**HOW DISCOVERED:** Following up on BUG-005's second half (a
`"reason"`/`"error"` key mismatch in the approval-resume path), grepped
every `.get("reason")` / `.get("error")` site across the whole codebase
to look for the same class of bug elsewhere. Found this generic branch
in the CORE mission engine, which is the first-execution path used by
literally every mission, not just approval-gated ones — a wider blast
radius than BUG-005's own fix. Reproduced by registering a capability
that raises a real `TypeError` and running a one-step mission against
it: `step_results[0]["reason"]` was `null` before the fix.
**IMPACT:** Any capability bug that raises rather than returns an error
dict — a real, plausible occurrence for a SYNAPSE-generated or hand-
written capability alike — left the mission's own record of what
happened with no diagnostic information, forcing anyone debugging it to
separately query the audit log instead of just reading the mission.
**STATUS:** FIXED
**FIX:** Changed `results.append({**record, "reason":
outcome.get("reason")})` to `outcome.get("reason") or
outcome.get("error")` — reads whichever key the producing layer
actually used. Safe by construction: when `"reason"` is already present
(REFUSED, BLOCKED, and the existing APPROVAL_REQUIRED cases all already
use it), the `or` short-circuits and nothing changes.
**REGRESSION TEST:** `tests/test_step_honesty.py::
test_a_step_whose_tool_raises_reports_the_real_exception_not_null`
(registers a capability that raises a real `TypeError`, confirms the
mission reports `FAILED` with the actual exception message present, not
`null`).
**VERIFICATION:** LOCAL VERIFIED — reproduced before the fix, confirmed
fixed after, via direct `mission_engine.run()` invocation. Full backend
suite: 552 passed (was 551), 2 skipped, no regressions.
**COMMIT:** `7b11626`
**REMAINING WORK:** None. Worth noting this fix also covers the
`resume_planned()` continuation path for free — steps AFTER an approved
one run through this exact same `mission_engine.run()` code, so no
separate fix was needed there.

---

## BUG-006

**SEVERITY:** P2
**AREA:** Mission engine / API surface
**FILE(S):** `app/api.py` (`resume_blocked_mission`)
**PROBLEM:** `POST /missions/{id}/resume-blocked` never accepted or
forwarded a `capability_name` at all (`resume_blocked_mission(mission_id:
str) -> ...: return mission_service.resume_blocked(mission_id)`), while
`mission_service.resume_blocked(mission_id, capability_name=None)`
requires that second argument to backfill a step's `tool` field when the
planner left it `null` (a genuine capability gap, as opposed to a
declared-but-unimplemented one that already carries a name). This route
could therefore only ever correctly resume the LESS common case
(already-named capability) — the more central "the planner found no
capability at all, SYNAPSE built one, now finish the mission" case had
no way to be resumed through this documented, live, external route; it
would just re-block with the identical reason forever.
**HOW DISCOVERED:** Found while executing every single route in
`app/api.py` for real via `TestClient` (46 routes, all invoked, not
grepped for) after BUG-005 proved that "a route exists and has a test
file mention" does not mean it works. This route's only prior test
coverage was an auth-only check and a route-inventory line — identical
in shape to BUG-005 before it was found.
**IMPACT:** Real, but narrower than BUG-005: the actual product never
hits this gap, because `synapse.install()` resumes a tied mission
internally with the freshly-installed capability's own name (an
internal call, not this route). This route is only reachable by an
external caller (a direct API integration, a future frontend feature,
or a judge/tester probing the API surface) who does NOT go through the
install-and-auto-resume path — for that caller, the documented
capability of "resume a blocked mission with a capability name" simply
did not work.
**STATUS:** FIXED
**FIX:** Added an optional `ResumeBlockedRequest` body
(`capability_name: Optional[str] = None`) to the route, forwarded to
`mission_service.resume_blocked()`. Fully backward compatible — a
no-body call still resumes the already-named-capability case exactly as
before.
**REGRESSION TEST:** `tests/test_api.py::
test_resume_blocked_route_can_backfill_a_null_tool_step` (a real
`tool: null` gap, resumed via the HTTP route with `capability_name` in
the body, completes end-to-end) and `tests/test_api.py::
test_resume_blocked_route_still_works_with_no_body` (the pre-existing
declared-capability case, unaffected).
**VERIFICATION:** LOCAL VERIFIED — reproduced (route silently could not
supply a name), fixed, confirmed via `TestClient` at the real HTTP
layer. Full backend suite: 551 passed (was 548 -- 3 new tests, 2 for
BUG-006 and 1 closing a real-but-not-broken coverage gap for
`POST /missions/planned`), 2 skipped, no regressions.
**COMMIT:** `f6f5c22`
**REMAINING WORK:** None.

**Also found during this same route-execution pass, and worth recording
even though nothing was broken**: the exploratory audit script (not
committed) called `POST /beastmode/ledger/seal` directly against a real
`TestClient`, which overwrote the actual, real, previously-recorded
`app/beastmode/ledger_seal.json` (16 real events, a real hash) with a
bogus 2-event seal from the throwaway script's own fake capabilities.
Reverted immediately via `git checkout`. The COMMITTED test suite
(`tests/test_ledger_forensics.py`) already does this correctly —
`monkeypatch.setattr(ledger_chain_module, "SEAL_PATH", tmp_path /
"seal.json")` before ever calling `seal()` — so no code change was
needed; this is a caution for any FUTURE ad hoc route audit, not a
system defect: never call `/beastmode/ledger/seal` for real without
first patching `SEAL_PATH` to a throwaway location, since it writes a
real file on disk, not just Firestore.

---

## BUG-005

**SEVERITY:** P1
**AREA:** Mission engine / approval-resume / multi-step composition
**FILE(S):** `app/missions/service.py` (`resume_planned`)
**PROBLEM:** `POST /missions/{id}/resume-planned` — the real, live route a
PLANNED multi-step mission MUST use to continue after a mid-mission
(non-final-step) human approval — failed 100% of the time, for every
mission, unconditionally. `resume_planned()` built its `WorkflowState`
with `status = "EXECUTING"` and never set `approval_request_id` on it,
while `orchestrator.approve_and_resume()` requires
`workflow.status == "AWAITING_APPROVAL"` AND a matching
`approval_request_id` before it does anything. A second, compounding bug
made the failure invisible: `resume_planned()`'s own summary read
`approved.get("reason")`, but `approve_and_resume()`'s guard-failure
paths carry the message under `"error"`, not `"reason"` — so every
caller saw only `{"status": "FAILED", "reason": null}` with no
explanation at all.
**HOW DISCOVERED:** This exact mega-prompt series explicitly asked for a
test of "approval in the middle... resumed mission" for a multi-step
plan. Before writing it, a grep across the whole test suite for
`resume_planned` and for the route string `resume-planned` found it
referenced only in an auth-only check (`test_owner_auth.py`, confirms it
requires a token, never calls it meaningfully) and a route inventory
line (`test_api_hardening.py`, never calls it either) — **zero
functional test coverage anywhere**. Writing the missing test
immediately reproduced the failure on the first run, confirmed at the
`mission_service` layer and again independently at the real HTTP API
layer via `TestClient`.
**IMPACT:** Any real mission with an approval gate anywhere before its
last step — exactly the "Buy something after checking the price" or
"install this capability then use it" shape this whole project's demo
story is built around — could never actually finish once the caller
clicked approve, unless the approval happened to be the mission's final
step. The sibling `resume_blocked()` path (capability-acquisition gaps)
was unaffected; only mid-mission Guardian/risk-tier approval gates on an
already-planned, already-executing mission hit this.
**ROOT CAUSE:** `resume_planned()` was written without copying the two
lines its sibling `resume()` (the single-tool mission path) already gets
right (`workflow.status = "AWAITING_APPROVAL"` and
`workflow.approval_request_id = mission["approval_request_id"]`) — the
two implementations diverged and only one was ever exercised by a test.
A secondary, related gap: the approved step's args were passed to
`approve_and_resume()` unresolved (`*step.args`, the plan's raw
`"$STEP_N"` text) instead of resolved against already-completed steps
the way `mission_engine.run()`'s own per-step loop does — meaning even a
hypothetical caller that patched around the first bug would have gotten
the literal placeholder string instead of a prior step's real output.
**STATUS:** FIXED
**FIX:** `resume_planned()` now sets `workflow.status =
"AWAITING_APPROVAL"` and `workflow.approval_request_id =
mission["approval_request_id"]` before calling `approve_and_resume()`
(matching `resume()`'s pattern); resolves the approved step's args via
`mission_engine._resolve_args(step.args, completed)` before passing them
through; and reads `approved.get("reason") or approved.get("error")` so
no failure path is ever silently reported as `null` again.
**REGRESSION TEST:** `tests/test_loop_closure.py::
test_resume_planned_completes_a_mission_with_a_mid_mission_approval` (a
real 3-step mission: step 1 executes, step 2 needs MEDIUM-risk approval
AND depends on step 1's output via `$STEP_1.value`, step 3 runs after —
proves the whole chain completes and step 2 gets the real resolved
value, not the placeholder or nothing) and `tests/test_loop_closure.py::
test_resume_planned_reports_the_real_reason_not_a_null` (proves a real
failure surfaces a real, non-null reason). Also verified independently
at the real HTTP API layer (`POST /missions/planned` →
`POST /approvals/{id}/decide` → `POST /missions/{id}/resume-planned`,
via `TestClient`, not committed as a permanent test but run and
confirmed this pass).
**VERIFICATION:** LOCAL VERIFIED — reproduced before the fix (100%
failure), confirmed fixed after (100% success across multiple runs) at
both the service layer and the real API layer. Full backend suite: 547
passed (was 545 — two new tests), 2 skipped, no regressions.
**COMMIT:** `c09faed`
**REMAINING WORK:** None. Worth flagging to the owner: any mission
plans/demo scripts authored around the assumption that a mid-mission
approval could never actually resume should be re-checked, since this
capability genuinely did not work before this fix, in any prior commit.

---

## BUG-003

**SEVERITY:** P1
**AREA:** Governance / capability installation / distributed concurrency
**FILE(S):** `app/memory/firestore_store.py` (`AxonFirestore.claim_install`),
`app/synapse/engine.py` (`install`)
**PROBLEM:** Re-verifying P1 (distributed Firestore concurrency) this pass
by actually running the Firestore emulator in this sandbox (Java present
here, confirmed) surfaced a genuine gap the prior session's closure of P1
had not caught: under real, tightly-synchronized 10-way contention on the
same install-claim document, `claim_install()`'s Firestore transaction
could exhaust its retry budget while every attempt hit `Aborted:
Transaction lock timeout`, and raised an unhandled exception out through
`synapse.install()` instead of resolving to a clean win/loss. Reproduced
on 2 of 5 runs of `tests/test_concurrency_firestore_emulator_engine.py`
(the test exercising the real production code path, not just the
hand-written reference test) before the fix.
**ROOT CAUSE:** The client library's own transaction retry (governed by
`max_attempts`) fires repeated attempts with NO delay between them, by
the library's own documented design ("exponential backoff is not
required"). Under genuinely simultaneous 10-way contention on one small,
frequently-locked document, that back-to-back retry pattern can never
give the emulator's lock queue time to drain, so every attempt lands in
the same contended window and eventually the budget (even raised to 20,
tested) runs out.
**USER IMPACT:** In a real burst of near-simultaneous install attempts on
the same capability (e.g. multiple Cloud Run instances handling
concurrent requests for the same acquisition), the caller could see an
unhandled 500 instead of an honest, actionable response.
**SECURITY IMPACT:** None directly (no capability could be double-
installed or installed without approval either before or after this fix
— that invariant held in every run), but an unhandled exception on a
governance-critical path is itself a reliability/observability gap.
**STATUS:** FIXED
**FIX:** Added an outer retry loop in `claim_install()` using a real
wall-clock sleep with jitter (50-200ms) between up to 8 attempts, each a
fresh single-attempt transaction — confirmed empirically this (not a
higher `max_attempts` alone, tried up to 20) is what reliably resolves
the contention. If still unresolved after 8 attempts, raises a new
`InstallClaimContention` exception rather than an opaque library error.
`synapse.install()` now catches that exception and returns an honest
`{"status": "FAILED", "error": "...retry..."}` (writing an
`INSTALL_CLAIM_CONTENDED` audit event) instead of letting it crash the
request — never fabricating `ALREADY_INSTALLED` for a state nobody
actually reached.
**REGRESSION TEST:** `tests/test_concurrency.py::
test_install_fails_honestly_when_claim_is_genuinely_contended` (fast,
MemoryFirestore-backed, monkeypatches `claim_install` to raise and checks
`install()`'s honest response — runs in every CI invocation, not
emulator-gated). Real-contention reproduction + fix verified 5/5 runs
against the actual emulator in this session (both
`test_concurrency_firestore_emulator.py`, whose reference-test worker was
updated to mirror the same real fix, and `test_concurrency_firestore_
emulator_engine.py`, which exercises the actual production code).
**VERIFICATION:** LOCAL VERIFIED, real Firestore emulator, this sandbox
(Java present here — confirmed, not assumed). Not yet PRODUCTION
VERIFIED (egress blocked from this environment; this is exactly the kind
of fix that should be spot-checked against real Firestore once
deployable).
**COMMIT:** `b9e768b`
**REMAINING WORK:** None functionally. Worth a note in the next
production deploy that this path now emits an `INSTALL_CLAIM_CONTENDED`
audit event type judges/owner may see for the first time under load.

---

## BUG-002

**SEVERITY:** P2
**AREA:** CI/CD
**FILE(S):** `.github/workflows/ci.yml`
**PROBLEM:** CI only runs the backend pytest suite. It does not run the
frontend's Node-native test scripts (`web/src/**/*.test.mjs`, 58 checks) or
the Firestore-emulator concurrency test (`tests/test_concurrency_firestore_emulator.py`,
currently correctly skipped locally without `FIRESTORE_EMULATOR_HOST`).
**ROOT CAUSE:** CI was set up before either of those existed and was never
revisited.
**USER IMPACT:** A frontend regression or a real distributed-concurrency
race could land on `main` without CI catching it.
**SECURITY IMPACT:** None directly, but the concurrency test specifically
exists to prove `install()` cannot double-install a capability under a race
— that guarantee currently has zero CI coverage.
**STATUS:** FIXED
**FIX:** Added a `frontend` job (Node 22, runs all `*.test.mjs` files, then
`npm run build`) and extended the `test` job to install a JDK, download and
run the Firestore emulator via `gcloud`-free `@google-cloud/firestore`
emulator jar (see workflow), setting `FIRESTORE_EMULATOR_HOST` so the
emulator test actually runs instead of skipping.
**REGRESSION TEST:** CI itself — first green run after this change is the
regression test.
**VERIFICATION:** Workflow YAML validated locally; cannot watch a live GH
Actions run from this sandbox (no push-triggered CI visibility tool here).
Owner should confirm the next CI run on this branch shows both new jobs
green.
**COMMIT:** `b9e768b`
**REMAINING WORK:** None — owner should watch the first real run.

---

## BUG-001

**SEVERITY:** P0
**AREA:** Frontend / Mission dispatch
**FILE(S):** `web/src/v4/AppV4.jsx`
**PROBLEM:** The hero mission-input box defaulted to a real, editable,
pre-filled value — the literal historical demo phrase "Pull the US birth
totals from 2005 and brief me" — bound via `value={prompt}`, not a
`placeholder`. A user opening `/v4` and clicking Send with zero typing or
speech would submit that phrase as their own request.
**ROOT CAUSE:** Carried over from an earlier development phase where the
input was seeded with a working example and never reset to empty once
`send()` became real.
**USER IMPACT:** Silent substitution of the user's real (absent) intent
with a hardcoded demo task — exactly the "never silently substitute a demo
task" violation called out as highest priority in this project's own
governing rules.
**SECURITY IMPACT:** None (no privilege implications), but a direct
integrity/honesty violation of the product's core promise.
**STATUS:** FIXED
**FIX:** Default changed to `useState("")`.
**REGRESSION TEST:** `prompt_default_check.mjs` (Playwright, 2/2: fresh page
load has a genuinely empty input; Send with zero interaction is a true
no-op) + full `voice_smoke.mjs` re-run (13/13, no regression).
**VERIFICATION:** LOCAL VERIFIED (Playwright, this sandbox). Not yet
PRODUCTION VERIFIED (egress blocked from this environment).
**COMMIT:** `0569371`
**REMAINING WORK:** None.

---

## BUG-004

**SEVERITY:** P2
**AREA:** SYNAPSE / observability / SSE reliability
**FILE(S):** `app/synapse/engine.py`
**PROBLEM:** A client disconnecting mid-acquisition (browser tab closed,
network drop) genuinely abandons the acquisition — nothing continues
driving it in the background — and, because `firestore_store
.save_capability()` for a new candidate only runs once the pipeline
reaches `AWAITING_APPROVAL`, a disconnect at any earlier stage
(`GUARDIAN_PRESCREEN` through `GUARDIAN_SCREEN`) previously left **zero**
trace anywhere: no capability document, no audit event. Real work already
done (a real `generate_candidate` call, a real sandbox execution, a real
evaluator call) could be silently thrown away with no record it ever
happened.

An earlier pass in this same session had reasoned (without empirically
testing it) that disconnects were harmless because "side effects happen
as the generator advances, independent of whether the HTTP response is
being read." That reasoning was WRONG and is corrected here: Starlette's
`StreamingResponse.stream_response()` simply stops calling `__next__()`
on the generator once a `send()` to the broken socket fails — nothing
else drives the generator forward. Caught by directly abandoning a real
`propose_stream()` generator mid-run (not by testing an actual socket
disconnect, which is harder to fake honestly) and observing that nothing
downstream of the last-consumed stage ever executes.
**ROOT CAUSE:** `save_capability()` for a proposal-in-progress is
deliberately deferred until `AWAITING_APPROVAL` (a proposal must never
contaminate the registry before that point) — but nothing else recorded
that an attempt had even started, so an early disconnect was
indistinguishable from "nothing happened."
**USER IMPACT:** Real API-key/quota spend on research/generation/sandbox/
evaluation could vanish without a trace on a dropped connection, with no
way for the owner to know it happened or that quota was spent.
**SECURITY IMPACT:** None — no correctness or governance harm; nothing
partial can ever be mistaken for installed, approved, or in-progress
state (verified: no capability document exists after an abandoned
generator, in any case).
**STATUS:** FIXED (observability only — NOT mid-flight resumability,
which would be a genuinely large architectural change not warranted by
what was actually found, and explicitly out of scope per this register's
own "no unnecessary complexity" discipline)
**FIX:** Added one `SYNAPSE_ACQUISITION_STARTED` audit event right after
Guardian pre-screen passes, before `RESEARCH` begins — so an abandoned
acquisition is now visible in the audit trail even when it never reaches
a terminal stage, without changing the pipeline's behavior or building
resume-from-any-stage support.
**REGRESSION TEST:** `tests/test_synapse_stream.py::
test_abandoning_the_stream_before_awaiting_approval_leaves_no_capability_trace`
— directly abandons a real generator after 4 real stages, confirms no
capability document exists (never a stuck/orphaned partial one) AND that
the new audit event recorded the attempt.
**VERIFICATION:** LOCAL VERIFIED. Full backend suite re-run clean (545
passed, 2 skipped, up from 544 — one new test, no regressions).
**COMMIT:** `b9e768b`
**REMAINING WORK:** None planned. If a future session decides mid-flight
resumability (checkpointing a proposal so a reconnect can continue from
where it left off, rather than restarting) is worth the real
architectural cost, that is a new, larger design decision — flagged here,
not started.

---

## Non-issues (investigated, no fix needed — recorded per this register's own "record false alarms when significant" rule)

- **SSE stage-record mutation**: `synapse.propose_stream()` yields the same
  `AcquisitionRecord` object mutated in place at every stage (by design,
  documented in its own docstring). A naive consumer that collects yielded
  references into a list rather than snapshotting per-yield will see the
  final stage repeated N times. The real consumer (`api.py`'s SSE route)
  already snapshots correctly via `.to_dict()` inside the loop. This bit an
  ad-hoc test harness this session, not any production code path — recorded
  so a future session doesn't re-discover it as a false "production bug."
- **`install()` auto-resumes a tied mission**: calling
  `mission_service.resume_blocked()` again after `install()` already did so
  internally hits an already-COMPLETED mission and returns a `FAILED`/"not
  blocked" response. This is correct, intentional loop-closure behavior
  (`app/synapse/engine.py:563`), not a bug — a caller (frontend or test)
  should treat `install()`'s own `mission_resumed` key as the final result
  and not call resume again.
