# STATE — AION Axon (Session A, core intelligence)

**Rewritten 22 Aug 2026 ~04:45 IST. Replace this file wholesale each session; never append.**

## Where things stand

| | |
|---|---|
| Branch | `feat/core-intelligence`, pushed, level with origin |
| HEAD | `4c9581b` |
| Live revision | `aion-core-00017-fzq` |
| Core URL | https://aion-core-638298765129.asia-south1.run.app |
| Registry (live) | **17 declared, 9 implemented** |
| Implemented | calculator · web_research · read_dataset · convert_currency_amount · detect_yoy_anomalies · analyze_yoy_alert · summarize_performance_text · analyze_complaint_urgency · **write_brief** |
| Telemetry (live) | 18 model calls, all measured, 65,486 tokens; 26 tool executions |
| Tests | **83 passing** across test_loop_closure / test_synapse / test_mission_engine / test_api / test_reliability / test_brief_writer |
| current_amendment | 13 |

**Test-count caveat:** 83 is the count for those five files run together. The
FULL suite (`pytest -q`, no path filter) does NOT pass — see blocker 2.

## Blockers

**1. Gemini free-tier DAILY quota exhausted (hard stop, hit 21 Aug 23:15 UTC).**
`limit: 20, GenerateRequestsPerDayPerProjectPerModel-FreeTier, gemini-3.6-flash`.
The `retryDelay: 9s` in the error is misleading — it is the daily cap, not a
rate limit. Resets ~12:30 IST. Do not retry or poll before then. Unblocks
permanently when the $150 credits land (~25 Aug).

**2. Full-suite cross-test-file state leak — 121 errors, NOT FIXED.**
Pre-existing on clean HEAD, not caused by this session's changes. Root cause
found: `firestore_store` (`app/memory/firestore_store.py`) is a module-level
singleton whose class is chosen ONCE at import time from `AXON_FIRESTORE_MODE`
(memory-store has `.capabilities`; real `AxonFirestore` does not). Full-suite
import order can hand `tests/test_adversarial.py`'s `clean` fixture the real
class → `AttributeError: 'AxonFirestore' object has no attribute
'capabilities'`. Fix direction: make the backend a fixture-scoped injected
dependency, not an env-var-gated module singleton. Full detail in
`docs/audit.md`.

## Next 3 priorities

**1. Finish live-verifying the args-backfill fix (`655102c`) — needs quota.**
Two Stage 12 bugs were found live 21 Aug and both are fixed + deployed:
- `e9a44a5` (tool-name backfill) — **VERIFIED LIVE**, mission `3c60715b`.
- `655102c` (args backfill) — **tests pass, proven by revert, but NOT yet
  confirmed live.** Deployed in `00016-kjz`.

To verify: `POST /missions/planned` with any free-text request that has no
matching capability → confirm `tool: null` + BLOCKED → `POST
/missions/{id}/acquire` → `scripts/approve.py <request_id>` → `POST
/synapse/install/<capability>` → the mission must come back **COMPLETED with a
real non-error result**. Use a FRESH request; the already-installed
`analyze_complaint_urgency` and `summarize_performance_text` will mask the test.

Mission `ab1f0b35-5eed-4632-b0dc-760abcc66316` is sitting BLOCKED with
`tool: null` and can be reused — `/acquire` on it is the exact call that
429'd. Cheapest resume path: retry that one call after quota reset.

**DONE 21 Aug (`7ac0125`) — `write_brief` built and live.** Kept here only
so the next reader does not rebuild it. Deterministic, model-free, 8 tests.
Verified live on mission `e37b2464` — and it rendered a full brief **while the
Gemini planner was returning 429**, evidencing that the mission's product does
not depend on model availability. The real priority 2 is below.

**2. Phase 8 fire drill — the ONE continuous messy-workflow run.**
Every ingredient now exists (acquisition ✓, dataset ✓, brief ✓) but they have
never been run as a single unbroken mission, which is what the locked §9 demo
actually shows. Needs quota for the planner.

**3. DEPLOY the Holo-Deck. It is BUILT — only hosting is missing.**
Owner ruled 22 Aug: **Session B is dead, Session A inherits everything** —
`web/`, `README.md` and `docs/` are now in scope, and the old do-not-touch
list is void (recorded in `CLAUDE.md`).

Surveyed on inheritance and the docs were wrong: `docs/audit.md` and
`README.md` both said the UI "is not built". It IS built — `web/` is a
React/Vite/Tailwind app, ~960 lines across `App.jsx`, `AxonLoop.jsx`,
`panels.jsx`, `ReviewPanel.jsx`, `api.js`, wired to every live endpoint
(capabilities, autonomy, evolution, monitors, approvals, telemetry,
sandbox proof) with `Promise.allSettled` so one dead endpoint cannot blank
the screen. It reads the governed API rather than Firestore directly, so
the browser holds no credentials. `web/dist/` is built and NEWER than
`web/src/`. README corrected 22 Aug.

**The only gap is deployment:** no `firebase.json`, no `.firebaserc`, and
`https://aion-axon-2026.web.app` returns **404**. The API's CORS allowlist
already names that origin, so the backend is ready for it. This is a
config-plus-`firebase deploy` job, NOT a build job — much smaller than the
roadmap assumed. Needs an owner console step (`firebase login`).

## Outstanding owner actions

- **Wait for quota reset (~12:30 IST 22 Aug), then run priority 1.** Nothing
  else in Session A's scope is blocked on the owner.
- Confirm whether Session B (README.md, docs/, Holo-Deck) is still active.

## What this session actually did (21 Aug)

- Deployed `aion-core` with owner-token auth; verified writes 401 without it.
- **Acquisition #3 closed** (`analyze_yoy_alert`, Gemma 100/PASS) after the
  20 Aug quota block; registry 14→15, autonomy 32%→47%; verified live.
- **Corrected three stale "not started" claims** in `docs/audit.md` — Stages
  12, 14 and 10 had all shipped that morning (`b330877`, `d451dcf`) and the
  doc still listed them as the top 3 priorities.
- **Fixed 3 real bugs, each with a regression test proven by reverting the fix
  and watching the test fail:**
  - `3c6d488` — `POST /missions` defaulted `tool`/`args`, letting a free-text
    request build a mission that failed later with a bare `TypeError`.
  - `e9a44a5` — a `tool: null` blocked step never got the installed
    capability's name written back, so the mission stayed BLOCKED forever
    despite auto-resume firing correctly.
  - `655102c` — the same step's `args` stayed `[]`, so the newly installed
    capability ran with no arguments and crashed on its own parameter.
- Notion master plan session log updated, including a correction paragraph
  for the Stage 14 staleness.

**The lesson worth carrying:** Stage 12 was marked IMPLEMENTED and had passing
tests, but every test covered only ONE gap shape (planner names an
unimplemented capability). The first real live run hit the other shape
(`tool: null`) and found two bugs in a row. "Implemented and tested" had not
yet meant "run once for real."
