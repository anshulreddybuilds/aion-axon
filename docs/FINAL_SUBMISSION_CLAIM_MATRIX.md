# AION AXON — Final Submission Claim Matrix

**Evidence standard:** current `main` repository code, current Git history, and the latest successful GitHub Actions run for `main` are authoritative. Old hackathon drafts and earlier V6 labels are not authoritative.

## Current repository identity

- Authoritative baseline: `main`
- Baseline commit: `98183a2d44e90e94c226e1f9579c0c316e8af151`
- Latest successful CI run on that commit: GitHub Actions run `33168696307`
- Backend application version declared in `app/api.py`: `0.3.0`
- Frontend package version declared in `web/package.json`: `0.1.0`
- Current repository does **not** establish `AXON RUSTOS v1.1.0`, `AXON-WEB-V6.1.4-PROD-20260831`, `axon_core v2.0.0-berserk`, or revision `v6-beastmode-prod-20260831` as source-controlled build identifiers.

## Claim matrix

| Claim | Status | Evidence | Safe submission wording |
|---|---|---|---|
| Governed self-evolution | PROVEN | `app/missions/`, `app/synapse/`, `app/governance/`, and the 12-stage production UI path implement planning, gap detection, synthesis, screening, sandboxing, evaluation, governance, approval, install and resume. | “AXON can acquire a missing capability through a governed lifecycle before execution.” |
| 12-stage capability spine | PROVEN | Current README and UI architecture define 12 stages: Owner, Orchestrator, Gap Detect, Research, Generate, AST Screen, Sandbox, Evaluator, Guardian, Approval, Install, Ledger. | “The current production architecture exposes a 12-stage governed capability spine.” |
| 15-stage lifecycle | CONTRADICTED | Current repository documents 12 stages, not 15. | Do not claim 15 stages for the current repository. |
| SYNAPSE | PROVEN | `app/synapse/engine.py`, generator/evaluator/planner/safety/sandbox modules, plus frontend live pipeline rendering. | “SYNAPSE generates and verifies candidate capabilities through the governed acquisition path.” |
| AST firewall | PROVEN | `app/synapse/safety_screen.py` uses Python AST parsing and blocks dangerous imports/calls and dunder/reflection patterns. | “Generated Python is statically screened before sandbox execution.” |
| Zero-credential sandbox | SUPPORTED BUT NOT FULLY PROVABLE | `app/synapse/sandbox_client.py` documents a separate Cloud Run sandbox, OIDC invocation, and permanent proxy execution boundary. | “The architecture isolates generated code in a separate sandbox with no application credentials.” |
| Sandbox network isolation | SUPPORTED BUT NOT FULLY PROVABLE | Sandbox client and repository threat model specify a separate service and locked execution boundary; independent current production black-box verification is unavailable here. | “Sandbox execution is designed to run behind a separate credential-isolated service.” |
| Human approval gate | PROVEN | `app/governance/approval.py`, `require_owner`, approval APIs, frontend approval flow, and CI tests cover approval/rejection paths. | “Capabilities requiring approval are held until an owner decision is recorded.” |
| Risk governance | PROVEN | `app/governance/risk_score.py`, guardian/review/execution gate modules and tests. | “Risk and guardian checks determine whether a candidate may proceed.” |
| Automatic resume | PROVEN | `app/missions/service.py`, mission resume logic, concurrency protections, and frontend reconciliation tests. | “After successful installation, the blocked mission can resume through the same governed execution path.” |
| Firestore persistence | PROVEN | `app/memory/firestore_store.py`, rehydration on application lifespan, registry persistence and emulator CI tests. | “Capability and mission state are persisted through the Firestore-backed store.” |
| SHA-256 ledger | PROVEN | `app/beastmode/ledger_chain.py` imports `hashlib`, computes SHA-256 event and chain hashes, stores the seal in Firestore, and verifies it later. | “AION AXON maintains a tamper-evident SHA-256 hash chain over recorded evolution events.” |
| Tamper-proof ledger | CONTRADICTED | `ledger_chain.py` explicitly states the seal is tamper-evident, not tamper-proof, because an actor with direct Firestore write access could alter and reseal data. | Use “tamper-evident,” never “tamper-proof.” |
| Server-grounded telemetry | PROVEN | `app/observability/telemetry.py` measures durations with `time.perf_counter()` and reads model token usage from `usage_metadata`; frontend `TelemetryPane.jsx` renders those API-derived values. | “Telemetry uses runtime measurements and model-reported usage metadata; unavailable measurements remain unknown.” |
| Exact `telemetry.total_execution_ms` contract | NOT OBSERVABLE | Current repository telemetry uses `tool_executions`, `model_calls`, `by_stage`, and related fields rather than the previously cited exact field names. | Do not claim those exact field names unless verified in the deployed API. |
| Synthetic token estimation | PROVEN ABSENT IN CURRENT TELEMETRY MODULE | `usage_of()` returns `None` and `measured=False` when model usage metadata is absent; it does not estimate from text length. | “Token counts are reported only when supplied by model usage metadata.” |
| Decorative randomness | UNKNOWN | No deployed asset access was available from this environment, so current production bundle-level `Math.random()` usage could not be independently audited. | Do not mention randomness in the submission unless verified from the deployed bundle. |
| Multimodal output | SUPPORTED BUT NOT FULLY PROVABLE | Current frontend contains artifact rendering paths and image/table/SVG-oriented views, but current production output was not independently inspected here. | “The UI supports structured and visual artifact presentation.” |
| Responsive UI | PROVEN | Current frontend contains desktop sidebar plus mobile navigation and responsive Tailwind classes; frontend CI build succeeds. | “The dashboard has responsive desktop/mobile navigation.” |
| Production deployment | NOT OBSERVABLE | Direct fetches of the supplied production URLs failed from this environment; GitHub repository and CI prove source/build state, not live hosting state. | “The project has production URLs; current live deployment identity should be verified manually before submission.” |
| V6 deployment identity | UNKNOWN | No current repository identifier establishes the claimed V6 strings; live endpoint could not be fetched here. | Do not present V6 build identifiers as verified. |

## CI evidence

The latest successful `main` CI run (`33168696307`) completed both backend and frontend jobs. The backend job reported `572 passed, 4 skipped`; all four Firestore-emulator concurrency tests passed. The frontend job ran all `*.test.mjs` files and completed a successful Vite production build.

The latest feature branch `feat/beastmode-core-oagiwb-weku3h` is **not** the submission baseline: its latest commit `84aca2a909d200bf63b2f7d8208ee5228871609d` has a failing CI run where the real Firestore mission-resume concurrency test reported zero winners. Do not merge that branch merely to obtain newer UI work without fixing and re-running CI.
