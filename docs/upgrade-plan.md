# AION Axon — Upgrade Plan (written 22 Aug 2026)

Nine days to submission (30 Aug), hard deadline 31 Aug 5pm PDT.
Judging: 40% Innovation & Operational Utility · 30% Architectural
Discipline · 30% **Demo & Production Readiness**.

That last 30% is why presentation is not decoration. It is nearly a third
of the score, and it is the third most teams lose.

---

## Tier 1 — Must land before submission

These are the difference between "a working system" and "a submitted
entry". Nothing in Tier 2 or 3 matters if any of these slip.

| # | Item | State | Blocked on |
|---|---|---|---|
| 1 | **Phase 8 fire drill** — the messy workflow as ONE continuous mission | Every ingredient proven separately; never run end to end as one | Gemini quota |
| 2 | **Phase 10 reliability** — full demo, unattended, twice in a row | Not started | Tier 1.1 |
| 3 | **Demo video** — public on YouTube | Not started | Tier 1.2 |
| 4 | **Devpost submission** | Text drafted (`docs/devpost.md`) | Tier 1.3 |

**The single biggest risk to this project is no longer engineering.** It is
spending the last nine days improving a system that is already good enough
to submit, and then submitting late or not at all. Tier 1 is the whole job.

---

## Tier 2 — Presentation: the 3D Holo-Deck (owner mandate, 22 Aug)

**Owner ruling: the Holo-Deck gets a 3D interface, regardless.** Recorded
as a decision, not a proposal.

Two things must be stated plainly alongside it, because recording a
decision honestly includes recording what it costs.

**1. It contradicts a previously locked rule.** `CLAUDE.md` §P9 says:
*"Animate ONLY 3 states (mission working / approval / refusal);
everything else static; 60fps; no WebGL. Every animation = a real
event."* The no-WebGL line was chosen deliberately — an 8GB machine
recording a screen capture is exactly where WebGL drops frames, and a
demo video that stutters reads as an unreliable system. **The owner ruling
is newer and wins**, but the reason behind the old rule does not
disappear, so it becomes a constraint on how the 3D is built rather than
an argument against building it.

**2. The rule that must survive the rebuild: every animation is a real
event.** A 3D scene that idles impressively while nothing is happening is
a screensaver. A 3D scene where a node lights up *because* a real
capability was just acquired is evidence. The current 2D Holo-Deck already
gets this right, and it is the property most worth carrying over.

### How to do it without risking the submission

- **The 2D Holo-Deck stays deployed and stays the fallback.** It is live
  at https://aion-axon-2026.web.app and it works. 3D ships to a preview
  channel first and only replaces the main site once it renders at a
  stable frame rate on *this* machine, during a *screen recording*.
- **Time-box it.** If 3D is not demo-ready by **27 Aug**, the 2D version
  is what gets filmed. That date is not pessimism; it is what leaves
  Phase 10 and the video intact.
- **Test it under recording load, not just in a browser.** The failure
  mode is not "it doesn't work", it is "it works until OBS is also
  running".
- Prefer CSS 3D transforms and SVG depth over a full WebGL scene where
  they get 80% of the effect at 10% of the frame-rate risk. Reach for
  Three.js only for the one hero moment that genuinely needs it.

### Also on the UI, smaller but real

- **Write access.** Approve / Reject / kill switch currently 401, because
  the browser holds no owner token by design. Either add a
  paste-your-token field held in memory only, or accept the demo drives
  writes from the CLI. **Judges clicking a dead Approve button is worse
  than no button.**
- **Rollback button.** The API route exists; the UI never exposed it.
  Rollback is one of the strongest governance beats and it is currently
  invisible.

---

## Tier 3 — Real improvements, deliberately deferred past the freeze

Recorded so they are not lost, and explicitly **not** to be built before
30 Aug. Each is a genuine improvement; none is worth the submission.

- **Search grounding + automated promotion.** Research currently returns
  DEGRADED with zero citations on the free tier. When the \$150 credits
  land (~25 Aug) grounding should work, which would let autonomy
  promotion come from *grounded evidence* rather than human verification.
  That is a materially stronger claim than the one the README makes today
  — but it is quota, not code, and it must not be faked to close.
- **Semantic policy matching.** Guardian matching is lexical. A novel
  phrasing of a prohibited request can miss. It degrades safely (a miss
  means a human is asked, never "anything runs"), which is why this can
  wait.
- **Retry-with-feedback on failed candidates.** One attempt, then
  REJECTED. A repair loop is quota-hungry — rejected for now on cost, not
  on merit.
- **Real authentication.** Owner auth is a bearer token. The honest answer
  is Firebase Auth or IAP. Documented as a limitation rather than
  overstated.
- **Parallel step execution.** Sequential only. Not a blocker for the
  locked demo.
- **`write_brief` recommendations.** It reports findings and states
  plainly when it has no recommendations. Generating them would need a
  model, which would cost the property that makes the brief trustworthy —
  if this is ever built, the generated recommendations must be visibly
  marked as inferred.

---

## The honest summary

The system works. It acquires capabilities under governance, refuses what
it should, produces its deliverable even when the model layer is down, and
has 264 passing tests and a live dashboard.

What remains is **proving it in one continuous run, filming it, and
submitting** — plus making it look as good as it works.

Presentation is worth 30%. It is worth real effort. It is not worth the
submission.
