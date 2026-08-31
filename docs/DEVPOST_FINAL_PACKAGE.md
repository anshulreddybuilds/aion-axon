# AION AXON — Final Devpost Package

## Title

AION AXON: Evidence-Driven Self-Evolving Autonomous Agent OS

## Tagline

A governed agent operating system that detects capability gaps, safely synthesizes and verifies new tools in a sandbox, and resumes execution—proving autonomy is earned through evidence.

## Short description

AION AXON is a governed autonomous agent system that detects missing capabilities during mission execution, synthesizes and screens candidate tools, verifies them in a credential-isolated sandbox, records human governance decisions, installs approved capabilities, and resumes the blocked mission through the same execution path.

## Full description

### The problem

Agents are easy to demonstrate when every required tool already exists. The harder production problem is the missing capability: the agent either stops for a developer, or generates and executes code without a sufficiently strong trust boundary.

### The solution

AION AXON treats capability acquisition as a governed software-engineering lifecycle. A mission is planned, missing capabilities are detected, a candidate is generated, the candidate is statically screened, executed in a separate sandbox, evaluated, reviewed by governance controls, and — where approval is required — held for an explicit owner decision. Only after the approval record is valid does installation proceed. The original mission can then resume through the normal execution gate.

### Current governed spine

The current repository exposes a 12-stage spine:

1. Owner
2. Orchestrator
3. Gap Detect
4. Research
5. Generate
6. AST Screen
7. Sandbox
8. Evaluator
9. Guardian
10. Approval
11. Install
12. Ledger

This is the current implementation contract. Earlier 15-stage wording is intentionally not used here.

### Security

The Python AST screen rejects dangerous imports and execution/reflection primitives before sandbox execution. The sandbox is a separate service and the installed capability remains a proxy to that boundary rather than moving generated code into the credentialed core. Approval is stored and re-read before installation. A kill switch and execution gate provide an additional control boundary.

### Persistence and auditability

Capability, mission and audit state use the Firestore-backed persistence layer. The ledger implementation computes SHA-256 event hashes and a hash chain, stores a seal in Firestore, and can later recompute and compare the chain. The correct security wording is **tamper-evident**, not tamper-proof.

### Telemetry

The telemetry module measures execution duration with a monotonic performance counter and reads token counts from model response usage metadata when supplied. If usage metadata is absent, the value remains unmeasured instead of being estimated. The frontend telemetry view renders API-derived measurements and explicitly shows missing measurements as absent.

### Google technologies

The repository includes Google Gemini/Gen AI integration, Google ADK, Cloud Run, Firestore, BigQuery tooling, Firebase Hosting, and related Google Cloud libraries. Exact model/version availability in the current production project should be described only where independently verified.

### Live links

- Frontend: https://aion-axon-2026.web.app/
- Backend: https://aion-core-638298765129.asia-south1.run.app/
- GitHub: https://github.com/anshulreddybuilds/aion-axon

### Testing

The authoritative `main` commit `98183a2d44e90e94c226e1f9579c0c316e8af151` has a successful GitHub Actions run. The backend job reported `572 passed, 4 skipped`, and the four Firestore-emulator concurrency tests passed. The frontend tests and Vite production build also passed.

### Honest limitations

- The current repository contract is 12 stages, not 15.
- The backend declares application version `0.3.0`; the repository does not establish the previously advertised V6 build identifiers.
- Live production HTTP headers and current deployment revision were not independently retrievable from the audit environment.
- Telemetry is honest about missing model usage metadata; it does not estimate unavailable token counts.
- The SHA-256 ledger is tamper-evident, not tamper-proof.
- Production cold-start behavior and current live persistence cannot be independently certified from source code alone.

### Why it matters

The central design principle is simple: **autonomy is earned through evidence**. The interesting property is not that an agent can write code; it is that the code must pass a chain of safety, execution, evaluation and governance checks before it becomes part of the agent's usable capability set.

## Built with

Google Gemini / Google Gen AI SDK · Google ADK · Python 3.11 · FastAPI · Uvicorn · React 18 · Vite · Tailwind CSS · Framer Motion · Google Cloud Run · Google Cloud Firestore · Firebase Hosting · BigQuery tooling · Python AST analysis · isolated sandbox service · SHA-256 hash-chain ledger.

## Data sources

- Operator-provided mission text and arguments.
- Firestore-backed capability, mission and audit state.
- Model-generated research/generation outputs where available.
- Runtime execution timing and model usage metadata where available.
- Public BigQuery datasets only where the relevant capability explicitly uses them.

## Judge FAQ

### Why is this self-evolving?

Because a missing capability can trigger a governed acquisition path instead of an immediate terminal failure. The generated candidate is screened and sandbox-tested before it is eligible for installation.

### Is generated code executed directly inside the core?

No. The repository's sandbox client treats the sandbox as the execution boundary, including after installation.

### How is credential access restricted?

The AST screen rejects environment/process/network/reflection primitives, and the separate sandbox boundary is designed to run without the application's credentials.

### How does approval work?

The approval record is persisted and installation re-reads that record. Approval is not treated as a cosmetic UI state.

### Is the ledger immutable?

The safe wording is tamper-evident. SHA-256 chaining detects changes relative to a stored seal, but an actor with direct write access to the same store could theoretically alter and reseal data.

### Are telemetry numbers estimated?

The current telemetry module does not infer token counts from text length. Model token counts are taken from usage metadata when available; missing values remain unmeasured.

### What should a judge focus on?

Watch the capability gap, acquisition/security path, real approval/install transition, mission resume, actual result, and audit evidence. Those are the core product story.

## AI assistance disclosure

AION AXON was developed with substantial AI-assisted coding and review, including Claude Code, while design decisions and approvals remained under the project author's control. This disclosure should be retained if required by the hackathon rules.
