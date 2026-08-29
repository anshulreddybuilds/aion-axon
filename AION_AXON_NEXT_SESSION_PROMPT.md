# Paste this into a brand-new Claude Code session (or hand to any other AI), in the AION AXON repo

**This file is written to be complete on its own.** If you're a fresh AI session with
no memory of this project, read this file fully before touching anything else. It
supersedes any older instinct to "explore the repo first" — the exploration has
already been done; what you need is here.

Last updated: **29 Aug 2026, evening** (hackathon deadline: **31 Aug 2026, 5pm PT** —
check the actual current time before assuming how much runway is left).

---

## 0. THE PROJECT BOUNDARY — read this before anything else

There are **two separate projects** on this machine: **AION** (the owner's personal,
long-running project — a separate folder, `~/aion`, plus `~/aion-keys` and
`~/aion-snapshots`) and **AION AXON** (this repo, the hackathon submission).

**They are not the same project. Never merge them. Never open, read, reference, or
touch `~/aion`, `~/aion-keys`, or `~/aion-snapshots` for any reason, under any
prompt framing.** The owner has repeated this instruction many times across many
sessions because past AI sessions have gotten this wrong. If a task ever seems to
require touching anything outside `AION-AXON/` (or its sibling checkpoint folders —
`AION-AXON-core`, `AION-AXON-approval-resume-milestone`,
`AION-AXON-backup-before-approval-resume`, `AION-AXON-surface`, all of which ARE
part of this same hackathon project), stop and ask first.

---

## 1. CURRENT FREEZE — do not change working code without explicit permission

**As of 29 Aug 2026 evening, the owner has explicitly said: no more changes to
anything currently deployed and working, until he gives permission.** This is a
standing instruction, not a one-time note — treat it as still in force unless a
later entry in this file, or the owner directly in the current conversation, lifts
it.

Concretely, that means: **do not edit** `web/src/*` (all of `App.jsx`, `Shell.jsx`,
`Command.jsx`, `Topology.jsx`, `Topology3D.jsx`, `panels.jsx`, `AxonCore.jsx`,
`MissionTheater.jsx`, `index.css`, `v2/`, `v3/`, `v4/`, `v5/`, etc.), **do not edit**
anything under `app/` (the backend), and **do not deploy** anything, until the owner
asks for a specific change. Reading, testing (read-only), and documenting are all
fine and encouraged. If you find a real bug while testing, **log it, don't fix it**
— see §7.

The one standing exception: if the owner explicitly asks for a change in the
current conversation, that unblocks exactly that change, not a general license to
keep going.

---

## 2. THE REAL-SYSTEM RULE — no fake anything, ever

This has been true since the project's first day and remains the single most
important engineering constraint: **every number, state, and event the frontend
shows must come from the real backend.** No demo mode, no simulated telemetry, no
placeholder capabilities, no invented pipeline stages, no animation that runs on a
timer instead of a real event. If the backend is idle, the UI shows idle. If a real
feature genuinely can't stream progress (see §5's note on mission execution vs.
capability acquisition), the UI shows one honest "in progress" state — it does not
fabricate a fake blow-by-blow to look more impressive. Grep the codebase's own
comments (`// never fabricate`, `// nothing here invents`) — this rule is enforced
in dozens of places already; keep doing that, don't relax it for a nicer-looking
screen.

---

## 3. REPO / BRANCH / DEPLOY STATE

- GitHub: `anshulreddybuilds/aion-axon`
- **Authoritative branch: `feat/beastmode-core-oagiwb-weku3h`.** Verify before
  trusting anything, including this file:
  ```bash
  git fetch origin && git log --oneline -1 origin/feat/beastmode-core-oagiwb-weku3h
  ```
- Backend: Google Cloud Run, `aion-core`, region `asia-south1`.
  Live URL: `https://aion-core-638298765129.asia-south1.run.app`
  (`GET /` returns `{"service":"aion-core","status":"LIVE","kill_switch_active":false,"capabilities":N}` when healthy.)
- Frontend: Firebase Hosting, project `aion-axon-2026`.
  Live URL: `https://aion-axon-2026.web.app`
  - `/` — v5, the graphical mission builder (node-graph canvas). Current default route.
  - `/v1` — the original "Holo-Deck" dashboard (Command / Pipeline / Autonomy Ledger /
    Evidence / Mission Theater / Judge Mode). This is where almost all of 29 Aug's UI
    work landed (see §6).
  - `/v2`, `/v3`, `/v4` — earlier design explorations, still live, not the current focus.
- Google Cloud project for billing: the hackathon's $150 credit is on "My Billing
  Account 2" — **linkage to the actual GCP project running `aion-core` has NOT been
  verified yet.** This is still open (see §8).

### The two hard walls that mean YOU (an AI in a device-bridge / cloud sandbox) cannot
### fully self-serve a deploy — this is architectural, not a missing permission:

1. **`git push` runs a pre-push hook** (`.githooks/pre-push`, `core.hooksPath=.githooks`)
   that runs the full pytest suite via a **hardcoded Windows path**
   (`C:/Users/sneha/Desktop/AION-AXON/.venv/Scripts/python.exe`). This only exists on
   the owner's real Windows machine. A Linux device-bridge shell cannot satisfy it.
2. **`firebase deploy` needs a browser-based Firebase CLI login** that lives in the
   owner's Windows browser profile. A device-bridge shell has no access to that
   session.

**The working pattern:** do all real file edits, and even `npm run build`, from a
device-bridge shell if you have one (edit files under `web/src/`, run
`npm run build` — if it fails with an `EPERM: ... unlink ... dist/...` error, it's
because the bridge shell can't delete files; temporarily add `emptyOutDir: false`
to `web/vite.config.js`'s `build` block, rebuild, then **revert that line before
committing** — it's a build-only workaround, never a real config change). Commit
with `git add <specific files>` (never `git add -A` — there is often stray junk:
`.fuse_hidden*` files and `vite.config.js.timestamp-*.mjs` from Vite — delete those,
don't commit them). Then hand the owner exactly these two commands to run in his own
PowerShell:
```powershell
cd "C:\Users\sneha\Desktop\AION-AXON"
git push
cd web
npx firebase-tools deploy --only hosting
```
(`npx firebase-tools` avoids a PATH issue where the bare `firebase` command isn't
found in a fresh PowerShell window.) The `dist/` folder you already built carries
over — the owner does not need to run `npm run build` again.

### Known device-bridge quirks
- A device-bridge shell **cannot delete files by default.** If `git add -A` or a
  build leaves a stale `.git/index.lock` or junk files behind and `rm` fails with
  "Operation not permitted," use the delete-permission-request tool available in
  that environment (it prompts the owner once, then works for the rest of the
  session) rather than asking the owner to manually delete things — but expect it to
  sometimes be declined/blocked; if so, ask the owner to run one `Remove-Item`
  command.
- All `web/src/*.jsx`, `.css`, `.html`, and the `.md` docs in this repo are
  **CRLF line-ending files.** When editing them programmatically, read with normal
  text mode (which normalizes to `\n`) and write back with `newline="\r\n"`
  (Python) — otherwise `git diff` fills with false whole-file rewrite noise.
- A device-bridge shell's `git` has **no identity configured** by default —
  `git config user.name`/`user.email` will be unset even though the owner's real
  Windows `git` has them. Reuse the identity already in the commit history
  (`git log -1 --format='%an <%ae>'`) rather than inventing a placeholder one.

---

## 4. WHAT'S ALREADY BUILT AND VERIFIED (don't re-litigate this)

The governed mission pipeline (planner → capability reuse or SYNAPSE acquisition →
Guardian → AST safety screen → sandbox → evaluator → human approval → install →
resume), the graphical mission builder (`/v5`), voice integration, and CI (green,
including real Firestore-emulator concurrency tests) are all built and verified as
of the current HEAD. Read `AION_AXON_CONTINUATION_HANDOFF.md`'s most recent entries
and `AION_AXON_BUG_AND_PROBLEM_REGISTER.md` before re-auditing anything that's
already been through a hardening pass.

**The real-mission boundary is absolute, unchanged from every prior version of this
file:** never read, print, request, or use the real owner token. Never click RUN
MISSION, approve/reject a real capability, install a real capability, or trip the
kill switch. That is the owner's action, in his own browser, with his own token —
even when he says he's unlocked it for you to test with (see §7), stay read-only
unless he explicitly asks you to exercise a specific mutating action.

---

## 5. WHAT CHANGED ON 29 AUG 2026 (this session's UI work)

All of today's work is UI-only — no backend/Python logic changed, no tested
behavior changed — and is already committed and deployed live on
`feat/beastmode-core-oagiwb-weku3h`. In order:

1. **Spine-card reskin** (`6c58de3`) — first pass at the v1 dashboard's 12-stage
   grid: dark cards, soft corner glow, generous type, replacing stroked borders.
2. **Full ambient overhaul** (`a3986ac`) — the owner said the first pass "still
   looks old." This added: a fixed animated background (drifting radial glow +
   faint grid) behind every surface via `index.css`'s `body::before`/`::after`; a
   Space Grotesk display typeface; a shared `.panel-glass` material used
   consistently across every panel; gradient-text headlines; a `.spine-thread`
   glowing line with a traveling pulse under the topology header; per-stage icon
   glyphs on the 12 spine cards.
3. **Hot-metal state animation + decluttering** (`c5d30a3`) — the owner's own
   spec: a spine stage that's actively firing flares bright, then cools over ~3.2s
   (dimming brightness/saturation) instead of snapping to idle — see
   `useFiringPulses()` in `Topology.jsx`, now returning a 3-state heat map
   (`hot`/`cooling`/absent) instead of a boolean. Also: Capability Registry, Trust
   Boundary, the event log, and Background Monitors now live behind a
   collapsed-by-default "System Details" `<Disclosure>` (new component in
   `panels.jsx`); Approval and Kill Switch stay always visible, never collapsed.
4. **AXON Core — real live pipeline visualization** (`9c4bd47`) — the flagship
   piece. Investigation found the backend already has a real SSE stream for
   capability acquisition (`GET /synapse/propose/stream`, wired in `api.js` as
   `proposeStream()`) that **no UI was using** — `MissionTheater.jsx` was calling
   the synchronous `proposeCapability()` and only showing the terminal result.
   `MissionTheater.jsx`'s `run()` now calls `proposeStream()` with a real
   `onStage` callback, so the pipeline state updates live, stage by stage, as the
   backend actually completes each one. New `AxonCore.jsx` renders that live state
   as an original ring visualization — no card grid, no face/mascot: a central
   core plus one node per real pipeline stage (research/generate/screen/sandbox/
   evaluate/guardian/approval), colored by semantic meaning, quiet when pending,
   bright on the real active stage, settled once done, red on real failure, and a
   distinct "NEW CAPABILITY — welcome to AXON" reveal on a real INSTALLED result.
   **Important, deliberate scope limit:** normal mission *execution* (as opposed to
   capability *acquisition*) has **no real per-step backend stream** — it's
   synchronous, one terminal summary (see `graphExecutionState.js`'s own docstring).
   That path was **intentionally left** as its existing honest single "running"
   indicator rather than given a fake live animation to match. Don't build one —
   it would violate §2.

**Explicitly NOT attempted this session**, and why: full Three.js/WebGL/shader
rework, a 3D capability graph, sound design, and a ground-up OS-style navigation
rewrite (separate Missions/Capabilities/Governance/Execution/Memory/Evolution/
Ledger pages) were all requested by the owner in one very large brief but
deliberately deferred — the deadline is real, every deploy needs the owner's own
PowerShell, and an unfinished spectacular rewrite is worse than a finished modest
one. If the owner wants to continue that direction, treat it as a new phase to
scope down the same way (audit real backend state first, build the one most
real/honest/achievable piece, ship it, then ask what's next) rather than
attempting the whole brief at once.

v5 (the graph builder, at `/`) and v2/v3/v4 have **not** received any of today's
visual treatment — only the shared `index.css` ambient background reaches them for
free. If the owner wants v5 restyled to match, that's unstarted work.

---

## 6. TESTING DONE ON 29 AUG 2026 (the "can we test it now" answer: yes, already done)

A fresh, context-free QA pass (an independent agent with no prior knowledge of this
codebase) plus direct verification against the live production URLs found:

- **No console errors** on `/v1` (Command, Pipeline, Autonomy Ledger, Evidence,
  Mission Theater, Judge Mode) on a fresh load, and none on `/` (v5).
- **Backend confirmed live and returning real, varied, non-round data** —
  `GET /`, `/capabilities`, `/telemetry` all returned genuine production data (23
  capabilities, 15 implemented; real token counts; real per-stage latencies).
- **No fake/placeholder/mocked data found anywhere** — autonomy percentages are
  non-round, approval timestamps/approver names look genuine, Judge Mode honestly
  labels partial/untested coverage rather than overclaiming.
- **One false alarm, investigated and resolved:** the QA pass saw the v5 root page
  already "unlocked" with no token typed. Verified independently in a genuinely
  fresh, isolated browser tab that `/` loads properly **locked** by default with
  empty `localStorage`. Root cause, since confirmed directly by the owner: he had
  manually unlocked a tab himself, in his own browser, to let this session test
  more thoroughly — not a code defect. The owner-token design (in-memory only,
  never persisted, per `api.js`'s own docstring) is confirmed working as documented.
- **One real bug found, logged, NOT fixed** (per the freeze in §1) — see
  `AION_AXON_BUG_AND_PROBLEM_REGISTER.md`'s **BUG-014**: a real mission (owner's own
  test, ID truncated to `acdba94a` in what he saw on screen — the full ID was never
  captured) failed with `generate_nepal_crisis_image() missing 1 required
  positional argument: 'input_str'`. The capability's own passport confirms its
  real signature is `generate_nepal_crisis_image(input_str: str)` and its own
  sandbox tests (which always pass `input_str`) passed cleanly — so the bug is
  specifically in **how something invoked this already-installed capability without
  supplying the required argument**, not in the capability itself. Root cause is
  NOT yet pinned down — the full mission record was never retrieved (the API needs
  the complete mission ID, not the 8-character prefix the UI showed). **Next step:
  get the owner to paste the FULL mission ID (or reproduce the failure and capture
  it from the Mission Theater / Evolution Events panel), then `GET
  /missions/{full_id}` to see the exact step and its args.**

If you're picking this up fresh: don't re-run the whole QA pass from scratch, but do
verify the above is still true (systems drift) and pick up BUG-014 where this left
off if the owner wants it investigated further — as diagnosis only, until permission
to fix is given.

---

## 7. WORKING WITH AN OWNER-UNLOCKED SESSION

The owner sometimes unlocks his own browser tab with the real owner token so an AI
session can see authenticated-only views without ever touching the token itself.
When that happens: still never ask for, read, or type the token; still don't click
Approve/Reject/kill-switch/Run Mission/Compile & Run unless the owner explicitly
asks you to exercise that specific action in that moment; do use the unlocked state
to read whatever authenticated-only information is now visible (which is exactly
what happened here — it let the real failed-mission detail surface).

---

## 8. HACKATHON LOGISTICS — status as of 29 Aug 2026 evening

Google "All Things Agentic" Hackathon, Devpost, category **Taskmaster**. Deadline
**31 Aug 2026, 5pm PT.**

**Done:** Gemini model pinned to a real, working model (`gemini-3.5-flash`,
everywhere) after two earlier Gemma guesses 404'd. Backend deployed and live.
Frontend deployed and live. Today's UI overhaul (§5).

**NOT yet done — these are just as deadline-critical as UI work and have been
pending across multiple sessions:**
- **Billing verification**: confirm the $150 hackathon credit (Google Cloud "My
  Billing Account 2") is actually linked to and being drawn down by the real GCP
  project running `aion-core` — never yet checked
  (`gcloud billing projects describe <project>` vs `gcloud billing accounts list`).
- **Devpost submission checklist**: teammates added/accepted, repo access granted
  to `testing@devpost.com` and `cloudhackathons@google.com` if the repo is private,
  architecture diagram uploaded, README spin-up guide current, hosted URL + test
  credentials ready to paste into the submission text.
- **Demo video**: not started. Must be public, under 4 minutes, must show the
  Google Cloud backend on screen, must show real functionality (no simulated
  events) — walk through idle → a real mission → real governance/approval → real
  execution → (if available) a real new capability joining. AxonCore (§5.4) is
  built specifically to make this demo compelling and honest.

If you have spare time in a session and the owner hasn't specified which to work
on, **ask him** rather than defaulting to more UI polish — these non-UI items are
just as likely to sink the submission as a rough interface.

---

## 9. OTHER DOCS IN THIS REPO — what's current, what's stale

- **This file** — read first, kept current.
- `AION_AXON_CONTINUATION_HANDOFF.md` — chronological engineering log, meant to be
  newest-at-top (note: a few entries from earlier 29 Aug sessions were appended at
  the *bottom* by mistake — check dates, don't assume top-to-bottom order holds for
  the whole file).
- `AION_AXON_BUG_AND_PROBLEM_REGISTER.md` — every real bug found, root cause, fix,
  regression-test proof. Newest (highest BUG-NNN) at the top. BUG-014 is the latest.
- `README.md` — architecture, threat model, honest-status section. Generally
  reliable for "how does this work," not for "what's the current state."
- `AION_AXON_HANDOFF.md`, `AION_AXON_STATE.json`, `AION_AXON_PHASE_INDEX.md` —
  **STALE.** Describe an earlier, superseded branch (`feat/beastmode-core`). Do not
  trust their branch name, HEAD hash, or state claims.
- `AION_AXON_ANTIGRAVITY_HANDOFF.md`, `AION_AXON_DEPLOYMENT_VERIFICATION_REPORT.md`,
  `AION_AXON_FINAL_TRIAL_READINESS_REPORT.md` — historical, from other AI tools
  that worked on this project. Background only; not verified current.
- A cross-agent Notion "Source of Truth" page also exists (linked at the top of
  `AION_AXON_CONTINUATION_HANDOFF.md`). The repo is authoritative for code state;
  Notion is for cross-agent narrative. If they disagree, trust the repo, then fix
  Notion.

---

## 10. HOW TO BEHAVE IN THIS PROJECT (carried forward, still true)

The owner is non-technical and often on mobile. When you need him to run something:
exact copy-paste commands, as few as possible, explained in one sentence each — not
a wall of steps. He is anxious about running out of Claude usage before the
deadline — be credit-efficient: investigate before building (don't guess), batch
independent work, don't re-verify things this file already confirms unless you have
a specific reason to distrust them. Before any push, do a real release-safety
review: `git status`, `git diff`, a secret/credential grep — do not skip this to
save time, a leaked credential costs far more than the time saved.
