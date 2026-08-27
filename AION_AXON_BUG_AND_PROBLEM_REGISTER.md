# AION AXON — Bug and Problem Register

Living inventory of every issue discovered during hardening passes, per the
"never silently discard a finding" rule. Newest entries at the top. Severity:
P0 = catastrophic/security-critical, P1 = major functional failure,
P2 = reliability/usability/engineering issue, P3 = minor/polish.

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
**COMMIT:** (pending, this pass)
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
**COMMIT:** (pending, this pass)
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
**COMMIT:** (pending, this pass)
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
