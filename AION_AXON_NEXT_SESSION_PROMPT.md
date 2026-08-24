# Paste this into a brand-new Claude Code session, in the AION AXON repo

You are continuing AION AXON (`anshulreddybuilds/aion-axon`,
branch `feat/beastmode-core`) from a prior session's checkpoint.

**Step 1 — read the checkpoint, not the old conversation.**
Read `AION_AXON_HANDOFF.md` and `AION_AXON_STATE.json` in full before
doing anything else. Do NOT try to reconstruct project history from git
log or from asking me questions — the handoff is deliberately complete.

**Step 2 — verify minimally, then trust the checkpoint.**
Run only:
```bash
git status --short && git rev-parse HEAD && git fetch origin && git rev-parse origin/feat/beastmode-core
```
Compare the result to `AION_AXON_STATE.json`'s `head`/`origin_head`/`clean`
fields.

- **If they match**: the entire production state, test baseline, and
  security posture described in the handoff is still accurate. Do NOT
  re-run the full backend test suite, the fixture suite, a frontend
  build, or any production smoke test "just to check" — that work was
  already done and verified at this exact commit. Go straight to
  deciding the next action.
- **If they don't match**: something changed outside this handoff's
  knowledge. Investigate the actual diff (`git log <handoff-head>..HEAD`)
  before trusting anything else in the handoff — treat the delta as
  unverified, not the whole document.

**Step 3 — do not repeat completed work.**
Phases 19-29 are done and LIVE VERIFIED in production as of the
checkpoint HEAD. Do not redo: the AST/security bypass audit, the ledger
forensic suite, the owner-auth endpoint sweep, the mission-pipeline code
trace, the approval cross-binding proof, or the deploy+smoke-test cycle.
`AION_AXON_HANDOFF.md` sections L and M list exactly what's done and
what must not be repeated. `AION_AXON_PHASE_INDEX.md` gives a one-line
orientation per phase if you need to find which commit did what.

**Step 4 — identify the actual next action, don't invent a new phase.**
`AION_AXON_HANDOFF.md` section O has the current recommendation. In
short: the highest-leverage remaining action is the owner personally
executing the first real production mission — that is a human action,
not something for you to do. If the owner isn't ready for that, the
only other open item is a low-priority stale-number fix (section K.6/N.2).
Do not self-generate a large new "Phase 30" of speculative hardening
unless the owner directs it.

**Step 5 — before ANY push or deploy, do a release-safety review.**
Even though the checkpoint state is trusted, any NEW commit still needs:
`git diff`, secret/credential grep, and a real (not assumed) test run
before it gets pushed or deployed. Never skip this because "the last
session already verified everything" — that verification covered the
old commits, not new ones.

**Step 6 — the real-mission boundary is absolute and unchanged.**
Never read, print, request, or use the real owner token. Never click
RUN MISSION, approve/reject a real capability, install a real
capability, or mutate production Firestore/ledger through the real
mission path. If Mission Readiness says READY, that means the SYSTEM is
ready — it is never permission for you to execute the mission yourself.
The owner does this personally, in their own browser, with their own
token. See `AION_AXON_HANDOFF.md` section P for the exact click-path to
tell the owner if they ask.

**Working discipline for this session:**
1. Read handoff → 2. check git state → 3. if no drift, skip
re-verification → 4. pick the next real action from section O → 5.
release-safety review before any push/deploy → 6. never cross the
mission boundary.

Keep responses grounded in the checkpoint's facts. If something in the
handoff turns out to be wrong when you check it, say so plainly and
correct your own document rather than silently trusting stale data.
