# AION Axon — Independent Code Audit

**23 Aug 2026 · 7 days to deadline (31 Aug, 5pm PDT)**

Audited by reading the code and querying the live services, not by reading
the project's own documentation. Every claim below was checked; where a
claim could not be verified, that is stated rather than assumed.

---

## Verdict in one line

**The system is real and the engineering is sound. The submission is not
ready, and three of the blockers have nothing to do with code.**

---

## Part 1 — What holds up

These were checked in source, not taken from docs.

### The central governance claim is true

`ExecutionGate` really is the only path to tool execution. Verified by
tracing every caller:

- `execution_gate.execute()` and `execute_approved()` are called from
  exactly one file — `app/workflows/orchestrator.py`
- The only two `registry.get()` calls both live in that orchestrator, and
  both feed the gate
- No route, service or agent invokes a registered tool directly

A governance check that can be bypassed by choosing a different endpoint is
not a check. This one cannot be.

### Nothing installs without a human, enforced not intended

`app/synapse/engine.py::install()` re-reads the approval from Firestore and
refuses if it is absent or not `APPROVED`:

```
approval = firestore_store.get_approval(request_id)
if approval is None or approval.get("status") != "APPROVED":
    return {... "reason": "Human approval has not been granted."}
```

It trusts the record of the decision, not the proposal that asked for it.
That distinction is the difference between a gate and a formality.

### Generated code never runs beside the credentials

`_sandbox_proxy()` confirms an installed capability is a proxy that calls
the sandbox — before AND after approval. Approval means the owner accepted
the capability, not that the code earned a seat next to the secrets.

### The trust boundary holds from both sides, live

| Check | Result |
|---|---|
| `GET /sandbox/proof` (through core) | `ZERO_CREDENTIALS`, 0 credentials, `service_account_roles: none granted` |
| Sandbox URL from the public internet | **HTTP 403** |

### The test suite is honest

- **280 tests, 22 files, 542 assertions**
- **Zero vacuous tests** — every single test contains an assertion or an
  expected-raise. This was checked mechanically, not sampled.
- **10 adversarial tests** that genuinely attack the governance rather than
  confirm it, including exfiltration payloads, persuasion phrasings, a
  planted secret in the sandbox scan, and kill-switch coverage across
  every execution path.
- A pre-push hook runs the full suite and refuses a red push.
- **CI green on all 5 most recent pushes.**

### Repo hygiene

- **No secrets committed.** No `.env`, no key material, no private key
  patterns in any tracked file.
- **Zero `TODO`, `FIXME`, `HACK` or `XXX` markers** in the entire codebase.
  Unusual, and a genuine signal.
- 115 commits, clean working tree, ~6,400 lines of application Python.

---

## Part 2 — Blockers, in order of how badly they hurt

### 🔴 1. Judges will land on the wrong branch

**This is the worst problem found, and it is silent.**

| | |
|---|---|
| GitHub default branch | **`feat/end-to-end-workflow`** |
| All the work is on | `feat/core-intelligence` |
| `main` is behind by | **98 commits** |
| App files on `main` | **24** |
| App files on the working branch | **44** |

A judge opening the repository sees a branch that is missing roughly **45%
of the application**. They will not know to switch branches, and nothing on
the landing page tells them to.

Everything else in this audit is irrelevant if this is not fixed. It is
also a five-minute fix.

### 🔴 2. The repository is PRIVATE

Judges cannot see any branch. Access has not been granted.

### 🔴 3. No demo video exists

30% of the total score, and a hard rulebook requirement (public YouTube,
≤4:00, must show the backend running on Google Cloud). Nothing filmed.

### 🔴 4. Devpost submission not filed

Text is drafted and verified in `docs/devpost.md`. It has not been
submitted. Devpost allows editing until the deadline, so filing early costs
nothing and removes the largest single point of failure.

### 🟠 5. The public site is stale and carries a known bug

| | |
|---|---|
| Production last released | **22 Aug 13:18** |
| Bundle served | `index-QKRdI3jO.js` |
| Current build | `index-BWayAUp7.js` |

The Evidence tab bug — where the capability passport was erased by the
3-second poll — was fixed today in `web/src/App.jsx`, which is the
production surface. **That fix was never deployed.** Anyone visiting
`aion-axon-2026.web.app` today and clicking Evidence sees the bug.

Only preview channels were deployed all day.

### 🟠 6. Four UI surfaces, no decision

`/` (v1), `/v2`, `/v3`, `/v4` all exist and all work. Only v1 is on the
production URL. The demo cannot be filmed until one is chosen, and
`docs/demo-script.md` still describes the **old terminal/curl demo** —
wrong shots, wrong order, and its opening beat does not exist on the newer
surfaces.

### 🟠 7. The v4 approval panel is unproven

Built today. It renders, polls the correct endpoint, and shows the empty
state correctly. It has **never been exercised with a real pending
approval**, because nothing can enter the queue while generation quota is
exhausted. This is the single most important interaction in the product and
it is untested end to end.

---

## Part 3 — Known limitations, correctly reported by the system

These are not defects. They are recorded here because the system already
reports them honestly, and that honesty is worth preserving under pressure.

- **Search grounding is tier-blocked, not quota-blocked.** Proven by test:
  a fresh API key generated fine and grounding 429'd on its first call with
  no `quotaId`, no `quotaValue` and no retry delay. No number of new keys
  fixes it; only a billed tier does. Research therefore returns `DEGRADED`
  with **zero citations**, and the spine reports **92%, not 100%**. A
  system reporting 100% here would be lying about itself.
- **Voice input is unproven on this hardware** and is rendered disabled
  with the reason shown, rather than simulated.
- **Policy matching is lexical, not semantic.** Novel phrasing can miss.
- **The AST screen can be evaded** by sufficiently indirect code. Neither
  layer is trusted alone — which is why the sandbox holds nothing worth
  stealing.
- **1 of 2 background monitors is disabled** (`US births yearly watch`,
  disabled 20 Aug). The other is active with 80 runs.
- **ADK planner token usage is not captured** and is reported as
  `UNMEASURED` rather than estimated.

---

## Part 4 — What I got wrong today, recorded

Three times today a browser-based diagnosis was wrong because the test
browser pane was not being composited (`document.hidden === true`), so
`requestAnimationFrame` never fired and no animation ran:

1. Node pacing "measured" at 2000ms when the code says 1500ms — actually
   background timer throttling.
2. Screenshots failing.
3. The trace accordions reported BROKEN — disproven by the owner's own
   screenshot showing them working correctly.

**Static source audits in this document are environment-independent and
stand. Anything about animation or timing needs a visible browser to
confirm.** The dead-button findings (9 across v2 and v4, all fixed) were
static and are reliable.

---

## Part 5 — The order to do things

1. **Point the GitHub default branch at the branch with the code**, or
   merge into `main`. Five minutes. Nothing else matters until this is done.
2. **Add the judges to the private repo** (or make it public at submission).
3. **Deploy the current build to production** so the public URL stops
   serving a known bug.
4. **File the Devpost draft**, incomplete. It can be edited until the
   deadline.
5. **Tomorrow 12:30 IST**: one live acquisition NOT filmed, to prove the
   approval panel works with a real request. ~4 of 20 calls.
6. **Then film**, with ~16 calls left — four attempts.
7. Rewrite `docs/demo-script.md` for whichever surface is chosen. Costs no
   quota; can be done tonight.

---

## Closing

The hard part is done and it is genuinely well built. The governance is not
decoration: it is enforced in code, covered by adversarial tests, and holds
up when queried live. Very little of what remains is engineering.

The risk now is losing on paperwork — a stale default branch, a private
repo, an unfiled form and a missing video — while sitting on a system that
would score well if judges could actually reach it.
