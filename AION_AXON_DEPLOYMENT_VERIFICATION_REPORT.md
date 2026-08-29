# AION AXON — Deployment + Live Verification Phase Report

**Date:** 2026-08-27
**Scope:** Re-verify the prior session's claims from scratch (nothing trusted blindly), then attempt to carry the system from CODE READY to LIVE/TRIAL READY.

---

## Ground Truth (Phase 1) — re-verified, not assumed

```
Branch:   feat/beastmode-core-oagiwb-weku3h
HEAD:     0b7b957 (this session's new commit; f6ae294 confirmed as its immediate parent)
Status:   clean
Remote:   matches local exactly (git fetch + rev-parse, both sides equal)
```

Secret scan re-run across the **whole repo**, not just the diff: no API keys, service-account JSON, private keys, or `.env` files tracked. Clean.

---

## Phase 2 — Full Local Regression, Run Fresh (not re-reported)

| Suite | Result |
|---|---|
| Backend (`AXON_FIRESTORE_MODE=memory`, full suite) | **566 passed, 3 skipped, 0 failed** |
| Firestore emulator suite (real emulator, started fresh this session — Java 21 + firebase-tools, same as CI) | **3 passed, 0 failed** (all three: install-transaction scaffold, real `install()` race, real `decide()` race) |
| Frontend (`node --test src/*.test.mjs` and the CI-equivalent plain-`node` loop) | **9/9 files, 90 assertions, 0 failed** |
| Production build (`npm run build`) | **PASS** |

Nothing failed. No test was weakened, skipped-around, or deleted to get here.

---

## Phase 3 — Governance/Security Audit: one real bug found and fixed

Re-checking the mutation surface directly rather than trusting the previous report's conclusions surfaced **one genuine, previously-undiscovered bug**:

### CONFIRMED BUG (fixed this session): Ledger Seal was not durable on Cloud Run

`POST /beastmode/ledger/seal` / `GET /beastmode/ledger/verify` (`app/beastmode/ledger_chain.py`) read and wrote a JSON file **next to the Python module** (`SEAL_PATH = Path(__file__).parent / "ledger_seal.json"`) instead of Firestore — the only piece of state in this entire codebase that didn't use `firestore_store`.

This is a real bug, not a style nit: **Cloud Run containers are stateless.** Their filesystem is neither shared across concurrently-running instances nor durable across a cold start or redeploy. A seal written by one instance is invisible to every other instance, and is wiped the moment that instance is recycled — the opposite of what "sealed baseline" is supposed to mean for a feature whose entire purpose is being tamper-evident governance proof, one Judge Mode explicitly showcases.

**It gets worse:** a stale `ledger_seal.json` from a local test run had already been **accidentally committed to git** (in commit `c9ec542`, unrelated to ledger work) and would have been baked into every Docker build via `COPY app ./app` — meaning a fresh production container could start already claiming "16 events sealed" with a hash nobody in that environment actually produced.

**Fixed:** seal storage moved to Firestore (`system/ledger_seal`, mirroring how `KillSwitch` already stores its state in `system/control`), added to both `MemoryFirestore` and `AxonFirestore`. The stray committed file was removed. Proven against a real Firestore emulator with **two independent `AxonFirestore` client instances** (standing in for two separate Cloud Run containers) — both see the same seal, which is exactly the property that was broken before:

```
REAL FIRESTORE ledger seal round-trip: PASS
cross-instance visibility: PASS
```

Two new regression tests added and passing: one exercising cross-instance durability directly, one proving `seal()` no longer touches the old local-disk path at all (`tests/test_ledger_forensics.py`).

### Mutation endpoint audit — the required 7-question table, for the governance-critical routes

| Endpoint | Who can call | Duplicate calls | Concurrent | Kill switch mid-op | Network fail after commit | UI retry | UI matches server state |
|---|---|---|---|---|---|---|---|
| `POST /approvals/{id}/decide` | Owner (bearer token, `secrets.compare_digest`) | 2nd call → `ALREADY_DECIDED`, clean 200 | **Fixed this pass** — real Firestore transaction, proven race-free | Checked before the transaction; a switch flip in the narrow window between check and commit can still let one decision through (confirmed risk, pre-existing, not a data-corruption bug — see below) | Decision already durably committed; client retry hits `ALREADY_DECIDED` | Safe — same as above | **Fixed this pass** (App.jsx + MissionTheater.jsx now check the real status) |
| `POST /synapse/install/{capability}` | Owner | 2nd call → `ALREADY_INSTALLED` (idempotent, proven under 10 real concurrent emulator callers) | Safe — `claim_install()` real transaction | Same narrow-window shape as above (checked before, not inside, the transaction) | Claim already committed; retry is idempotent | Safe | Frontend correctly distinguishes `INSTALLED`/`ALREADY_INSTALLED` from real failures (existing `reconcileRecord()` logic, verified) |
| `POST /killswitch` | Owner | Idempotent by construction (boolean flag, last-write-wins is correct for a flag) | Safe — no meaningful race on a pure state flag | N/A | Idempotent | Safe | `GET /killswitch` always reflects current real state |
| `POST /missions/{id}/resume*` (3 routes) | Owner | 2nd call → `FAILED` via a status guard (not a transaction) | **Confirmed risk, not fixed this pass** — same TOCTOU shape as the approval race, no test proves it either way | Not checked at this layer directly (relies on `execution_gate`'s own check) | Real tool side effects can occur before the mission document reflects them (documented, not new) | Depends on idempotency of the underlying tool, out of this audit's scope | Depends on the above |
| `POST /beastmode/ledger/seal` | Owner | **Fixed this pass** — now durable and consistent across instances; each call still legitimately creates a new baseline (by design — sealing again after new events is the normal flow) | Two racing seals: last-write-wins on the Firestore doc, no transaction — **confirmed risk, not fixed** (a real edge case, but sealing is a rare, deliberate owner action, not a hot path; classified P3) | N/A | Idempotent from the caller's perspective (a retry just re-seals) | Now safe (auto-fire-on-mount was already fixed last session; double-submit guard already added) | **Fixed last session** (Judge Mode's `LedgerSealCard`) |

**Classification, as requested:**
- Ledger Seal durability → **confirmed bug**, fixed.
- Approval-decide / install kill-switch check-before-not-inside-transaction window → **design limitation**, pre-existing, narrow, not newly introduced or worsened. Not fixed this pass (closing it means moving the kill-switch check inside the same transaction, a real change to a hot path, not justified by a demonstrated failure).
- Mission-resume TOCTOU → **confirmed risk**, undemonstrated, not fixed (same conclusion as the prior report).
- Ledger-seal concurrent-seal race → **confirmed risk**, low priority (rare, deliberate, owner-only action).

---

## Phase 4 — Deployment Access: NOT AVAILABLE

Checked directly, not assumed from a prior session:

```
gcloud:                  not installed
firebase:                not installed
~/.config/gcloud (ADC):  does not exist
GOOGLE_*/GCP_*/FIREBASE_* env vars: none set
curl to *.run.app:       blocked by this environment's own egress proxy (403 on the CONNECT tunnel itself)
curl to *.web.app:       blocked the same way
curl to *.googleapis.com: reachable (404 — a real response from Google, not a block) — meaning even WITH credentials, only the *.run.app/*.web.app hostnames are blocked here, not Google's own APIs, but that's moot without credentials anyway
```

**Per your explicit instruction: stopping here before any deployment.**

### Exact commands and access needed (for you, or a session running on a machine that has them)

Per `CLAUDE.md`'s own environment notes, the owner's Windows machine already has the Google Cloud SDK at `%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin` (not on PATH by default) and a working `gcloud`/Firestore ADC setup used earlier in this project. From that machine (or any environment with equivalent access):

```powershell
# 1. Pull the verified commit
git fetch origin feat/beastmode-core-oagiwb-weku3h
git checkout feat/beastmode-core-oagiwb-weku3h
git log -1   # confirm HEAD is 0b7b957 or a later fast-forward of it

# 2. Authenticate (if not already)
gcloud auth login
gcloud config set project aion-axon-2026

# 3. Deploy the backend (aion-core) to Cloud Run, asia-south1, per CLAUDE.md's own P2 deployment notes
gcloud run deploy aion-core --source . --region asia-south1 --project aion-axon-2026

# 4. Build and deploy the frontend to Firebase Hosting
cd web
npm ci
npm run build
firebase deploy --only hosting --project aion-axon-2026

# 5. Verify the deployed commit
gcloud run services describe aion-core --region asia-south1 --format="value(status.latestReadyRevisionName)"
curl https://aion-core-638298765129.asia-south1.run.app/health
```

Required access: a Google account authorized on GCP project `aion-axon-2026` (Cloud Run Admin + Firebase Hosting Admin roles, or owner), and the Firebase CLI logged into the same project. **No credentials were invented, requested, or assumed to make this happen from this session** — this is a genuine access gap, not a policy choice.

---

## Phases 5–9 — NOT PERFORMED

Deployment, live health verification, live concurrency verification, and the end-to-end trial smoke test all require reaching the live Cloud Run/Firebase Hosting services, which this session cannot do (Phase 4). **No fabricated results are reported for these phases.** They must be run by whoever executes the Phase 4 deployment steps, ideally with this same rigor: real requests, real status checks, no narrated-but-unexecuted claims.

---

## Phase 10 — Final Architecture Audit (grep-based, whole repo)

| Search | Result |
|---|---|
| `TODO` / `FIXME` / `HACK` / `XXX` | **Zero matches** anywhere in `app/` or `web/src/` |
| Disabled/bypassed security checks | None — every "bypass" match is either policy text asserting the Guardian *cannot* be bypassed, or red-team test vectors proving bypass attempts are *blocked* |
| Commented-out authentication | None |
| Debug endpoints | None found in `app/api.py` |
| Hardcoded credentials/passwords | None |
| Bare `except:` / silent `except Exception: pass` | **Zero** — every exception handler in `app/` does something (returns a structured error, logs, or re-raises) |
| Hardcoded localhost/ports outside legitimate dev CORS config | None beyond the documented `ALLOWED_ORIGINS` dev fallback list |
| Fake/mock/stub production behavior | None — every "fabricat(e/ed)" hit in `app/` is defensive documentation about *avoiding* fabrication (e.g., the evaluator's own docstring: "a fabricated score is worse than a missing one") |

**No production or trial blockers found in this pass.** This corroborates rather than contradicts the prior session's equivalent finding — independently re-run, not copied.

---

## Phase 11 — Final Trial Readiness Gate

```
[GREEN]  repository integrity        -- HEAD 0b7b957, clean, remote matches, no secrets
[GREEN]  backend tests                -- 566 passed, 3 skipped (all honest, all independently verified), 0 failed
[GREEN]  frontend tests                -- 9/9 files, 90 assertions, 0 failed
[GREEN]  production build              -- vite build succeeds
[GREEN]  Firestore transaction safety  -- approval-decide + install races both proven closed against a REAL emulator
[GREEN]  approval flow                 -- false-success bug fixed in both UI entry points; contract fully documented
[GREEN]  install/reconcile             -- idempotent, proven under real concurrent load
[YELLOW] mission resume                -- status-guarded, not transactional; same TOCTOU shape as the fixed approval race, undemonstrated
[GREEN]  kill switch                   -- fail-safe, blocks decide/install; narrow pre-existing check-before-transaction window noted, not newly introduced
[GREEN]  owner authentication          -- constant-time compare, fail-closed, never logged, every mutating route gated (2 public POSTs confirmed read-only)
[GREEN]  audit trail                   -- mission_id gap fixed; SSE errors surfaced to client but not separately server-audited (minor, documented)
[GREEN]  Judge Mode                    -- auto-fire-on-mount and double-submit bugs fixed last session, re-verified this session
[GREEN]  Ledger Seal                   -- NEW this session: durability bug found AND fixed, proven cross-instance against a real emulator
[GREEN]  CORS                          -- strict anchored allowlist, re-verified, not weakened
[RED]    production deployment          -- NOT PERFORMED (no access from this environment)
[RED]    live backend                   -- UNKNOWN (unreachable from this environment)
[RED]    live frontend                  -- UNKNOWN (unreachable from this environment)
[RED]    live API connectivity          -- UNKNOWN
[RED]    safe end-to-end mission (live) -- NOT PERFORMED (blocked by deployment)
[YELLOW] failure handling               -- thoroughly verified in code/tests; NOT verified against the live deployed system
[GREEN]  Gemini/AI dependency           -- every call site degrades to a typed error/PLANNER_ERROR, verified against current code and offline tests
[YELLOW] trial reproducibility          -- code-level reproducibility is solid; depends on Phase 5-9 being completed before a real trial
[GREEN]  security                       -- no new findings this pass beyond what's already documented as accepted (bearer-token replay, out of scope)
[GREEN]  observability                  -- mission_id gap fixed; remaining gaps are documented, non-blocking
```

---

## Phase 12 — Precise Terminology

- **CODE READY: YES.** All local code and tests are verified, twice now, independently.
- **DEPLOYMENT READY: YES, conditionally.** Code and deployment prerequisites (a working `gcloud`/`firebase` setup) exist for this project (documented on the owner's own machine per `CLAUDE.md`) — they are just not reachable **from this remote session**. Deployment readiness is a property of the code + access, and the access exists somewhere, just not here.
- **LIVE READY: NOT VERIFIED.** Nobody has confirmed, this session or before, that the live Cloud Run/Firebase Hosting services actually run commit `0b7b957` (or `f6ae294`, or even `782bb20`). This is unknown, not assumed good or bad.
- **TRIAL READY: NOT YET.** By your own definition, this requires a safe end-to-end mission actually exercised on the deployed system with all governance controls behaving correctly — Phases 5–9 are prerequisites that were not performed.

---

## Phase 13 — Human Approval Boundary

No consequential mission was approved on your behalf. No approval gate was bypassed. Owner authentication was not weakened. The kill switch was not touched or disabled. No execution or success was fabricated — every claim above is either a re-run test result or an explicit "not performed / unknown."

**The next irreversible-ish action is deployment itself** (Phase 5) — not irreversible in the strict sense (Cloud Run keeps prior revisions, Firebase Hosting keeps prior releases, both roll back cleanly — see the prior report's §24), but it is a real production change only you (or someone you delegate GCP/Firebase access to) can authorize and execute, since this session has no path to do it. See Phase 4 above for the exact commands.

---

## FINAL REPORT

1. **CURRENT COMMIT:** `0b7b957`
2. **BRANCH:** `feat/beastmode-core-oagiwb-weku3h` (pushed, remote matches local)
3. **TEST RESULTS:** Backend 566 passed / 3 skipped / 0 failed. Emulator 3/3 passed (real, not mocked). Frontend 9/9 files, 90 assertions, 0 failed. Build: PASS.
4. **BUGS FOUND (this phase):** 1 new — Ledger Seal not durable on Cloud Run (local-disk storage instead of Firestore), plus a stray committed test artifact that would have been baked into the Docker image.
5. **BUGS FIXED (this phase):** The Ledger Seal durability bug, in full — proven against a real emulator with two independent client instances, two new regression tests, stray file removed.
6. **BUGS LEFT OPEN (confirmed, documented, not fixed — same as the prior report plus one new item):** mission-resume TOCTOU races (undemonstrated); the approval/install kill-switch check-before-not-inside-transaction narrow window (pre-existing design limitation); concurrent-seal race on Ledger Seal itself (rare, low priority); `claim_install()`'s request_id-swap theoretical edge case; `Command.jsx`'s duplicated speech-recognition logic; SSE errors not server-side audited; bearer-token replay (explicitly out of scope, pre-existing).
7. **SECURITY FINDINGS:** No new vulnerabilities this pass. Owner auth, CORS, and the mutating-route inventory were independently re-verified, not just trusted. Ledger Seal's fix is a durability/correctness fix, not a security fix (nothing was exploitable by an outside attacker; the bug just meant the feature silently didn't work as claimed under Cloud Run's real operating model).
8. **DEPLOYMENT STATUS:** Not performed. No access from this environment (Phase 4). Exact steps and access requirements given above.
9. **LIVE VERIFICATION RESULTS:** Not performed — blocked by #8.
10. **END-TO-END TRIAL RESULT:** Not performed — blocked by #8. No fabricated success is reported.
11. **EXACT REMAINING HUMAN ACTIONS:** (a) Run the Phase 4 deployment commands from a machine/session with real `gcloud`/`firebase` access to project `aion-axon-2026`. (b) After deploying, run Phases 6–9 (live health, live concurrency, one safe end-to-end smoke mission) for real against the live URLs. (c) Only after that succeeds, call it TRIAL READY.
12. **FINAL VERDICT: 🟡 DEPLOYMENT READY** (code-side; live/trial status genuinely unknown pending steps 11a–11c).
