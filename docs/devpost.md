# Devpost submission text — AION Axon

Paste-ready. Category: **Taskmaster**.
Every number here is verifiable in the repo or against the live URL.

---

## Elevator pitch (200 chars)

A governed agent that acquires the capabilities it lacks — researching,
generating and sandbox-testing new tools, then earning human permission to
install them, and losing autonomy when it gets things wrong.

---

## Inspiration

Most agents can execute tools. The interesting failure is what happens when
the tool they need **doesn't exist**.

There are two usual answers and both are bad. The agent stops and a human
writes the missing code — which is just software development with extra
steps. Or the agent improvises and hallucinates a result it cannot actually
produce. The second is worse, because it looks exactly like success.

We wanted a third answer: let the agent **build the missing capability**, but
never let it decide on its own that the result is trustworthy. That turns the
interesting question from "how autonomous can it be?" into "how does it
*earn* autonomy, and how does it lose it?"

---

## What it does

AION Axon takes a messy multi-step request, plans it, and executes it step by
step through a single governed gate. When it hits a step it cannot do:

1. **GUARDIAN pre-screens the need** — a request for a credential-reading
   capability is refused at the doorway, before a single token is spent.
2. **RESEARCH** — Google Search grounding, citations stored as evidence.
3. **GENERATE** — Gemini writes a candidate capability.
4. **SAFETY SCREEN** — an AST walk rejects `os`, `subprocess`, `eval`,
   dunder access. The sandbox answers "does this work"; the screen answers
   "should we run it at all".
5. **SANDBOX TEST** — the candidate runs in a second Cloud Run service that
   holds zero credentials and zero IAM roles.
6. **EVALUATE** — Gemma scores whether the test output actually demonstrates
   the capability, or reports UNSCORED.
7. **GUARDIAN SCREEN**, then **HUMAN APPROVAL** — the pipeline stops here,
   always.
8. **INSTALL → EVOLUTION EVENT** — and the originally blocked mission
   **resumes and finishes itself**.

Two properties are enforced by tests rather than intention:

- **Nothing installs without an explicit human yes.** `install()` re-reads the
  approval from Firestore rather than trusting the proposal record — the
  passport says what was *proposed*, not what the owner *decided*.
- **Generated code never runs inside the credentialed service.** Not during
  testing, and not after approval. An installed capability is a proxy that
  calls the sandbox. Approval means the owner accepted the capability, not
  that the code earned a seat beside the secrets.

### Autonomy that can go down

This is the part we haven't seen elsewhere. Each capability carries an
autonomy score. Verified success promotes it (+15); a contradiction between
its claim and independent ground truth demotes it (−18). **Demotion is larger
than promotion on purpose — trust should be slower to earn than to lose.**
Below 40%, the Guardian demands human verification for work the capability was
trusted with yesterday. Autonomy caps at 95%, because a capability that needs
no oversight ever is a claim no evidence supports.

### Every refusal cites a policy

Seven policies, deny-by-default. "The agent said no" is an opinion; **"the
agent refused under G-04"** is a decision a human can audit and appeal.
Prohibited policies cannot be satisfied by approval — if approval could unlock
it, it would be a permission, not a prohibition. G-06 makes the override
attempt itself a refusal, because a guardrail you can talk out of is a
suggestion.

---

## How we built it

**Google tech used, all of it load-bearing:**

| Technology | Role |
|---|---|
| **Gemini 3.6 Flash** | Mission planning, capability generation, research |
| **Google ADK 2.7** | `Runner` + `InMemorySessionService` drive planner agents constrained by `output_schema` |
| **Gemma 4** (`gemma-4-26b-a4b-it`) | Second-opinion evaluator scoring candidate code |
| **Google Search grounding** | Research citations stored in the Skill Passport |
| **Cloud Run ×2** | `aion-core` (credentialed) and `aion-sandbox` (zero credentials) |
| **Firestore** | capabilities, evolution_events, audit_events, missions, approvals, monitors |
| **Secret Manager** | API key for core only; the sandbox is given none |
| **BigQuery** | Public-dataset analysis, read-only and byte-capped |
| **Cloud Scheduler** | Ticks background monitors every 15 minutes |
| **Cloud Build** | Builds both services from source |

**Data sources:** BigQuery public datasets (`bigquery-public-data.usa_names`)
and the public web via Google Search grounding. No private or personal data is
used anywhere.

**The security decision we're most pleased with:** the sandbox authenticates
by *identity*, not by a shared secret. `aion-core` mints an OIDC token from
the Cloud Run metadata server, so the sandbox can require authentication while
still holding no credential of its own. `GET /sandbox/proof` returns the
sandbox's own environment scan **through core** — one response proving that
core *can* reach it and the internet *cannot*.

---

## Accomplishments

Verified against the deployed services, not locally:

- **Two capabilities acquired end to end** — `convert_currency_amount` and
  `detect_yoy_anomalies` — each researched, generated, screened,
  sandbox-tested, evaluated, human-approved, installed, and recorded as an
  Evolution Event with full chain of custody.
- **A real finding in real data.** BigQuery pulled 9 years of US birth
  records (88.8 MB scanned); the capability acquired minutes earlier flagged
  2006, 2009 and 2010 as anomalies. The 2009–2010 drops match the documented
  post-2008 decline in US births — a result checkable against the outside
  world rather than taken on trust.
- **The trust boundary holds from both sides.** Core reads
  `ZERO_CREDENTIALS`; the public internet gets `HTTP 403` on the same URL.
- **Acquired capabilities survive cold starts.** Cloud Run scales to zero;
  the registry rehydrates from Firestore before serving traffic.
- **205 tests**, including 19 adversarial ones that try to break the
  governance rather than confirm it.

---

## Challenges we ran into

**The sandbox became a liability the moment it became useful.** Adding
`/execute` turned a harmless public service into an arbitrary-code-execution
endpoint on our own bill. Closed by removing public invoke and granting only
core's service account.

**Acquired capabilities evaporated between demo takes.** Firestore recorded a
capability as READY while the runtime registry — process memory on a
scale-to-zero service — had lost it. Every unit test passed throughout.

**Free-tier quota is the real constraint.** Search grounding and generation
share a daily cap. We chose to report `DEGRADED` and `BLOCKED` honestly rather
than fabricate a citation or a score to make a demo run green.

---

## What we learned

These are the findings we'd actually pass to someone building the same thing.

**1. Every serious defect was found by running it, not by testing it.**
Capabilities vanishing on restart, the publicly executable sandbox, a missing
CORS layer, two separate governance checks wired into only one of two
execution paths — all found live. The 205 tests are real and they hold, but
not one of them caught the thing that would have broken the demo.

**2. "Two paths, one check" bit us twice.** Verification was wired into the
planned-mission path but not the direct one; later, autonomy supervision had
exactly the same shape. Each path passed its own tests. A governance check
that depends on which endpoint the caller used is not a check — and we now
look for that pattern deliberately whenever a new check is added.

**3. Approval fatigue is a governance failure, not a governance feature.**
Our first version asked the owner to approve a freshly installed capability
twice in a row, and a later bug re-asked the same question forever because the
answer was never recorded. An owner asked constantly stops reading, which
defeats the gate entirely. We now treat a human's reviewed approval as
evidence, and we show the *actual generated source* in the approval card
rather than a description of it — collapsed by default, because an owner shown
a wall of code on every card learns to scroll past it.

**4. An unmeasured number must never become a plausible one.** Our telemetry
counts a model call with no `usage_metadata` as UNMEASURED rather than
assigning an estimate. An inferred token count reads exactly like a measured
one and would quietly corrupt every cost figure downstream — including any we
put in this submission.

---

## What's next

- Semantic policy matching (today it is lexical, so novel phrasing can miss).
- Retry-with-feedback when a candidate fails its own tests.
- Firestore → BigQuery export for self-improvement analytics.
- Multi-owner approvals and a policy editor.

---

## Honest status

Documentation honesty is explicitly judged, and a system built around evidence
should hold itself to the standard it applies to its own agent.

**Implemented and live:** governed execution, capability gap detection,
acquisition loop, AST screening, sandbox execution, Gemma evaluation, policy
catalog, human approval with code review, install and rollback, evolution
events, autonomy ledger, mission auto-resume, background monitors, telemetry.

**Partial or blocked:**

- **Search grounding is free-tier quota-blocked.** Acquisition research
  currently returns `DEGRADED` with **zero citations**, and the Skill Passport
  shows "ungrounded" rather than a fabricated source.
- **Autonomy promotion is currently driven by human verification**, not by
  grounded research evidence. Both directions of the arc are demonstrable
  live; automated promotion from citations is untested for the same quota
  reason.
- **A third planned acquisition (a background-monitor skill) was not
  acquired.** The monitor infrastructure is built, tested and running on a
  schedule; the acquisition itself hit the daily quota cap.
- **Policy matching is lexical, not semantic**, and **the AST screen can be
  evaded** by sufficiently indirect code. Neither layer is trusted alone —
  that is why the sandbox holds nothing worth stealing.
- **The Holo-Deck UI is built but not yet hosted.** All state is available
  over the API.
- **ADK planner token usage is not captured**, because the planner runs
  through ADK rather than a direct GenAI call.

---

## AI assistant disclosure

This project was built during the submission period (first commit 19 Aug 2026)
with substantial use of **Claude Code** as an AI coding assistant, which the
official rules expressly permit. No pre-existing code was incorporated.
Architectural and governance concepts — deny-by-default approval gating,
evidence-gated autonomy — draw on the author's earlier private work; **no code
from it was copied into this repository.**

All design decisions, approvals and deployments were made by the author. Every
capability installed by SYNAPSE required an explicit human approval, including
during the demo.

---

## Built with

`gemini` `google-adk` `gemma` `google-cloud-run` `firestore` `bigquery`
`secret-manager` `cloud-scheduler` `cloud-build` `python` `fastapi` `react`
`vite` `tailwindcss` `framer-motion`
