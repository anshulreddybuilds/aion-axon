# AXON Beastmode — Repository Audit

**Written before any implementation, per the owner's own instruction:
"do not modify blindly."** Branch `feat/beastmode-core`, `main` untouched.
Baseline: **280 tests passing**, clean tree, HEAD `8fc86b7`.

This audit exists to separate what the codebase actually does from what
the Beastmode plan assumed it doesn't. Several proposed "new" subsystems
turn out to already exist under different names.

---

## What already exists (verified in source, not assumed)

| Beastmode asks for | Already real, as | File |
|---|---|---|
| Formal risk tiers (5-level) | 2-level `Enforcement` (`PROHIBITED` / `APPROVAL_REQUIRED`) + 3-level `RiskLevel` (`LOW`/`MEDIUM`/`HIGH`) | `app/governance/policies.py`, `app/governance/guardian.py` |
| Policy-as-code (`G-04`, `G-06`, …) | **7 policies, G-01 through G-07**, deny-by-default, ordered by precedence, first match wins | `app/governance/policies.py` |
| "Trust Kernel" / immutable governance core | `ExecutionGate` is the only path to tool execution — verified this session by tracing every caller; exactly one file (`app/workflows/orchestrator.py`) calls it | `app/governance/execution_gate.py` |
| Adversarial red-team suite | **10 real adversarial tests**, not simulated: exfiltration payloads, persuasion phrasings, kill-switch coverage across every path, a planted secret in the sandbox scan | `tests/test_adversarial.py` |
| "Why was this blocked?" explainability | Every Guardian decision already carries `policy_id`, `policy_title`, `reason` — returned by the live API today | `app/governance/guardian.py`, `app/governance/approval.py` |
| AST firewall | 15 forbidden imports, 13 forbidden builtins, already enforced pre-sandbox | `app/synapse/safety_screen.py` |
| Zero-credential sandbox | Separate Cloud Run service, 0 credentials, 0 IAM roles, verified live: `403` from the public internet | `app/synapse/sandbox_client.py` |
| Independent evaluation | Gemma (`gemma-4-26b-a4b-it`) scores every candidate; policy can override a 100/100 score (verified live: candidates have been auto-rejected despite passing sandbox) | `app/synapse/evaluator.py` |
| Human approval, not a formality | `install()` **re-reads** the approval from Firestore rather than trusting the proposal | `app/synapse/engine.py` |
| Rollback | `POST /synapse/rollback/{capability}` exists, tested, used operationally this session to reset demo takes | `app/synapse/engine.py` |
| Evidence Passport | `GET /capabilities/{name}/passport` already returns need, source, test, AST findings, sandbox result, evaluator verdict+reasoning, approver | `app/api.py` |
| Evolution ledger | 8 real events recorded (verified live), `BEFORE → CHANGE → REASON → AFTER` shape | `app/synapse/engine.py` |
| Mission auto-resume | `resume_blocked()` — a blocked mission finishes itself on install, proven live multiple times this session | `app/missions/service.py` |

**Consequence:** several Beastmode items are *renaming* exercises
(`RiskLevel` → "Risk Engine", `ExecutionGate` → "Trust Kernel",
`tests/test_adversarial.py` → "Red Team Engine"), not new engineering.
Renaming for the demo narrative is cheap and legitimate. Rewriting the
underlying mechanism to match the new name is not, and is not being done
here — the existing, tested implementation is kept and *wrapped*, not
replaced.

---

## What genuinely does not exist yet

| Beastmode asks for | Verdict |
|---|---|
| Cryptographic hash-chained ledger (SHA-256, tamper-evident) | **Does not exist.** Evolution events are stored, not hash-chained. Real gap, buildable additively. |
| Formal `CapabilityContract` (I/O schema + permission manifest as a first-class artifact) | **Does not exist as a schema.** The information exists scattered (risk field, AST findings) but not as one declared contract object. |
| Capability lineage / versioning graph | **Does not exist.** One name = one live implementation; no v1/v2/v3 history. |
| Capability memory ("don't regenerate what already failed") | **Does not exist.** Each acquisition is independent. |
| Judge Mode / dedicated evidence-walkthrough UI | **Does not exist.** |
| 15-state formal state machine | **Partially exists** as informal status strings (`BLOCKED`, `AWAITING_APPROVAL`, `INSTALLED`, `REJECTED`, `ROLLED_BACK`) — not a declared enum with transition rules. |
| Quarantine / automatic revalidation on dependency change | **Does not exist.** |
| Multi-model debate (evaluator explicitly challenging generator) | **Does not exist.** Evaluator scores independently but does not converse with the generator. |

---

## Explicit non-goals for this pass

Per the owner's own instruction ("do not destroy working functionality")
and basic engineering judgment even under an uncapped scope:

- **The 12-stage orchestrator is not being replaced with a 15-stage one.**
  The stage *names* used in the demo narrative can expand; the actual
  execution path through `ExecutionGate` is not being rewritten four days
  before a deadline when it is the one thing proven to work live, repeatedly,
  today.
- **`RiskLevel` is not being expanded from 3 tiers to 5** inside the
  enforcement logic itself. A cosmetic 5-tier *display* score can be
  computed from real signals (below) without touching the actual gate
  decision, which stays exactly as tested.

---

## Implementation plan for this pass (P0–P1 only, honestly scoped)

1. **`app/beastmode/contracts.py`** — formal `CapabilityContract`: declared
   I/O shape, permission manifest (`network`, `filesystem`, `credentials`,
   `subprocess`), sandbox resource profile. Derived from data the pipeline
   already produces (AST findings, risk field); does not change what the
   AST screen or sandbox actually enforce.
2. **`app/beastmode/red_team.py`** — a **live, narratable runner** over the
   REAL adversarial tests in `tests/test_adversarial.py`, plus genuinely
   new attack vectors not yet covered (fork-bomb pattern, resource
   exhaustion pattern), producing a scorecard. Calls real test logic;
   does not simulate results.
3. **`app/beastmode/ledger_chain.py`** — SHA-256 hash-chains the real
   evolution events already in Firestore. Additive: a new field per event,
   a verifier function, a migration for existing events. Does not replace
   `firestore_store`.
4. **`app/beastmode/risk_score.py`** — a **display-layer** 0–100 score
   computed from real signals already produced (AST findings count,
   sandbox pass/fail, evaluator score, network/credential flags). Feeds
   the UI only; the actual ALLOW/APPROVAL_REQUIRED/PROHIBITED decision
   remains exactly the tested `Enforcement`/`RiskLevel` logic.

Each ships with real tests, run against the full 280-test baseline before
and after, on this branch only.
