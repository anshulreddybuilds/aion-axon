# AION AXON — Screenshot Evidence Checklist

Only use screenshots captured from the current live application or a current local reproduction. Never manufacture screenshots or edit UI states into evidence.

| # | Screenshot | Show | Claim supported |
|---|---|---|---|
| 01 | Mission Intake | Mission input + current AXON command surface | The operator can dispatch a mission. |
| 02 | Capability Gap | Real blocked/gap state naming the missing capability | Gap detection is a real runtime state. |
| 03 | Generation | Actual generated capability/candidate if exposed | Capability acquisition generates a concrete candidate. |
| 04 | AST Screen | Actual safety findings/pass result | Generated code is statically screened. |
| 05 | Sandbox | Actual sandbox result and reason | Candidate execution is isolated/tested before install. |
| 06 | Evaluator / Guardian | Actual score/verdict/policy result | Candidate is evaluated and governed. |
| 07 | Approval | Actual approval request or recorded owner decision | Approval is a persisted governance state. |
| 08 | Install / Resume | Actual installation and mission transition | The acquired capability becomes available and the mission can resume. |
| 09 | Final Result | Actual mission result | The application completed the requested computation. |
| 10 | Ledger | Actual event/hash-chain/verification record | Audit evidence is recorded and hash-linked. |
| 11 | Security Block | Actual blocked unsafe capability attempt, if available | Dangerous behavior is rejected by governance/safety controls. |
| 12 | Telemetry | Actual runtime/model-usage values | Telemetry is displayed from measured/returned data. |

## Caption template

**What is shown:** describe only what is visibly present.

**Why it matters:** connect the visible state to one architectural claim.

**Evidence level:** PROVEN / SUPPORTED BUT NOT FULLY PROVABLE / NOT OBSERVABLE / UNKNOWN.

Never use a caption that says “proves” when the screenshot only illustrates a component or architecture.
