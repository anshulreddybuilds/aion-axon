# Paste this into a brand-new Claude Code session (or hand to any other AI), in the AION AXON repo

You are continuing or testing AION AXON (`anshulreddybuilds/aion-axon`).

**The authoritative branch is `feat/beastmode-core-oagiwb-weku3h`.**
Not `feat/beastmode-core` and not `feat/beastmode-core-oagiwb` — both are
older, abandoned lines. This was determined from git history (commit
ancestry + timestamps + CI results), not assumed; if in doubt, re-derive
it the same way: check which branch's tip is a strict descendant of the
others and has the most recent, real (non-junk) commits, and check
GitHub Actions for which branch has an actually green run at its current
tip.

**Step 1 — verify branch/HEAD before trusting ANY other doc in this repo.**
```bash
git fetch origin
git log --oneline -1 origin/feat/beastmode-core-oagiwb-weku3h
```
This repo also contains `AION_AXON_HANDOFF.md`, `AION_AXON_STATE.json`,
and `AION_AXON_PHASE_INDEX.md` — these are a checkpoint system from an
**earlier, now-superseded branch** (`feat/beastmode-core`, an old HEAD)
and are STALE. Do not trust their branch name, HEAD hash, or "current
state" claims without independently re-verifying against git. They may
still be useful for early project history/architecture rationale, but
not for "what's the current state" questions.

**Step 2 — for CURRENT, accurate state, read these instead:**
- `AION_AXON_CONTINUATION_HANDOFF.md` — chronological engineering log,
  newest update at the top, actively maintained through the current HEAD.
- `AION_AXON_BUG_AND_PROBLEM_REGISTER.md` — every real bug found across
  this project's life, root cause, fix, and regression-test proof.
  Newest (highest BUG-NNN) at the top.
- `README.md` — architecture, threat model, honest-status section.

**Step 3 — do not repeat completed work.**
The governed mission pipeline (planner -> capability reuse or SYNAPSE
acquisition -> Guardian -> AST safety screen -> sandbox -> evaluator ->
human approval -> install -> resume), the graphical mission builder
(`/v5`), voice integration (mechanically verified via simulated Web
Speech API), and CI (genuinely green, including real Firestore-emulator
concurrency tests) are all built and verified as of the current HEAD.
Read `AION_AXON_CONTINUATION_HANDOFF.md`'s most recent entries before
re-auditing anything that's already been through a hardening pass.

**Step 4 — known open items, as of this file's own last update:**
- Vertex AI + ADC support was just added (replacing API-key-only auth)
  and is offline-verified only — not yet confirmed against a real live
  Gemini call. This is the actively open item.
- Production has never been deployed — no Claude session has ever had
  deploy credentials; this is owner-only.
- No live end-to-end rehearsal with a real deployed backend exists yet.
- Physical microphone has never been tested (only simulated).

**Step 5 — the real-mission boundary is absolute.**
Never read, print, request, or use the real owner token. Never click
RUN MISSION, approve/reject a real capability, install a real
capability, or mutate production Firestore/ledger through the real
mission path. That is the owner's action, in their own browser, with
their own token.

**Step 6 — before any push, do a release-safety review.**
`git status`, `git diff`, a secret/credential grep, and a real test run
(`AXON_FIRESTORE_MODE=memory pytest -q` — expect 572 passed, 4 skipped
as of this file's last update; re-verify the number if it's been a
while) before pushing anything.

Keep responses grounded in verified facts, not this file's own claims
taken on faith — if something here turns out wrong when you check it,
say so and correct it, the same discipline this file itself is asking
you to apply to the OLDER handoff docs it supersedes.
