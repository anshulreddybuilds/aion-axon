# STATE — AION Axon (Session A)

**Rewritten 22 Aug 2026 ~07:00 IST. Replace this file wholesale each session; never append.**

Session A now owns the whole repo — Session B is dead by owner ruling
(22 Aug), recorded in `CLAUDE.md`. `web/`, `README.md` and `docs/` are all
in scope; the old do-not-touch list is void.

## Where things stand

| | |
|---|---|
| Branch | `feat/core-intelligence`, pushed, level with origin |
| HEAD | `da8d8e6` |
| aion-core | `aion-core-00018-hph` · https://aion-core-638298765129.asia-south1.run.app |
| Holo-Deck | **LIVE** · https://aion-axon-2026.web.app |
| Registry | **18 declared, 10 implemented** |
| Implemented | calculator · web_research · read_dataset · write_brief · convert_currency_amount · detect_yoy_anomalies · analyze_yoy_alert · summarize_performance_text · analyze_complaint_urgency · analyze_review_sentiment |
| Telemetry | 18 model calls (all measured), 65,486 tokens, 33 gated runs |
| Approval queue | 0 |
| Tests | **266 passing, 0 errors** on a bare `pytest -q` |
| current_amendment | 13 |

## Blockers

**1. Gemini free-tier DAILY quota exhausted** (hit 21 Aug 23:15 UTC).
`limit: 20, GenerateRequestsPerDayPerProjectPerModel-FreeTier`. The
`retryDelay` in that error is misleading — it is the daily cap, not a rate
limit. Resets ~12:30 IST. Do not poll. Unblocks permanently when the $150
credits land (~25 Aug).

Nothing else is blocked.

## Next 3 priorities

**1. Phase 8 fire drill — the ONE continuous messy-workflow run.**
Every ingredient exists and each is individually proven live: acquisition,
BigQuery dataset, anomaly analysis, and now the brief. They have never run
as a single unbroken mission, which is exactly what the locked §9 demo
shows. **Needs quota.** This is the highest-value remaining item.

**2. Phase 10 reliability — the full demo unattended, twice in a row.**
The next roadmap gate after the fire drill. Needs quota.

**3. Holo-Deck write access — owner decision, not a bug.**
Approve / Reject / kill switch return **401** in the browser, because the
browser holds no owner token by design (same property the sandbox has).
Either add a paste-your-token field held in memory only, or accept that the
demo drives writes from `scripts/approve.py` and the Holo-Deck stays a read
surface. **A judge clicking a dead Approve button is worse than no button.**
Rollback also has a working API route with no UI.

## Outstanding owner actions

- **Wait for quota reset (~12:30 IST), then run priority 1.**
- Decide priority 3 (Holo-Deck writes, or accept read-only).
- The 3D mandate (22 Aug) is recorded in `docs/upgrade-plan.md`. The
  Synapse Theater below now delivers the hero visual **without WebGL**;
  decide whether that satisfies it or whether real 3D is still wanted.
  If it is, the deadline is **27 Aug** or the current version gets filmed.

## DONE 21–22 Aug — do not rebuild

**Capabilities and the loop**
- **`write_brief` (`7ac0125`)** — the mission's product, declared since day
  one and never built. Deterministic and model-free: cannot invent a figure,
  cannot be rate-limited. Verified live on mission `e37b2464` **while the
  Gemini planner was returning 429**, which is real evidence that the
  deliverable does not depend on model availability.
- **Acquisition #3 `analyze_yoy_alert`** (Gemma 100/PASS) after the 20 Aug
  quota block.
- **Both Stage 12 fixes VERIFIED LIVE** (`e9a44a5`, `655102c`) on mission
  `ab1f0b35` / `analyze_review_sentiment`: `COMPLETED`, `tool` backfilled,
  original request text passed as args, returned
  `sentiment: Negative, rationale: "crushed"`. Cost **zero quota** — the
  SYNAPSE proposal had been banked before the cap hit.
- **Approval queue cleared** — 11 stale requests rejected; the installed
  capability verified still READY at version 1 afterwards.

**The Holo-Deck**
- **Deployed to Firebase Hosting.** Required adding Firebase to a
  Cloud-only project: Management API enabled, then adoption **through the
  console** (`firebase projects:addfirebase` 403s until terms are accepted).
  On **Blaze** because billing was already enabled; free-tier allowances
  cover ~275 kB against 360 MB/day.
  ⚠️ **Never delete the project from the Firebase console — it deletes the
  Cloud project and everything in it.**
- **Synapse Theater built (`8dcbd44`)** — the §5.1 hero that was never
  built. The six §6.1 runtime agents side by side, each showing a real
  number from the live API. A pulse fires **only** when that agent's own
  counter moves between polls; the first poll only sets a baseline. Proven
  with a DOM observer: a real mission produced 9 pulse mutations, 12s of
  idle produced 0. Depth from layered SVG gradients, blur and a 9° CSS
  tilt — **no WebGL**, so the recorded video cannot stutter.
- **Zero decorative motion (`da8d8e6`)** — the AXON orb and the LiveBadge
  dot both breathed unconditionally. Both now still when idle. Verified by
  walking every element on the deployed page and reading computed
  `animationName`: 0 animating while idle.

**Fixes found by actually running things**
- `3c6d488` — `POST /missions` defaulted `tool`/`args`, so a free-text
  request built a mission that failed later with a bare `TypeError`.
- `5b19070` — **full-suite state leak, 121 errors → 0.**
  `scripts/test_approval_resume.py` was a probe matching `test_*.py`, and
  `scripts/` sorts before `tests/`, so it built a real `AxonFirestore`
  before any test set `AXON_FIRESTORE_MODE`. **CI never saw it because CI
  passes `tests` explicitly** — green for maintainers, broken for anyone who
  cloned the repo. Fixed with a rootdir `conftest.py`, `pytest.ini
  testpaths`, and renaming the probe. Guarded by
  `tests/test_store_isolation.py`, which deliberately does not set the env
  var so it tests the conftest rather than its own preamble.
- `b1a6bf0` — **CORS blocked every Firebase preview channel.** Channels get
  a generated subdomain that cannot be listed ahead of time, so the whole
  review-before-live process was dead. Fixed with an anchored regex pinned
  to this project's prefix; four near-miss hostile origins are tested.
- `f94cc91` — **the cache header never applied.** Rules match the REQUEST
  path, not the file served, so a rule on `/index.html` never fired for
  visitors requesting `/`. Every visitor had a **one-hour stale window**;
  it bit live immediately after promoting the Theater. `no-cache` is now the
  catch-all with hashed assets overriding it.

**Documentation corrected (5 stale claims)**
- `docs/audit.md` listed Stages 12, 14 and 10 as the top-3 not-started
  priorities when all three had shipped that same morning.
- The README's **90-second happy path would have 401'd a judge** — every
  write example was missing `X-Axon-Token` — and it claimed `write_brief`
  was an unimplemented gap after it had been built. Both fixed and the
  documented outputs re-run against the live service.
- `PROGRESS.md` listed phases 3–8 as NOT STARTED when all six were live.
- README's Holo-Deck limitation rewritten twice: "not built" → "built, not
  deployed" → "live but read-only".

## The lessons worth carrying

**"Implemented and tested" had not yet meant "run once for real."**
Stage 12 was marked IMPLEMENTED with passing tests, but every test covered
only one gap shape. The first real live run hit the other shape and found
two bugs back to back.

**Green CI is not the same as a working repo.** The suite passed for
maintainers and failed for anyone who cloned it, for months of commits,
because CI happened to invoke pytest differently than a human would.

**Deploying is a test.** The preview channel found a CORS hole, a stale-cache
bug and one of my own bugs within minutes — none of which any amount of
local testing would have surfaced.
