# SESSION A — CORE INTELLIGENCE (paste this into Claude Code session A)

---

AION Axon — you are **SESSION A: CORE INTELLIGENCE**.

## Your branch

`feat/core-intelligence` — already created. Work only there. Never commit
to `main`; the owner is the only merger.

## Files you OWN (edit freely)

- `app/**` — all application code
- `tests/**`
- `sandbox/**`
- `scripts/**`
- `requirements.txt`, `Dockerfile`, `.dockerignore`
- `CLAUDE.md`, `PROGRESS.md` — you are the only session that edits these

## Files you must NOT touch

- `web/**` — Session B owns the Holo-Deck UI
- `README.md`, `docs/**` — Session B owns docs and packaging
  - **Exception:** you may edit `docs/firestore-contract.md`, but ONLY to
    ADD fields, and you must say so in your report so Session B knows.
    Never rename or remove a field there — the UI reads it and a rename
    fails silently as a blank panel.

If you think you need a file outside your scope: stop and flag it. Do not
edit it.

## Read before writing code

1. `CLAUDE.md` — project handoff, hard rules, environment
2. `PROGRESS.md` — what is actually done, with commit hashes
3. `docs/firestore-contract.md` — the interface you must honour
4. `docs/day1-evidence.md`, `docs/phase2-evidence.md` — verified evidence
5. The Notion master plan (Amendments 7/8/9 and §§2, 3, 9) via the Notion
   connection — authoritative over anything you remember

## What you ship, in priority order

**P0 — Synapse acquisition loop** (Notion §3 demo moments 1–3, plan Days 4–7)
- gap detected (already works: mission goes BLOCKED with `blocked_on`)
- RESEARCH via Google Search grounding, citations stored
- generate candidate capability code
- stage-1 test via Gemini code execution
- stage-2 test in the deployed `aion-sandbox` service
- Guardian screen → human approval → install → register
- emit an Evolution Event (BEFORE → CHANGE → REASON → AFTER)

**P0 — Guardian policy catalog** (plan Day 7)
- deny-by-default policy file with citable IDs
- **G-04 credential-access-prohibited** is required by the locked demo:
  "read credentials from the runtime" must be REFUSED **citing G-04**, and
  an override attempt must be refused AGAIN
- keep the existing `Decision` enum; this replaces the risk-tier logic, it
  does not replace the gate

**P0 — Skill Passport**
NEED → RESEARCH → PROPOSAL → TESTS → RISK → APPROVAL → INSTALL → VERSION
→ ROLLBACK, per acquired capability, written to `evolution_events`.

**P1 — Amendment 7 autonomy** (~2 days, only after the above works)
- Evidence Engine: ONE ground-truth check, Research capability ONLY
- Autonomy Ledger: `autonomy_pct`, `success_rate`, `intervention_rate` as
  new fields on `capabilities/{id}` — extend, do not create a new collection
- Promotion/demotion: verified success → +Δ; reality mismatch → −Δ;
  threshold triggers Guardian "human verification required"

**P1 — the mission's actual product**
- `write_brief` capability → the rendered **Business Action Brief**
- BigQuery public-dataset capability (acquisition #2)
- background monitor capability (acquisition #3)

## Hard rules

1. Public name is "AION Axon" — never bare "Axon".
2. Gemini `gemini-3.6-flash` by default. `gemini-3.1-pro` only if a step
   provably needs it. **"Gemini 3.5 Pro" does not exist** — never write it.
3. Do NOT touch: Vertex AI / Agent Engine / Agent Builder, Veo/Imagen,
   Live API voice, Maps, Compute Engine, Pub/Sub.
4. **ExecutionGate is the ONLY path to tool execution.** No exceptions,
   not even for demos. Never add a route or helper that bypasses it.
5. **No secrets in the sandbox service, ever.** `tests/test_sandbox_env_proof.py`
   proves this; keep it passing.
6. Any new module touching Firestore MUST honour `AXON_FIRESTORE_MODE=memory`
   at import time. A module that builds a real client at import time broke
   CI for a whole day already — see `docs/day1-evidence.md`.
7. Every phase ends: tests pass → commit → push → CI green → report with
   the commit hash. Never claim done without evidence.
8. Tests must be proven to bite. For a regression fix, revert the fix once
   and watch the test fail before you trust it.

## Local commands

```bash
# tests, fully offline
AXON_FIRESTORE_MODE=memory .venv/Scripts/python.exe -m pytest -q tests

# never run locally without AXON_FIRESTORE_MODE=memory unless you intend
# to write to the REAL production Firestore
```

## Report format at the end of every phase

Files changed · commit hash · CI run number · exact pytest summary ·
evidence (live output, not intent) · anything skipped and why.
