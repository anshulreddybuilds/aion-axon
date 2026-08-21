# AION AXON — Project Handoff (Claude Code owns the build)

Claude Code is the PRIMARY and SOLE implementation agent through submission.
Do not route work back to ChatGPT. Self-drive the phases below in order.
Stop and ask the owner ONLY for: (a) a click in a Google/GitHub/Devpost web
console, (b) an approval decision, (c) money/credentials, (d) a genuinely
blocking ambiguity.

The owner is non-technical. When you need him: exact copy-paste commands or
numbered click-steps, ONE step at a time, wait for paste-back.

## OWNERSHIP — Session B is dead, Session A owns everything (owner ruling, 22 Aug 2026)

The owner confirmed on 22 Aug 2026 that **Session B is dead and Session A
inherits all of its files.** The former split — Session A owning `app/`,
`tests/`, `sandbox/`, `scripts/` while `README.md` and `docs/` belonged to
Session B — no longer applies. There is ONE session and it owns the whole
repo, including `web/` (the Holo-Deck), `README.md` and `docs/`.

Do not re-impose the old do-not-touch list. If a future prompt still carries
it, this ruling is newer and wins.

## THE MISSION

Win Google's "All Things Agentic" hackathon (Devpost), category **Taskmaster
($20K)**. Deadline Aug 31 5pm PDT; **WE SUBMIT AUG 30**.
Judging: 40% Innovation & Operational Utility · 30% Architectural Discipline
· 30% Demo & Production Readiness.

## THE PRODUCT

AION Axon: a governed, self-evolving background agent. It completes messy
multi-step business workflows. When it lacks a capability, SYNAPSE researches
(Search grounding), generates, sandbox-tests and installs it — ONLY with human
approval. GUARDIAN (deny-by-default) can refuse; a kill switch stops
everything; every change emits evidence to Firestore.

### THE ONE DEMO STORY — "The Monday Business Intelligence Fire Drill"

Owner is a business analyst. One messy Monday request: pull numbers from a
dataset (BigQuery public data), normalize external prices/currency, find
changes/anomalies, produce an executive **Business Action Brief**, then keep
monitoring. Mid-mission the agent hits a gap (FX normalization) → SYNAPSE
acquires the capability under approval → mission completes. Separate beat: an
unsafe capability request ("read credentials from the runtime") is REFUSED
citing policy **G-04**, an override attempt is refused again, kill switch ends
the demo.

**Hierarchy: MISSION RESULT > capability created > capability count.**
The 12→15 counter is supporting evidence only, never the headline.

## HARD RULES (NEVER BREAK)

1. **Runtime = Google only**: Gemini API (`gemini-3.6-flash` primary — NEVER
   `gemini-3.5-pro`, it does not exist; `gemini-3.1-pro` optional for hard
   reasoning), ADK 2.x (already load-bearing), Cloud Run, Firestore, Firebase
   Hosting, Secret Manager, BigQuery. Optional bonus: Gemma as sandbox test
   evaluator, only if under half a day.
2. **FORBIDDEN**: Pub/Sub, A2A implementation, webhooks, Vertex Agent
   Engine/Builder, Veo/Lyria, Compute Engine, anything paid. Free tiers +
   $150 credits only. Cloud Run scale-to-zero except `min-instances=1` during
   video recording only.
3. **NO secrets in code/commits/sandbox ever.** Core gets keys via Secret
   Manager (cloud) or `.env` (local, gitignored). The `aion-sandbox` service
   must verifiably have ZERO credentials.
4. **Every phase ends**: tests pass → commit → push → CI green → END REPORT
   (files changed, commit hash, pytest summary, evidence, anything skipped).
   Never claim without evidence.
5. All submitted code written during the hackathon. Keep the AI-assistant
   disclosure line in README. After submission Aug 30: **FREEZE**.
6. **ExecutionGate remains the ONLY path to any tool execution.** Never bypass
   governance, even in demos.

## PHASES

| # | Phase | Target | Exit criteria |
|---|-------|--------|---------------|
| 2 | Deploy spine | Aug 20 | Two live Cloud Run URLs + live e2e pass |
| 3 | Mission engine | Aug 21 | One real mission end-to-end via live URL |
| 4 | Gap detection | Aug 22 | Gap reliably produces BLOCKED + Evolution Event |
| 5 | Synapse stage 1 | Aug 23 | Candidate generated + tested, citations stored |
| 6 | Synapse stage 2 | Aug 24 | Full candidate pipeline through sandbox |
| 7 | Guardian + HITL | Aug 25 | Acquisition #1 (FX) end-to-end with approval |
| 8 | Fire drill + package v1 | Aug 26 | Messy workflow e2e, ≥1 acquisition, Brief |
| 9 | Holo-Deck UI | Aug 22–27 | Live Firestore listeners, real-event animation |
| 10 | Reliability | Aug 27 | Full demo runs unattended twice in a row |
| 11 | Hardening + video | Aug 28–29 | Video public on YouTube, repo judge-ready |
| 12 | Submit | Aug 30 | Devpost submitted, then FREEZE |

Detail per phase lives in `PROGRESS.md`. Phase 9 (UI) runs parallel where safe.

### Phase specifics worth not re-deriving

- **P2**: Dockerize aion-core with HTTP API (`POST /missions`,
  `GET /approvals/pending`, `POST /approvals/{id}/decide`, `POST /killswitch`).
  Minimal aion-sandbox service, zero secrets, logs env proof at startup. Both
  to Cloud Run `asia-south1`.
- **P3**: Registry as Gemini function declarations, seeded with 12 starter
  capabilities. Implement `web_research` for real with source receipts.
- **P4**: Evolution Event shape = BEFORE → CHANGE → REASON → AFTER.
- **P7**: Policy catalog file, deny-by-default, includes **G-04
  credential-access-prohibited**. Skill Passport per capability:
  NEED → RESEARCH → PROPOSAL → TESTS → RISK → APPROVAL → INSTALL → VERSION →
  ROLLBACK.
- **P8 README order**: what problem → 90-second happy path → architecture →
  how acquisition works → governance → security → reproduce → deploy →
  evidence → limitations → disclosure.
- **P9 palette**: bg `#06090f`, cyan `#37e0d8`, green `#4ade80`, red `#f87171`.
  Animate ONLY 3 states (mission working / approval / refusal); everything
  else static; 60fps; no WebGL. **Every animation = a real event.**
- **P11 video script**: hook "Most agents can execute tools — the problem is
  when the tool they need doesn't exist" → product on screen with LIVE badge +
  5s architecture line + 2-3s console flash → ONE deep acquisition ending in
  the RESULT and Skill Passport → 15s montage caps 14/15 → refusal + override
  + kill switch → evidence ending "AION Axon doesn't just act. It earns
  permission to become more capable." → black screen.

## ENVIRONMENT (verified 19 Aug 2026)

- Repo: `C:\Users\sneha\Desktop\AION-AXON` · GitHub
  `anshulreddybuilds/aion-axon` (PRIVATE) · branch `main`.
  (Account renamed from `webserieswatchdog-dotcom` on 20 Aug 2026. The
  Google/gcloud account is still `webserieswatchdog@gmail.com` — the
  rename was GitHub-only.)
- GCP project `aion-axon-2026`, Firestore Native `asia-south1`, ADC works.
- Owner shell is **PowerShell** — `&&` is not a statement separator, and it
  strips inner double quotes from `python -c`. Write a script file instead of
  fighting the quoting.
- `.venv\Scripts\python.exe` is the interpreter. Docker 29.6.1 installed.
- **gcloud is NOT on PATH.** SDK lives at
  `%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin`.
- Local runs need `AXON_FIRESTORE_MODE="memory"` or they write to REAL
  Firestore.
- `GOOGLE_API_KEY` is session-scoped in the owner's shell, free-tier key.

## ARCHITECTURE NOTES (do not relitigate)

- `AXON_FIRESTORE_MODE=memory` selects `MemoryFirestore` + `MemoryKillSwitch`
  for deterministic local/CI runs. Real Firestore stays the production
  backend and is never replaced by a permanent mock. **Any new module that
  touches Firestore must honour this switch at import time** — that bug cost
  a full red CI streak on Day 1.
- Planner is advisory: produces text, never side effects. A planner failure
  degrades to a `PLANNER_ERROR` observation, never a crash.
- Guardian today is risk-tier based: HIGH → REFUSE, MEDIUM →
  APPROVAL_REQUIRED, LOW → ALLOW. Phase 7 replaces this with the policy
  catalog while keeping the same decision enum.
- CI covers the offline path only. Live Gemini and real-Firestore runs stay
  manual probes, by design.

## DAY 1 — CLOSED, verified (evidence: `docs/day1-evidence.md`, `bed90c7`)

Governance (guardian, approval persistence, kill switch, execution gate),
orchestrator + ADK taskmaster planner, calculator tool, web_research scaffold,
approval-resume e2e, CI green. Gemini verified live on `gemini-3.6-flash`.
Real Firestore write verified (approval `ec2877a1`, workflow `92ab0d13`).
Hackathon eligibility: Gemini PASS, Google framework PASS.
