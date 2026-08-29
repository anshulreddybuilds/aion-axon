# AION AXON — Handoff (read this first, in full, before touching anything)

Checkpoint written at HEAD `9af5bf1`, end of Phase 29. This is a state
snapshot, not a narrative — treat every fact below as current until you
personally verify otherwise (see §Q).

## A. Project identity

- Hackathon submission: "AION Axon" — a governed, self-extending AI agent.
  Core thesis: an agent that can propose a NEW capability, but never
  installs one without static AST screening, isolated sandbox execution,
  independent evaluation, AND a real human's explicit approval.
- GitHub: `anshulreddybuilds/aion-axon` (PRIVATE), branch `feat/beastmode-core`.
- GCP project: `aion-axon-2026`, region `asia-south1`.
- This repo is entirely separate from `C:\Users\sneha\aion` (a different,
  unrelated project under a different git identity). Never conflate them.

## B. Current Git state

- HEAD: `9af5bf1` — origin/feat/beastmode-core matches exactly.
- Working tree: clean.
- Branch is NOT `main` — everything lives on `feat/beastmode-core`; no PR
  has been opened yet.

## C. Production state

| | |
|---|---|
| Backend | Cloud Run service `aion-core`, region `asia-south1` |
| Backend URL | `https://aion-core-638298765129.asia-south1.run.app` |
| Current revision | `aion-core-rel-9af5bf17d1` — 100% traffic, contains HEAD `9af5bf1` |
| Rollback revisions (preserved, do not delete) | `aion-core-rel-9f1cfcd684`, `aion-core-rel-10037a2a58`, `aion-core-00034-6c4` |
| Frontend | Firebase Hosting, project `aion-axon-2026` |
| Frontend URL | `https://aion-axon-2026.web.app` |
| Frontend assets | `index-C4FMqUBT.js` / `index-zx6vXsgM.css` — matches local `web/dist` build of HEAD |
| Sandbox service | Cloud Run `aion-sandbox`, `https://aion-sandbox-638298765129.asia-south1.run.app` — reachable only via Cloud Run's own OIDC identity token (401/403 from outside Cloud Run; this is correct, not a bug) |
| Secrets | `gemini-api-key`, `axon-owner-token` in Secret Manager, wired via `secretKeyRef` — never read their values |
| Service account | `aion-core-sa@aion-axon-2026.iam.gserviceaccount.com` |
| Scaling | maxScale 20, concurrency 80, 1 vCPU / 512Mi, timeout 300s, ingress `all`, `allUsers` has `run.invoker` (intentionally public) |

**Real production mission: NEVER EXECUTED.** This is the single most
important fact in this document.

## D. Architecture overview

```
web/ (React + Vite + Tailwind, "Holo-Deck")
  → calls aion-core's REST API directly (no backend-for-frontend)
  → owner token lives in a JS module variable only, never localStorage

app/ (FastAPI, "aion-core")
  api.py            — all routes
  synapse/          — the acquisition engine (generate → screen → sandbox → evaluate → approve → install)
    engine.py       — SynapseEngine.propose()/install()/rollback() — THE core state machine
    generator.py    — Gemini-based candidate generation
    safety_screen.py — AST static screen (blocklist)
    sandbox_client.py — calls aion-sandbox over OIDC
    evaluator.py    — Gemma-based independent scoring
    planner.py      — memory-informed planning (ADVISORY ONLY)
  governance/
    approval.py     — ApprovalManager, Firestore-backed
    owner_auth.py   — require_owner dependency, bearer token, fails closed
    guardian.py     — policy engine (G-04 credential-access, G-06 override-refusal, etc.)
    autonomy_ledger.py — per-capability trust score
  beastmode/        — additive, read-only "proof layer" over the real pipeline
    memory.py, security_report.py, mission_readiness.py, red_team.py,
    ledger_chain.py, quarantine.py, lineage.py, contracts.py, risk_score.py
  memory/firestore_store.py — MemoryFirestore (tests/CI) vs AxonFirestore (prod), chosen by AXON_FIRESTORE_MODE at import time

sandbox/main.py — separate Cloud Run service, zero credentials, runs
  candidate code as `python -I` with POSIX rlimits (256MB/10s/no-fork) +
  a real subprocess wall-clock timeout + a stripped env allowlist.
```

Key architectural decision, repeated because it matters most:
**`app/beastmode/*` never has a write path.** Every beastmode module
reads real Firestore/AST-constant/red-team data and narrates it. Memory
and Planner are explicitly advisory — `synapse.propose()`'s control flow
was deliberately NOT wired to them, because `firestore_store` is a
module-level singleton shared unfixtured across the whole pytest session,
and branching engine behavior on that shared state was judged a
materially different risk than a pure read endpoint. Don't revisit this
without re-reading `app/beastmode/memory.py`'s and
`app/synapse/planner.py`'s module docstrings first.

## E. Mission pipeline (the real one, LIVE MISSION mode)

```
POST /synapse/propose (owner-gated)
  → SynapseEngine.propose(need, mission_id, allow_retry)
  → Guardian pre-screen (need text) — REFUSE possible here, before any generation
  → Research (web search, best-effort)
  → loop (1 or 2 attempts if allow_retry):
      generate_candidate() [Gemini]
      → safety_screen.screen() [AST] — REJECTED possible here
      → sandbox_client.execute_in_sandbox() — BLOCKED (sandbox unreachable) or
        SANDBOX_FAILED (retry if allowed) possible here
  → evaluate() [Gemma] — REJECTED if score < 50 (MIN_EVALUATOR_SCORE);
    UNSCORED does NOT block, travels to approval marked clearly
  → Guardian screen of the built capability — REFUSE possible here
  → approval_manager.create() — Firestore write, record.status = AWAITING_APPROVAL
     (record.to_dict() = the "Skill Passport", saved into capabilities/{name}.passport)

[SEPARATE HUMAN ACTION]
POST /approvals/{request_id}/decide (owner-gated)
  → re-reads the request from Firestore, refuses if already decided
  → writes status APPROVED/REJECTED + HUMAN_APPROVAL_DECISION audit event

[SEPARATE CALL]
POST /synapse/install/{capability} (owner-gated)
  → re-reads the capability's OWN passport's OWN approval_request_id
  → re-reads THAT approval fresh from Firestore — never trusts the passport's cached copy
  → refuses (APPROVAL_REQUIRED) unless status == APPROVED
  → ONLY this code path ever writes capabilities/{name}.state = "READY"
  → writes one evolution_event (the ledger)
```

Retry-with-feedback: `attempts[]` on the record captures each attempt's
real outcome (`SANDBOX_FAILED`/`SANDBOX_PASSED`/etc.) with real stderr,
bounded to max 2 attempts, never unbounded.

Proven this session (Phase 28C), not merely asserted: an approval on
capability A structurally cannot install capability B — each proposal
mints an independent `uuid4` request_id, and install() only ever reads
the TARGET capability's own passport. See
`tests/test_reliability.py::test_approving_one_capability_cannot_install_a_different_one`.

## F. Frontend structure

- `web/src/App.jsx` — nav shell: Command / Pipeline / Autonomy Ledger /
  Evidence / Mission Theater / Judge Mode.
- `web/src/MissionTheater.jsx` — has a LIVE MISSION / DEMO RECOVERY
  toggle. LIVE calls the real `/synapse/propose` (10-30s real call).
  DEMO renders `DemoRecoveryMode.jsx`, a **frontend-only, zero-network**
  fixture (see `web/src/demoRecoveryFixture.js` — grep it yourself, it
  imports nothing from `api.js` and makes no `fetch` call at all).
- `web/src/missionStages.jsx` — `deriveStages()`/`StageRow`, shared by
  both real Mission Theater rendering and the demo fixture (extracted
  here specifically to avoid a circular import — do not move it back).
- `web/src/JudgeMode.jsx` — the Proof Center. Cards: Mission Readiness,
  Security Coverage (with "ATTACK IT" + "KNOWN LIMITATIONS"), Red Team,
  Autonomy Ledger, Quarantine, Ledger Seal (owner-gated), Planner,
  Capability Contract, Lineage, Capability Memory, Approval Explain.
  Every card calls a real endpoint on mount; failures render
  "NOT AVAILABLE" with the real error, never fabricated.
- `web/src/api.js` — the only file that knows `CORE` (the backend base
  URL) and holds the owner token (module variable, never persisted).

No frontend test framework exists (no vitest/jest configured). The one
frontend test file, `web/src/demoRecoveryFixture.test.mjs`, uses Node's
built-in `assert` directly — run with `node web/src/demoRecoveryFixture.test.mjs`.

## G. Security controls

| Layer | What it does |
|---|---|
| AST (`app/synapse/safety_screen.py`) | Blocklists ~24 imports, ~13 builtins, all dunder attribute/name access, `.format()`/`.format_map()` on dunder-shaped string literals |
| Sandbox (`sandbox/main.py`) | Separate Cloud Run service, zero credentials, POSIX rlimits (256MB mem / 10s CPU / 1MB file / zero fork), real subprocess wall-clock timeout, stripped env allowlist |
| Guardian (`app/governance/guardian.py`) | Policy engine, deny-by-default on risk tier; G-04 (credential access), G-06 (override refusal) |
| Owner auth (`app/governance/owner_auth.py`) | Bearer token via `X-Axon-Token`, fails closed (503) if unconfigured, constant-time comparison |
| Ledger (`app/beastmode/ledger_chain.py`) | SHA-256 hash chain over evolution_events, tamper-EVIDENT not tamper-PROOF (seal file is local disk — disclosed limitation) |

**5 real AST bypasses found and fixed this session** (all in
`app/synapse/safety_screen.py`, each with a real repro before the fix
and a regression test after):
1. Forbidden-builtin aliasing (`x = eval; x(...)`) — commit `930aeda`
2. `__builtins__` captured by bare name — commit `8a15a12`
3. Network-capable stdlib beyond `socket` (urllib/http/ftplib/smtplib/xmlrpc/telnetlib/asyncio) — commit `1d45c2d`
4. Format-string dunder traversal (`'{0.__class__...}'.format(x)`) — commit `15cc7c7`
5. Frame/object-graph reflection (`inspect`, `gc`) — commit `626bb0a`

Live red-team result: **22/23 vectors contained** (`GET /beastmode/red-team`,
computed fresh on every call, not cached).

## H. Approval model

`PROPOSAL != APPROVAL != INSTALL`, enforced structurally:
- `decide()` refuses a request that's already been decided (no replay).
- `install()` NEVER trusts the passport's cached approval status — always
  re-reads Firestore fresh.
- Each proposal gets an independent `uuid4` request_id; no cross-capability
  reuse is possible (proven by test, Phase 28C).
- `decided_by` is a caller-supplied label, not cryptographic identity —
  this is a known, disclosed limitation of the single-shared-bearer-token
  auth model (see `app/governance/owner_auth.py`'s own docstring). Not a
  new finding, don't "fix" it without an owner decision (it means real
  per-user auth, a bigger change).

## I. Test/build baseline

- Backend: `454 passed, 0 failed` — `cd` to repo root, `./.venv/Scripts/python.exe -m pytest -q`
- Fixture: `11 passed` — `node web/src/demoRecoveryFixture.test.mjs`
- Frontend build: clean — `cd web && npm run build`
- **One pre-existing, unrelated test-order fragility**:
  `tests/test_reliability.py::test_declared_but_unbuilt_capability_is_also_a_gap`
  fails when run in isolation (depends on `registry.declare("write_brief", ...)`
  happening in an earlier test file), passes as part of the full suite.
  Confirmed present before Phase 28's changes too. Not a security issue.
  Not fixed — out of scope each time it was noticed.

## J. Production endpoints (all live as of `9af5bf1`)

Public reads: `/`, `/health`, `/capabilities`, `/autonomy`,
`/autonomy/{capability}`, `/telemetry`, `/evolution`, `/ground-truth/match`,
`/capabilities/{capability}/passport`, `/monitors`, `/sandbox/proof`,
`/approvals/{request_id}/review`, `/approvals/pending`, `/killswitch` (GET),
`/beastmode/red-team`, `/beastmode/ledger/verify`, `/beastmode/contract/{name}`,
`/beastmode/quarantine`, `/beastmode/lineage/{name}`,
`/beastmode/approval/{request_id}/explain`, `/beastmode/memory/{capability}`,
`/beastmode/security/report`, `/beastmode/mission/readiness`.

Public POST (advisory, zero side effects, proven by test):
`/beastmode/memory/query`, `/beastmode/plan`.

Owner-gated (require `X-Axon-Token`, 401 otherwise — all individually
regression-tested in `tests/test_owner_auth.py`):
`/missions*`, `/synapse/propose`, `/synapse/install/{capability}`,
`/synapse/rollback/{capability}`, `/ground-truth` (POST), `/monitors` (POST +
`/run-due` + `/{id}/disable`), `/approvals/{id}/decide`, `/killswitch` (POST),
`/beastmode/ledger/seal`.

## K. Known limitations (disclosed, live in `/beastmode/security/report`)

1. **Sandbox process does not independently block network egress** once a
   connection is attempted — AST is the only control against this vector.
2. **Cloud Run has no VPC-based egress isolation** — confirmed via
   `gcloud run services describe` (no `vpc-access-connector` annotation)
   AND `gcloud compute networks vpc-access connectors list` returning
   `SERVICE_DISABLED` (Serverless VPC Access API never enabled on this
   project). This is positive evidence of absence, not an unchecked box.
   **Do not silently fix this** — creating a VPC connector/NAT/firewall is
   a real infrastructure decision requiring separate owner authorization.
3. **YAML containment is dependency-absence**, not a deliberate AST rule
   (`pyyaml` isn't installed in the sandbox container) — fragile if that
   ever changes.
4. **Format-string protection covers literal strings only** — a
   sufficiently obfuscated dynamically-constructed format string remains
   a residual, disclosed blocklist gap.
5. **Ledger seal is a local file** — an actor with both direct Firestore
   write access and local disk write access to `ledger_seal.json` could
   edit an event and re-seal over it. Tamper-evident, not tamper-proof,
   by design.
6. `security_report.py`'s `regression_tests.latest_known` is a manually-
   synced STATIC snapshot (currently `{value: 439, as_of_commit: "10037a2"}`)
   — it is NOT the live count (454 as of this handoff) and will drift
   further with each new commit that adds tests without updating this file.
   The live `red_team` field in the same response IS computed fresh every call.

## L. What has already been completed (do not redo)

- Phases 19-24: 5 real AST bypasses found+fixed, ledger forensic suite
  (17 attack classes), owner-auth regression coverage audit (7 previously
  untested endpoints closed), sandbox resource-exhaustion tests (real,
  non-mocked), Capability Memory, Planner, formal state machine module
  (`app/beastmode/state_machine.py` — exists, has no dedicated endpoint).
- Phase 22: Security Coverage Report + Judge Mode card.
- Phase 23: Deterministic Demo Recovery Mode (frontend-only fixture).
- Phase 25: First production push+deploy (backend+frontend).
- Phase 26: Mission Readiness endpoint + Judge Mode narrative + a real
  frontend/backend version-skew crash found and fixed during verification.
- Phase 27: Full deploy+verify cycle repeated, all smoke tests passed.
- Phase 28: Cross-capability approval-binding regression test, mission
  input `min_length=3` validation, explicit LIVE/DEMO UI wording.
- Phase 29: Pushed + deployed Phase 28's work, re-verified everything in
  production including a second live Demo Recovery run (zero mutation
  confirmed twice, on two different production deploys).

**Every one of the above is LIVE VERIFIED in production as of `9af5bf1`.
Do not re-run the full Phase 25-29 deploy+verify cycle unless `git status`/
`HEAD` actually differs from this document — see the next-session prompt.**

## M. What MUST NOT be repeated

- Do not re-discover that this repo is separate from `C:\Users\sneha\aion`.
- Do not re-run the full forensic audits already completed (network
  egress, ledger tampering, owner-auth sweep, reflection/type() battery)
  unless new code touches those areas.
- Do not re-derive the mission pipeline trace from scratch — §E above is
  it.
- Do not re-verify Phase 25-29's deployments from zero — check `git
  status`/HEAD against §B first; if they match, the production state in
  §C is still accurate (production doesn't drift on its own).
- Do not treat the stale `regression_tests` count in the security report
  as a bug requiring an urgent fix — it's a known, disclosed, low-priority
  paper cut (see §K.6).

## N. Current highest-priority gaps

1. **No real owner-authorized production mission has ever run.** This is
   the load-bearing gap across every phase from 23 onward.
2. `security_report.py`'s static test count is stale (439 vs actual 454+).
   Trivial fix, low priority.
3. Cloud Run VPC egress remains architecturally open — a real fix needs
   an explicit owner decision (cost/complexity of a VPC connector) and is
   NOT something to do silently.
4. No PR has been opened from `feat/beastmode-core` to `main` — worth
   asking the owner whether that's wanted before a hackathon submission
   deadline.
5. `app/beastmode/state_machine.py` exists but has no dedicated
   Judge-visible endpoint/UI (directive from Phase 23-26 called this out
   as low-priority; still true).

## O. Exact recommended next phase

**Either:**
(a) The owner personally executes the first real mission (see §P) — this
    is the highest-leverage remaining action for the hackathon submission,
    and no amount of further Claude Code work substitutes for it.
(b) If the owner isn't ready for that yet, the next safe engineering task
    is resyncing `security_report.py`'s static test count (§K.6, §N.2) —
    small, safe, five-minute fix.

Do not invent a large new phase without the owner's direction — the
system has been extensively hardened and verified; further scope should
be owner-directed, not self-generated.

## P. Human authorization boundaries (unchanged, absolute)

Claude Code must NEVER: read/print/transmit the owner token, click RUN
MISSION, approve/reject a real capability, install a real capability,
mutate Firestore/ledger through the real mission path, flip the kill
switch, or claim a real mission was executed when it wasn't.

To run the first real mission, the OWNER must personally: open
`https://aion-axon-2026.web.app` → Mission Theater → select **LIVE
MISSION** (not DEMO RECOVERY) → paste the real owner token into the
unlock field → type a real need → click **RUN MISSION** → personally
review and decide any resulting approval request.

## Q. Useful commands

```bash
# repo state
cd /c/Users/sneha/Desktop/AION-AXON-core
git status --short && git rev-parse HEAD && git fetch origin && git rev-parse origin/feat/beastmode-core

# tests
./.venv/Scripts/python.exe -m pytest -q
node web/src/demoRecoveryFixture.test.mjs
cd web && npm run build

# production read-only checks (safe, no token needed)
curl -s https://aion-core-638298765129.asia-south1.run.app/health
curl -s https://aion-core-638298765129.asia-south1.run.app/beastmode/mission/readiness
curl -s https://aion-core-638298765129.asia-south1.run.app/beastmode/security/report

# production config (read-only, gcloud already authenticated in this env)
gcloud run services describe aion-core --region=asia-south1 --format="value(status.latestReadyRevisionName,status.traffic)"

# deploy (only with explicit owner authorization each time)
gcloud run deploy aion-core --source=. --region=asia-south1 --revision-suffix=rel-$(git rev-parse --short=10 HEAD) --quiet
npx firebase deploy --only hosting --project aion-axon-2026
# NOTE: the gcloud deploy command reliably exceeds a 2-minute foreground
# shell timeout and appears to fail/hang locally -- it has succeeded
# server-side both times this happened. Always re-check
# `gcloud run services describe` before assuming failure or retrying.
```

## R. Important files/modules (for a fast orientation read, not exhaustive)

- `app/synapse/engine.py` — the whole real pipeline, `SynapseEngine`.
- `app/governance/approval.py`, `owner_auth.py`, `guardian.py` — the trust boundary.
- `app/beastmode/security_report.py`, `mission_readiness.py`, `memory.py`, `red_team.py` — the proof layer.
- `web/src/MissionTheater.jsx`, `DemoRecoveryMode.jsx`, `missionStages.jsx`, `JudgeMode.jsx` — the judge-facing UI.
- `CLAUDE.md` — original project brief/doctrine (Day-1 era; not updated past that except a pointer added by this handoff).
- `tests/test_reliability.py`, `test_owner_auth.py`, `test_ledger_forensics.py`, `test_adversarial.py` — the highest-signal test files for anything touching security/approval.

## S. Rollback information

```bash
# roll back backend traffic to the pre-Phase-28 revision
gcloud run services update-traffic aion-core --to-revisions=aion-core-rel-9f1cfcd684=100 --region=asia-south1
# or further back:
# aion-core-rel-10037a2a58 (pre-Phase-25/26 work)
# aion-core-00034-6c4 (original baseline before this entire session)

# frontend: Firebase Hosting retains prior releases in its own console;
# not independently scripted this session -- use the Firebase console's
# release history if a frontend rollback is ever needed.
```
