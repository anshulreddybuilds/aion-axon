# SESSION B — SURFACE & PACKAGE (paste this into Claude Code session B)

---

AION Axon — you are **SESSION B: SURFACE & PACKAGE**.

## Your branch

`feat/holodeck-surface` — already created. Work only there. Never commit
to `main`; the owner is the only merger.

## Files you OWN (edit freely)

- `web/**` — the Holo-Deck UI (create this directory; it does not exist yet)
- `README.md`
- `docs/**` — EXCEPT `docs/firestore-contract.md` (read-only for you) and
  `docs/session-a-prompt.md`
- `firebase.json`, `.firebaserc` — Firebase Hosting config
- Architecture diagram source and demo script

## Files you must NOT touch

- `app/**`, `tests/**`, `sandbox/**`, `scripts/**` — Session A owns all of it
- `Dockerfile`, `requirements.txt`, `.github/workflows/ci.yml`
- `CLAUDE.md`, `PROGRESS.md` — Session A owns these. Keep your own log at
  `docs/session-b-log.md` instead, or you will conflict on every merge.

If you need a backend change, **do not write it** — add it to
`docs/session-b-log.md` under "Asks for Session A" and tell the owner.

## Read before writing code

1. `docs/firestore-contract.md` — **your single source of truth for data
   shapes.** Every field the UI renders is defined there.
2. `CLAUDE.md` — hard rules and environment
3. The Notion master plan §5.1 (Holo-Deck spec) and §9 (video script), and
   Amendment 7 (the autonomy gauge panel) via the Notion connection

## What you ship, in priority order

**P0 — Holo-Deck UI** (Notion §5.1, plan Days 4–9)
- Vite + React + Tailwind + Framer Motion, static build → Firebase Hosting
- **Palette locked, set before any component:** bg `#06090f` · cyan
  `#37e0d8` · green `#4ade80` · red `#f87171`
- **Live Firestore listeners. No polling.**
- Hero visual: the radial loop — central AXON orb ringed by
  Understand / Execute / Learn / Govern (Amendment 8 replaced the
  six-node Synapse Theater with this; it tells the same story with less
  build risk)
- Panels: Mission Status · Evidence Engine · Autonomy Ledger ·
  Capability Registry · Recent Events (audit feed) · approval card ·
  "WHY THIS SKILL EXISTS" (Skill Passport) · kill switch
- Persistent **● LIVE — Cloud Run / aion-core** badge (rulebook row 6
  requires the video to prove the backend runs on Google Cloud)

**Animation rules — these are hard**
- Animate ONLY three states: mission working · approval · refusal.
  Everything else static.
- **Every animation must narrate a REAL event.** No decoration-only motion.
- Must hold 60fps on the demo laptop. **No WebGL, no 3D** — the video is
  recorded and jank is visible.
- The red refusal flash (`#f87171`) is the moment judges are told to
  remember. It is missing from the original mockup. Add it.
- For the RECORDED portion keep only: central loop + Mission Status +
  Evidence Engine + Autonomy Ledger. Other panels stay in the app for
  judges to click, but the video must not linger on them.

**P0 — README** (rulebook row 8, reproducibility is explicitly judged)
Order matters: what problem → 90-second happy path → architecture → how
acquisition works → governance → security → reproduce → deploy →
evidence → limitations → **AI-assistant disclosure line**.

**P1 — Architecture diagram** (rulebook row 9)
Gemini → ADK → Cloud Run ×2 → Firestore → Holo-Deck, with an explicit
**TRUST BOUNDARY** drawn around the sandbox. That boundary is the
architectural story; do not omit it.

**P1 — Devpost submission text** (rulebook row 10)
Features, all Google tech used, data sources, findings & learnings.
The learnings section must be honest about what is IMPLEMENTED vs
PARTIAL — documentation honesty is explicitly scored.

**P2 — Demo shot list** for the 4-minute video, per Notion §9.

## Critical: build against empty collections

`capabilities/` and `evolution_events/` **do not exist yet** — Session A
ships them. Build those panels now; they will render empty until then.

**An empty panel is correct behaviour, not a bug.** Do not fake data to
make a panel look alive. Rulebook row 16 requires the product to run
consistently as depicted, and a judge who spots invented numbers has
found a reason to stop trusting everything else on screen.

Every number on screen must come from live Firestore, or it does not go
on screen.

## Backend facts you need

- Core API: `https://aion-core-638298765129.asia-south1.run.app`
- Sandbox: `https://aion-sandbox-638298765129.asia-south1.run.app`
- GCP project `aion-axon-2026`, Firestore Native, `asia-south1`
- **Cloud Run returns HTTP 411 on a POST with no body — always send one,
  even `{}`.** This has already broken a call once.
- Firestore web SDK needs the project's web API config. Ask the owner to
  add a Firebase web app in the console; do not guess the config values.

## Hard rules

1. Public name is "AION Axon" — never bare "Axon".
2. Do NOT touch: Vertex AI / Agent Engine / Agent Builder, Veo/Imagen,
   Live API voice, Maps, Compute Engine, Pub/Sub.
3. **No secrets in the web app.** A Firebase web config is public by
   design; a Gemini API key is NOT and must never reach the browser.
4. Every phase ends: build passes → commit → push → report with the
   commit hash. Never claim done without evidence.

## Report format at the end of every phase

Files changed · commit hash · build output · screenshot or live URL ·
anything skipped and why · "Asks for Session A" if you were blocked.
