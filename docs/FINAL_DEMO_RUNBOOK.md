# AION AXON — Final Demo Recording Runbook

**Owner records the video. This document does not require recording by an agent.**

## Goal

Tell one evidence-driven story in under four minutes:

`MISSION → PLAN → GAP → ACQUIRE → SCREEN → SANDBOX → GOVERN → INSTALL → RESUME → RESULT → AUDIT`

The current repository implements a **12-stage** spine, not the older 15-stage wording.

## Pre-recording safety check

1. Open the live frontend: https://aion-axon-2026.web.app/
2. Confirm the page actually shows the live API as online.
3. Do one unrecorded mission run first.
4. Use this mission text:

```text
Calculate the coefficient of variation for dataset [10, 12, 15, 18, 20] and interpret the relative dispersion.
```

5. Only record a successful run. If the live system fails, record the actual failure only if the submission narrative is explicitly about failure recovery; otherwise retry after diagnosis.
6. Do not quote fixed latency/token numbers from old documents. Read the values actually displayed by the current run.

## Recording timeline

### 0:00–0:20 — Problem

**Show:** clean AXON dashboard.

**Say:**

> “Traditional agents stop when a required capability is missing, while unrestricted code generation creates a security problem. AION AXON treats capability acquisition as a governed process: autonomy has to earn its way into execution through evidence.”

### 0:20–0:40 — Architecture

**Show:** current pipeline / command view.

**Say:**

> “The current AXON spine makes the important handoffs visible: planning, gap detection, generation, AST screening, sandbox verification, evaluation, guardian policy, human approval, installation and ledger recording.”

### 0:40–1:20 — Mission

**Action:** paste the coefficient-of-variation mission and dispatch it.

**Say:**

> “I’m giving AXON a real computational mission. The important part is that I’m not giving it a coefficient-of-variation capability as a second prompt. AXON has to use its governed capability path.”

**Show:** planner and capability-gap state if the current UI exposes it.

### 1:20–2:15 — Acquisition and security

**Show:** the live acquisition stages as they actually appear.

Priority order:

1. gap / blocked state
2. generated candidate
3. AST screen
4. sandbox result
5. evaluator / guardian result
6. approval gate

**Say:**

> “The missing capability is intercepted rather than silently guessed. The candidate is generated and statically screened before sandbox execution. The sandbox is the execution boundary; approval is a separate governance decision.”

If the UI opens a human approval gate, show the actual approval action. Do not describe auto-promotion if the live run actually requires approval.

### 2:15–2:55 — Install and resume

**Action:** after the legitimate approval/install step, stop clicking.

**Show:** mission transition from blocked/waiting to resumed/completed.

**Say:**

> “The capability is now installed through the governed path. The original mission can resume through the same execution engine instead of requiring me to re-submit the task.”

Then state the actual result shown by the application.

For the coefficient-of-variation mission, the expected mathematical reference is approximately:

- mean: `15.0`
- population standard deviation: `4.183`
- coefficient of variation: `27.89%`

These are reference values only. The video must show the application's actual result, not a hardcoded narration if the application produces something different.

### 2:55–3:25 — Telemetry and audit evidence

**Show:** current telemetry/audit panels.

**Say:**

> “The telemetry view reports runtime measurements and model usage metadata when those measurements are actually available. Missing measurements remain unknown instead of being estimated. The audit layer records the evolution event and maintains a SHA-256 hash chain.”

If the current UI shows a real hash, let the viewer read it. Do not invent or substitute a shortened example hash.

### 3:25–3:45 — Security / persistence

**Show:** security proof, capability passport, registry, or approval record — whichever is genuinely populated by the current run.

**Say:**

> “The capability remains governed after acquisition: the registry and approval record provide the chain of custody, while the sandbox remains the execution boundary.”

### 3:45–3:55 — Closing

**Show:** strongest clean completed state.

**Say:**

> “AION AXON demonstrates a practical form of self-evolving agency: detect the gap, acquire the capability under evidence, and continue the mission without abandoning governance. Autonomy is earned through evidence.”

## Recording rules

- Keep the video below four minutes.
- Do not show terminals, secrets, API keys, local `.env` files, or private dashboards.
- Do not use fixed numbers from old scripts unless the current UI displays the same numbers.
- Do not call the current system a 15-stage system; the repository's current contract is 12 stages.
- Do not call the ledger tamper-proof; the implementation explicitly describes it as tamper-evident.
- Do not claim a live deployment revision that has not been independently verified.
- During auto-resume, stop clicking so the judge can see that the original mission continues without re-prompting.

## Recovery plan

- **Live API unreachable:** stop and fix the deployment before recording.
- **Mission fails:** do not narrate it as success. Capture the actual error only if needed for diagnosis, then retry after diagnosis.
- **Approval required:** perform the real approval step; do not fake an automatic promotion.
- **Telemetry absent:** say it is unavailable rather than inventing a value.
- **Ledger absent:** omit the claim from the spoken video rather than displaying a fabricated hash.
- **Existing capability already present:** use the application's actual reuse path if available; do not delete production state merely to force a demo.
