# AION AXON — Build Progress

Status values: `DONE` · `IN PROGRESS` · `BLOCKED` · `NOT STARTED`.
A phase is DONE only with a commit hash AND evidence. Never mark DONE on
intent. Anything unverified is written down as unverified.

| Phase | Status | Commit | Evidence |
|-------|--------|--------|----------|
| 1 — Governed execution loop | DONE | `bed90c7` | `docs/day1-evidence.md`, CI run 32252020824 |
| 2 — Deploy spine | DONE | `f580ef1` | Two live Cloud Run URLs, live approval-resume, `docs/phase2-evidence.md` |
| 3 — Mission engine | NOT STARTED | — | — |
| 4 — Gap detection | NOT STARTED | — | — |
| 5 — Synapse stage 1 | NOT STARTED | — | — |
| 6 — Synapse stage 2 | NOT STARTED | — | — |
| 7 — Guardian + HITL | NOT STARTED | — | — |
| 8 — Fire drill + package v1 | NOT STARTED | — | — |
| 9 — Holo-Deck UI | NOT STARTED | — | — |
| 10 — Reliability | NOT STARTED | — | — |
| 11 — Hardening + video | NOT STARTED | — | — |
| 12 — Submit | NOT STARTED | — | — |

---

## Phase 1 — Governed execution loop — DONE

Commit `bed90c7`. CI run `32252020824` green.

- Governance: guardian, approval persistence, kill switch, execution gate.
- Orchestrator + ADK taskmaster planner driving `gemini-3.6-flash`.
- Calculator tool, web_research scaffold, approval-resume e2e test.
- Gemini verified live. Real Firestore write verified (approval `ec2877a1`).
- Eligibility: Gemini PASS, Google framework PASS.

Full detail: `docs/day1-evidence.md`.

## Phase 2 — Deploy spine — DONE (19 Aug, a day early)

Exit criteria met: two live Cloud Run URLs + live e2e pass.

- **aion-core**: https://aion-core-638298765129.asia-south1.run.app
- **aion-sandbox**: https://aion-sandbox-638298765129.asia-south1.run.app

Evidence: `docs/phase2-evidence.md`.

- [x] HTTP API on aion-core (`POST /missions`, `GET /approvals/pending`,
      `POST /approvals/{id}/decide`, `POST /killswitch`) — `app/api.py`
- [x] Missions persisted to Firestore so approval-resume survives a
      Cloud Run instance change
- [x] Dockerfile for aion-core
- [x] aion-sandbox service, zero secrets, logs env proof at startup
- [x] API tests passing offline — 13 passed
- [x] Deploy aion-core to Cloud Run `asia-south1`
- [x] Deploy aion-sandbox to Cloud Run `asia-south1`
- [x] Prove Day-1 approval flow against the LIVE `.run` URL

### Owner console tasks — all complete

- [x] gcloud on PATH, authed as webserieswatchdog@gmail.com
- [x] APIs enabled: run, cloudbuild, artifactregistry, firestore, secretmanager
- [x] Gemini key stored in Secret Manager as `gemini-api-key`

## Phase 3 — Mission engine — NEXT

Target Aug 21. Exit: one real mission end-to-end via the live URL.

- [x] Mission intake -> structured plan STEPS parsed into executable steps
      (`MissionPlan` schema + ADK `output_schema`)
- [x] Registry exposed as Gemini function declarations
- [x] Seed 12 starter capabilities (2 implemented, 10 declared)
- [x] Implement `web_research` for real, with source receipts
      (Google Search grounding)
- [ ] Run a live web fetch through the approval loop — needs deploy
- [ ] Live planned mission via the Cloud Run URL — needs deploy
