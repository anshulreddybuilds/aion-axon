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
| Tests | **264 passing, 0 errors** — full suite, bare `pytest -q` |
| current_amendment | 13 |

(The full suite genuinely passes now; there is no longer a per-file caveat.)

## Blockers

**1. Gemini free-tier DAILY quota exhausted (hard stop, hit 21 Aug 23:15 UTC).**
`limit: 20, GenerateRequestsPerDayPerProjectPerModel-FreeTier, gemini-3.6-flash`.
The `retryDelay: 9s` in the error is misleading — it is the daily cap, not a
rate limit. Resets ~12:30 IST. Do not retry or poll before then. Unblocks
permanently when the $150 credits land (~25 Aug).

**2. RESOLVED 22 Aug — full-suite state leak.** Was 121 errors on a bare
`pytest -q`. Cause: `scripts/test_approval_resume.py` was a probe matching
`test_*.py`, imported before `tests/` alphabetically, which built a real
`AxonFirestore` before any test set `AXON_FIRESTORE_MODE`. CI never saw it
(CI passes `tests` explicitly), so the repo was green for maintainers and
broken for anyone cloning it. Fixed with a rootdir `conftest.py`,
`pytest.ini testpaths = tests`, and renaming the probe. Guarded by
`tests/test_store_isolation.py`, proven by deleting the conftest and
watching it fail. **264 passed, 0 errors, both invocations.**

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

**2. Reliability (Phase 10) — run the full demo unattended twice in a row.**
With the suite green and the queue clear, this is the next roadmap gate.

**3. 3D Holo-Deck (owner mandate 22 Aug) + write access.** Full plan in
`docs/upgrade-plan.md`. The owner ruled the UI gets a 3D interface
regardless; that overrides `CLAUDE.md` §P9's "no WebGL" line, but the
reason for that line (frame drops on an 8GB machine *while screen
recording*) becomes a build constraint. **The live 2D Holo-Deck stays
deployed as the fallback, and 3D must be demo-ready by 27 Aug or the 2D
version gets filmed.** The rule that must survive the rebuild: every
animation is a real event, never idle decoration.

Separately, on the same surface:
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
- **Approval queue cleared (22 Aug).** 11 stale requests rejected via
  `scripts/clean_approvals.py --apply`: 7 `purchase item` and 2 other test
  artifacts (13-64h old), plus 2 duplicate `install capability:
  analyze_review_sentiment` proposals left over from the 429-ing acquire
  attempts. All superseded — that capability was already READY at version 1,
  and **verified still READY at version 1 after the rejections**, confirming
  a rejected duplicate proposal does not disturb an installed capability.
  Queue now 0. Rejections are recorded in the audit trail, not deleted.
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
