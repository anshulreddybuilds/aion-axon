# AION AXON

**Evidence-Driven Self-Evolving Autonomous Agent OS**

> **Autonomy is earned through evidence.**

Google **All Things Agentic Hackathon 2026** · Taskmaster

## What this is

AION AXON is a governed autonomous-agent runtime focused on the hard case: a mission requires a capability that is not currently available.

Instead of silently guessing or executing arbitrary generated code, AXON routes capability acquisition through a governed spine: plan the mission, detect the gap, research/generate a candidate, statically screen it, execute it in a separate sandbox, evaluate it, apply guardian/risk policy, obtain human approval where required, install the approved capability, and resume the mission through the normal execution gate.

## Current 12-stage governed spine

```text
01 Owner
   ↓
02 Orchestrator
   ↓
03 Gap Detect
   ↓
04 Research
   ↓
05 Generate
   ↓
06 AST Screen
   ↓
07 Sandbox
   ↓
08 Evaluator
   ↓
09 Guardian
   ↓
10 Approval
   ↓
11 Install
   ↓
12 Ledger
   ↓
Blocked mission resumes through the normal execution path
```

**Important:** the current repository contract is **12 stages**. Earlier 15-stage submission drafts are obsolete and should not be used as implementation claims.

## Security model

### AST safety screen

`app/synapse/safety_screen.py` parses generated Python with `ast` before execution. It rejects dangerous imports and calls including process/environment access, network clients, dynamic execution and several reflection/sandbox-escape primitives.

The screen is defense-in-depth, not a mathematical proof of safety. The code explicitly documents that sufficiently indirect techniques can evade static analysis, which is why the sandbox is a separate trust boundary.

### Separate sandbox

`app/synapse/sandbox_client.py` keeps generated-code execution outside the credentialed core. The client obtains an OIDC identity token from the Cloud Run metadata server when running in Cloud Run and invokes the separate sandbox service. Installed capabilities continue to use that boundary rather than moving generated code into the core process.

### Governance

Approval is a real persisted state. The installation path re-reads the approval record rather than trusting the proposal that requested installation. Owner authorization, guardian policy, risk scoring, kill switch and execution-gate controls provide additional boundaries.

## Persistence and auditability

The Firestore-backed store persists capabilities, missions and audit/evolution records. Application startup rehydrates the runtime registry from persisted state.

`app/beastmode/ledger_chain.py` implements a SHA-256 hash chain:

- canonicalizes each event
- computes an event SHA-256 digest
- chains each event to the previous digest
- stores the final seal in Firestore
- recomputes and compares the chain during verification

The correct security wording is **tamper-evident**, not tamper-proof. An actor with direct write access to the same datastore could alter records and reseal them; preventing that requires an external trust root and is outside this implementation.

## Telemetry

`app/observability/telemetry.py` follows two rules: measure rather than estimate, and never let telemetry failure change application behavior.

- Execution duration uses `time.perf_counter()`.
- Gemini token counts come from the response's `usage_metadata` when supplied.
- Missing usage metadata remains `None`/unmeasured instead of being estimated from text length.
- The frontend telemetry pane displays API-derived measurements and explicitly shows absent measurements as unavailable.

Do not use older submission wording that promises fields such as `telemetry.total_execution_ms` unless those exact fields are independently observed in the current deployment. The current source uses structures such as `tool_executions`, `model_calls`, `by_stage`, and measured token fields.

## Live links

- **Frontend:** https://aion-axon-2026.web.app/
- **Backend:** https://aion-core-638298765129.asia-south1.run.app/
- **GitHub:** https://github.com/anshulreddybuilds/aion-axon

The repository contains additional development surfaces at `/v2`, `/v3`, `/v4`, and `/v5`. The default `/` surface is the current production/filming fallback selected by `web/src/main.jsx`.

## Verify it yourself

The authoritative `main` baseline has a successful GitHub Actions run with both backend and frontend validation.

```bash
git clone https://github.com/anshulreddybuilds/aion-axon.git
cd aion-axon
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
# .venv\\Scripts\\Activate.ps1

pip install -r requirements.txt
pytest -q

cd web
npm ci
npm test
npm run build
```

### Latest authoritative CI evidence

Commit:

`98183a2d44e90e94c226e1f9579c0c316e8af151`

GitHub Actions run `33168696307` completed successfully:

- Backend: **572 passed, 4 skipped**.
- All four Firestore-emulator concurrency tests passed.
- Frontend test suite passed.
- Vite production build passed.

The four backend skips in the normal hermetic run are the distributed Firestore tests; CI runs those against the Firestore emulator in a separate step.

## Current implementation stack

The repository currently contains:

- Python 3.11
- FastAPI / Uvicorn
- React 18 / Vite
- Tailwind CSS / Framer Motion / Lucide React
- Google Gen AI SDK
- Google ADK
- Google Cloud Run
- Google Cloud Firestore
- Firebase Hosting
- BigQuery client/tooling
- Python AST analysis
- Separate sandbox service
- SHA-256 hash-chain ledger

Exact model versions and production configuration should be described only when independently verified for the deployment being submitted.

## Honest limitations

1. **12-stage contract:** the current implementation is 12 stages, not the older 15-stage draft.
2. **Version identifiers:** the backend application declares version `0.3.0`; the frontend package declares `0.1.0`. The repository does not establish `AXON RUSTOS v1.1.0`, `AXON-WEB-V6.1.4-PROD-20260831`, `axon_core v2.0.0-berserk`, or `v6-beastmode-prod-20260831` as authoritative source-controlled identifiers.
3. **Live deployment verification:** the audit environment could not retrieve the supplied production frontend/backend responses, so current live HTTP headers, TLS details, cache headers and serving revision remain unverified here.
4. **Telemetry:** token usage is reported only when model usage metadata is available; missing values are not estimated.
5. **Ledger:** the SHA-256 ledger is tamper-evident, not tamper-proof.
6. **Sandbox:** source code establishes the intended separate execution boundary, but current live sandbox configuration should not be presented as independently certified without a current deployment check.
7. **Demo state:** a failed or awaiting-approval mission must be presented as such. The UI is designed to keep real failure states distinct from success.

## Submission documents

The final submission package is maintained in:

- [`docs/FINAL_SUBMISSION_CLAIM_MATRIX.md`](docs/FINAL_SUBMISSION_CLAIM_MATRIX.md)
- [`docs/FINAL_DEMO_RUNBOOK.md`](docs/FINAL_DEMO_RUNBOOK.md)
- [`docs/FINAL_ARCHITECTURE.md`](docs/FINAL_ARCHITECTURE.md)
- [`docs/DEVPOST_FINAL_PACKAGE.md`](docs/DEVPOST_FINAL_PACKAGE.md)

## AI assistance disclosure

AION AXON was developed during the hackathon period with substantial AI-assisted coding/review, including Claude Code. The project author retained control of design decisions, approvals and deployments. Retain or adapt this disclosure to the hackathon's final submission rules.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
