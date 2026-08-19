# AION AXON — Build Progress

Status values: `DONE` · `IN PROGRESS` · `BLOCKED` · `NOT STARTED`.
A phase is DONE only with a commit hash AND evidence. Never mark DONE on
intent. Anything unverified is written down as unverified.

| Phase | Status | Commit | Evidence |
|-------|--------|--------|----------|
| 1 — Governed execution loop | DONE | `bed90c7` | `docs/day1-evidence.md`, CI run 32252020824 |
| 2 — Deploy spine | IN PROGRESS | — | — |
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

## Phase 2 — Deploy spine — IN PROGRESS

Target Aug 20. Exit: two live Cloud Run URLs + live e2e pass.

- [x] HTTP API on aion-core (`POST /missions`, `GET /approvals/pending`,
      `POST /approvals/{id}/decide`, `POST /killswitch`) — `app/api.py`
- [x] Missions persisted to Firestore so approval-resume survives a
      Cloud Run instance change
- [x] Dockerfile for aion-core
- [x] aion-sandbox service, zero secrets, logs env proof at startup
- [x] API tests passing offline — 13 passed
- [ ] Deploy aion-core to Cloud Run `asia-south1`
- [ ] Deploy aion-sandbox to Cloud Run `asia-south1`
- [ ] Prove Day-1 approval flow against the LIVE `.run` URL

### Owner console tasks for this phase

Tracked here so they are never lost between sessions.

- [ ] Add gcloud to PATH / authenticate `gcloud auth login`
- [ ] Confirm billing + $150 credits active on `aion-axon-2026`
- [ ] Enable Cloud Run + Artifact Registry + Cloud Build APIs
