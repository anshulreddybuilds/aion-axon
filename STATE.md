# STATE — AION Axon (Session A, core intelligence)

**Rewritten 22 Aug 2026 ~04:45 IST. Replace this file wholesale each session; never append.**

## Where things stand

| | |
|---|---|
| Branch | `feat/core-intelligence`, pushed, level with origin |
| HEAD | `4c9581b` |
| Live revision | `aion-core-00017-fzq` · **Holo-Deck: https://aion-axon-2026.web.app** |
| Core URL | https://aion-core-638298765129.asia-south1.run.app |
| Registry (live) | **18 declared, 10 implemented** |
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

**1. Phase 8 fire drill — the ONE continuous messy-workflow run.**
Every ingredient now exists and each is individually proven live
(acquisition, BigQuery dataset, anomaly analysis, brief). They have never
been run as a single unbroken mission, which is what the locked §9 demo
actually shows. Needs Gemini quota for the planner.

**DONE — `write_brief` (`7ac0125`) — `write_brief` built and live.** Kept here only
so the next reader does not rebuild it. Deterministic, model-free, 8 tests.
Verified live on mission `e37b2464` — and it rendered a full brief **while the
Gemini planner was returning 429**, evidencing that the mission's product does
not depend on model availability. The real priority 2 is below.

**2. Clean the approval queue before filming.** The Holo-Deck shows **12
waiting** approvals, most of them stale test artifacts. A queue that long
trains a viewer (and an owner) to scroll past without reading, which is the
opposite of what the demo argues. `scripts/clean_approvals.py` exists and is
dry-run by default. Rejecting is a recorded decision, so this is an owner
action, not housekeeping.

**3. Wire owner-token entry into the Holo-Deck (or accept read-only).**
The dashboard is LIVE at **https://aion-axon-2026.web.app** (deployed 22 Aug;
`firebase.json` + `.firebaserc` at repo root, `web/dist` is the public dir).
Reads all work. **Writes do not** — Approve / Reject / kill switch will 401,
because the browser holds no owner token by design. Either add a
paste-your-token field held in memory only, or decide the demo drives writes
from the CLI and the Holo-Deck stays a read surface. **Owner decision, not a
bug.**

## DONE this session — do not rebuild

- **`write_brief` (`7ac0125`)** — the mission's product. Deterministic,
  model-free, cannot invent a figure. Verified live on mission `e37b2464`
  **during a total Gemini outage**, which is evidence that the deliverable
  does not depend on model availability.
- **Both Stage 12 fixes VERIFIED LIVE (`e9a44a5`, `655102c`)** on mission
  `ab1f0b35` / capability `analyze_review_sentiment`: came back `COMPLETED`
  with `tool` backfilled AND the original request text passed as args,
  returning `sentiment: Negative, rationale: "crushed"`. Cost zero quota —
  the SYNAPSE proposal had already been banked before the cap hit.
- **Holo-Deck deployed** — see priority 3.
- **Firebase added to the GCP project.** It was a Cloud-only project; Firebase
  Management API had to be enabled AND the project adopted via the console
  (the CLI `addfirebase` 403s until terms are accepted). Now on the **Blaze**
  plan because the project already had billing — free-tier allowances still
  apply and usage is ~275 kB against 360 MB/day. ⚠️ **Never delete the project
  from the Firebase console — that deletes the Cloud project and everything
  in it.**

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
