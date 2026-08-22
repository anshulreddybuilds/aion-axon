# STATE — AION Axon (Session A)

**Rewritten 23 Aug 2026. Replace this file wholesale each session; never append.**

Session A owns the whole repo — Session B is dead by owner ruling (22 Aug),
recorded in `CLAUDE.md`. `web/`, `README.md` and `docs/` are all in scope.

## Where things stand

| | |
|---|---|
| Branch | `feat/core-intelligence`, pushed, level with origin |
| HEAD | `943104f` |
| aion-core | `aion-core-00027-jwn` · https://aion-core-638298765129.asia-south1.run.app |
| Holo-Deck | **LIVE** · https://aion-axon-2026.web.app (noindex + robots.txt) |
| Registry | **19 declared, 11 implemented** |
| Telemetry | 26 model calls, 92,390 tokens, 48 gated runs |
| Evolution events | 7 |
| Approval queue | 0 |
| Tests | **280 passing**, enforced by `.githooks/pre-push` |
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

## 🔴 CORS: unlocking the Holo-Deck took the whole surface down (FIXED 22 Aug)

`1e5f5c3`, live on `aion-core-00026-5sf`. **This would have hit on camera** —
the demo unlocks the Holo-Deck on screen.

`allow_headers` listed only `Content-Type`. A browser preflights any request
carrying a custom header, so the moment the owner token was pasted in, every
request preflighted for `X-Axon-Token`, got **400**, and was cancelled before
leaving the browser. Locked: perfect. Unlocked: every panel red with
"aion-core unreachable", ring falling 92% → 17%.

**Why it cost half an hour: the symptom pointed away from the cause.** `curl`
answered 200 throughout (curl does not preflight), and it reproduced in two
browsers on one machine — which reads as local antivirus or a proxy. Windows
proxy settings and AV were both checked and cleared first. The tell was that
a browser with **no token pasted in** rendered the page fine.

**279 green tests said nothing about this**, because every existing CORS test
sent a simple request and a simple request is never preflighted. The
regression test now asks the question a browser asks. Proven by reverting the
fix and watching it fail.

## 🔴 The test suite spent live quota, and green depended on the shell (FIXED)

`f65c2bc`. `conftest.py` fenced off production Firestore but left the model
API open, so the suite's behaviour turned on whether a real key happened to
be exported in the terminal that ran it:

| shell | result |
|---|---|
| no key | 280 passed, **4.5s**, zero network |
| key exported | ~**4 minutes** of real calls — one run `14 failed`, the next `280 passed`, **identical commit** |

Found when a key was exported to probe a new API key's model list and the
next `pytest -q` in that terminal came back red. Time went to hunting a
regression that did not exist.

Three problems: running tests silently spent the daily quota the demo
depends on; `.githooks/pre-push` runs this suite, so a push from a
key-holding terminal burned quota and could be blocked by a network blip on
a repo whose discipline is that red means a real defect; and green stopped
meaning anything, because it turned on ambient environment rather than code.
`AXON_LIVE_MODEL_TESTS=1` opts back in deliberately.

## Blockers

**Gemini quota — unblocked 23 Aug.** A new API key was provisioned and
stored as **version 2** of the `gemini-api-key` secret; `aion-core-00027-jwn`
is running on it. The 22 Aug exhaustion (real 429 at ~21:30 IST) is history.

⚠️ **Headroom is UNVERIFIED.** Trial credits on a Cloud project do not
automatically move the Gemini API off its free-tier per-day limit — those
are separate systems. No real generation call has been made on the new key
yet, so the first one is what proves it. On 429: check once, record, stop.

**Model IDs were checked before anything was switched, and nothing was
switched.** A proposal to move to `gemini-1.5-flash` / `gemini-1.5-pro` was
tested against the new key first: both **MISSING** from the 50 models it can
see. `gemini-3.6-flash` and the `gemma-4-26b-a4b-it` evaluator are both
**FOUND**. Adopting that proposal would have 404'd every call — and the
Gemma check mattered independently, since a key from a different project
could have silently lost evaluator access and killed the acquisition act on
camera.

Nothing else is blocked.

## Next 3 priorities

**1. SHOOT THE VIDEO. It is the only thing standing between this and a
submission.** 30% of the score, nothing filmed yet, and it cannot be
crammed on the last day. Everything it needs now exists and has been
rehearsed.

The setup is proven through THREE externally reviewed camera takes. The
run sheet is in `docs/demo-script.md`; the short version:
`cd` to the repo, `function prompt { "PS> " }`, `cls`, Ctrl+scroll until
only ~15 lines fill the terminal, F11, mouse off-screen, then `.\demo`.
`scripts/camera_test.py` rehearses every beat that costs NO quota, so the
setup can be checked without burning a Gemini call.

The acquisition act is the only part that spends quota: roughly 4 calls
against a daily 20. Shoot it FIRST in the session, while there is room to
retry.

**2. The chat panel ships TYPED. Decided — see below.**
Live on a preview channel:
https://aion-axon-2026--command-chat-du1686ek.web.app
Paste the owner token once, then type or speak a request. "Watch me talk
to it" is a much stronger four minutes than "watch me type curl", and it
targets the $5,000 Best Multimodal UX bonus. Not yet promoted to the main
site — that is a deliberate owner call, not an oversight.

**DECIDED 23 Aug: film the TYPED version. Voice is dropped from the demo.**

Not because it is unimportant — because it is a bonus, no footage exists
yet, and it had already eaten an evening. The typed one-sentence request
carries the whole premise ("a human asks in plain English" vs "a human
hand-writes curl"); voice was only ever the cherry.

Voice is **unproven end to end** and the reason is NOT in this codebase:

- Windows reports Microphone Array healthy, default, input level 94
- Chrome's site permission is granted and reads "Recently used"
- The browser still alternates `audio-capture` ("no microphone found") and
  `no-speech` ("nothing was heard")

Two real defects were found and fixed on the way (`943104f`) and are worth
keeping whether or not voice ever ships:

1. **Recognition could not survive a render.** The effect depended on
   `[onText]`, the parent passed an inline arrow, and `App.jsx` polls every
   3 seconds — so cleanup called `r.abort()` ~3s after the mic was switched
   on, every time. The 30-word demo request never survived.
2. **`onerror` threw the reason away.** Blocked mic, dead mic, network
   failure and plain silence all looked identical: the button just stopped
   glowing.

The second is why the first cost an evening. **No automated test** — there
is no JS test framework here, and standing one up now is a larger risk
than the bug. Recorded as a known gap, not dressed up as covered.

Also recorded from the 22 Aug attempt: the panel printed `AXON — FAILED`
with the real 429 rather than dressing it as a friendly chat reply. That is
the honesty design holding under a live failure.

**3. Phase 10 reliability: the full demo unattended, twice in a row.**
`scripts/golden_path.py` is the rehearsal. Needs quota.

## Outstanding owner actions

- **Film.** Nothing else in scope is blocked on anyone.
- Decide whether the chat/voice panel is promoted to the live site and
  whether it stars in the demo.
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

**The front door (22 Aug evening)**
- **Chat + voice** (`dba7f5e`). `POST /missions/planned` always did the
  whole job; it just had no interface, so reaching it meant a four-line
  curl with two headers and a JSON file. The owner hit two errors in a row
  doing exactly that, which was the argument for building this.
- **Owner token is typed in and held in a module variable only** — not
  localStorage, not sessionStorage, not a cookie, not the URL. Verified by
  unlocking with a fake token and confirming every storage surface stayed
  empty. It dies with the tab, which is the right trade for something that
  can trip the kill switch.
- Voice is the browser's own SpeechRecognition: no GCP speech service, no
  key, no cost, and it hides itself where unsupported so the demo never
  depends on a microphone.
- The transcript reports BLOCKED as blocked and FAILED as failed. Dressing
  those as friendly chat replies would hide the behaviour being judged.

**Filming (22 Aug evening)**
- `scripts/camera_test.py` — rehearses seven beats, no quota, ~26s.
- `.\demo` launcher. The absolute path wrapped across two lines, sat on
  screen for a whole take, and published the operator's real name to a
  video bound for public YouTube.
- `docs/demo-script.md` corrected twice. **Its opening shot would have
  died on camera at 0:30**: it used a direct `POST /missions`, and
  `/acquire` answers "Mission records no gap" for those. Only a
  `/missions/planned` mission can be acquired against.
- Three takes reviewed frame by frame. Readability went from "fails
  legibility, a digit was transcribed as ?" to "legible without zooming".

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
time the thing actually ran. The CORS bug is the seventh, and it survived
**279** green tests plus a passing fire drill — because the drill drove the
API with curl, and the one thing nobody had done was paste a token into a
browser.

**A test that does not do what the user does proves nothing about what the
user does.** Five CORS tests existed. All five sent simple requests. A
simple request is never preflighted, so none of them could ever have caught
this — the suite was green and blind at the same time.

**When a symptom points at the operator's machine, check what is different
about the machine's SESSION first.** Half an hour went to antivirus and
Windows proxy settings. The actual difference was one field on screen:
`UNLOCKED` in the failing browser, locked in the working one.

**Green CI is not a working repo.** The suite passed for maintainers and
failed for anyone who cloned it, for many commits.

**Three of the six bugs were the same disease:** the model was guessing at
something nobody had shown it — the data shape, the argument names, how to
write a test that does not throw away its own work. The fix each time was
to show it, not to prompt harder.
