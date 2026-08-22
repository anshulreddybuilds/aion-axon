# STATE — AION Axon (Session A)

**Rewritten 22 Aug 2026 ~13:45 IST. Replace this file wholesale each session; never append.**

Session A owns the whole repo — Session B is dead by owner ruling (22 Aug),
recorded in `CLAUDE.md`. `web/`, `README.md` and `docs/` are all in scope.

## Where things stand

| | |
|---|---|
| Branch | `feat/core-intelligence`, pushed, level with origin |
| HEAD | `989115b` |
| aion-core | `aion-core-00023-bvv` · https://aion-core-638298765129.asia-south1.run.app |
| Holo-Deck | **LIVE** · https://aion-axon-2026.web.app (noindex + robots.txt) |
| Registry | **19 declared, 11 implemented** |
| Telemetry | 26 model calls, 92,390 tokens, 48 gated runs |
| Evolution events | 7 |
| Approval queue | 0 |
| Tests | **279 passing**, enforced by a pre-push hook |
| current_amendment | 13 |

## 🔴 PHASE 8 FIRE DRILL — PASSED (22 Aug)

The locked demo story ran end to end, unbroken, on the live stack.
Mission `19bf2bf0-bef3-4208-a1f3-20013852c244`:

```
1. read_dataset            9 rows from BigQuery public data (~89MB)
2. GAP — no CAGR tool      mission BLOCKED mid-flight
3. SYNAPSE acquires        safety PASS · sandbox PASS · Gemma 100/PASS
4. STOPS at approval       owner approved calculate_birth_cagr
5. install                 registry 10 -> 11, autonomy 32% -> 47%
6. MISSION FINISHES ITSELF CAGR -0.9987%/yr across 2005-2013
```

Nobody re-ran anything. Earlier the same day a no-gap variant also
completed (mission `6337bd7c`), finding the **2006 / 2009 / 2010**
anomalies — the post-2008 US birth decline, checkable against the outside
world rather than against the system's own claims.

## Blockers

**Gemini free-tier daily quota** — 20 requests/day. Roughly 15 spent on
22 Aug across five drill runs. Resets ~12:30 IST. On 429: check once,
record, stop. Unblocks permanently when the $150 credits land (~25 Aug).

Nothing else is blocked.

## Next 3 priorities

**1. 🎬 THE VIDEO — the real deadline risk.**
Nothing has been shot. It is 30% of the score and the only deliverable
that cannot be crammed at the end. The system is now demo-ready and the
shot list is corrected; this is the thing most likely to cost the
submission. **Start filming before adding anything else.**

**2. Phase 10 reliability — the full demo unattended, twice in a row.**
`scripts/golden_path.py` is the rehearsal. Needs quota.

**3. Holo-Deck write access — owner decision, still open.**
Approve / Reject / kill switch return 401 in the browser by design, since
the browser holds no owner token. Either add an in-memory token field or
accept that the demo drives writes from `scripts/approve.py`. **A judge
clicking a dead button on camera is worse than no button.** Also open:
the owner asked about voice + chat input, which is legal under the Google
rules (nothing forbids it; Best Multimodal UX is a $5,000 bonus) and
should use the browser Web Speech API rather than a paid GCP service —
but only after the video exists.

## Outstanding owner actions

- Decide priority 3.
- Keep the URLs unshared until submission — see Secrecy below.

## Secrecy posture (owner asked, 22 Aug)

- GitHub repo: **PRIVATE**. The implementation was never exposed.
- Sandbox: **403** to the public internet.
- API + Holo-Deck: **publicly reachable** — they must be, since rules 5, 7
  and 11 require a public video, judge repo access and a hosted URL. But
  reachable is not findable: `noindex` + `robots.txt` now keep both out of
  search results.
- Nothing forbids staying quiet until 30 Aug. Publishing then, timestamped
  on Devpost, is what actually establishes authorship — staying hidden
  forever is the riskier option.

## DONE 21–22 Aug — do not rebuild

**The loop**
- `write_brief` (`7ac0125`) — the mission's product. Deterministic and
  model-free; verified live **during a total Gemini outage**, which is
  real evidence the deliverable does not depend on model availability.
- Both Stage 12 auto-resume fixes verified live (`e9a44a5`, `655102c`).
- Phase 8 fire drill passed (above).
- Approval queue cleared; 11 stale requests rejected.

**The Holo-Deck**
- Deployed to Firebase Hosting. Firebase had to be added to a Cloud-only
  project via the console (`projects:addfirebase` 403s until terms are
  accepted). On **Blaze** because billing was already enabled; free-tier
  allowances cover ~275 kB against 360 MB/day.
  ⚠️ **Never delete the project from the Firebase console — it deletes the
  Cloud project and everything in it.**
- Command-surface redesign from the owner's Replit mockup (`989115b` line):
  four views — Command, Pipeline, Autonomy ledger, Evidence — with the
  twelve-node execution topology, completion ring and inventory table.
  The design was adopted; its numbers were not. The mockup hard-coded 42%
  and six LOCKED stages; the live surface reads **92%** because it counts
  what is genuinely verified.
- Zero decorative motion, verified on the deployed DOM.

**Six real bugs, all found by RUNNING it**
| Fix | What it was |
|---|---|
| `3c6d488` | `POST /missions` defaulted tool/args |
| `d19f88e` | **mission reported COMPLETED on failed steps** |
| `d19f88e` | no data flowed between steps — added `$STEP_n` |
| (same) | `$STEP_n.field` for reaching inside a result envelope |
| — | SYNAPSE never saw the real input, so it guessed the data shape |
| — | generator wrote brittle float assertions, discarding working code |
| — | planner could not see parameter names, so it put the CAGR in the title |

**Infrastructure**
- `5b19070` — full-suite state leak, 121 errors to 0.
- `b1a6bf0` — CORS blocked every Firebase preview channel.
- `f94cc91` — cache header never applied; every visitor had a stale hour.
- **Pre-push hook** (`989115b`) — see below.

## The mistake, and the mechanism that replaces the promise

On 22 Aug the catalog-signature change was committed **and deployed** with
two failing tests. They passed file-by-file and the full suite was not
re-run before pushing.

That is the same shape as the 121 collection errors: **a check that depends
on remembering to run it is not a check.** The fix is therefore not "be
more careful" but `.githooks/pre-push`, wired via `core.hooksPath` so it
survives a fresh clone. Proven in both directions — a deliberately broken
test was refused, and the green suite went through.

## Lessons worth carrying

**"Implemented and tested" is not "run once for real."** Every bug in the
table above survived code review and a green suite. All six died the first
time the thing actually ran.

**Green CI is not a working repo.** The suite passed for maintainers and
failed for anyone who cloned it, for many commits.

**Three of the six bugs were the same disease:** the model was guessing at
something nobody had shown it — the data shape, the argument names, how to
write a test that does not throw away its own work. The fix each time was
to show it, not to prompt harder.
