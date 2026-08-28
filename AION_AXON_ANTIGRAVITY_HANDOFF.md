# AION AXON — ANTIGRAVITY HANDOFF

This file exists so the project continues with zero loss of context in Antigravity or any other coding agent. Read this AND `AION_AXON_CONTINUATION_HANDOFF.md` first — they agree; this file is the short migration summary, the other is the detailed history. (Note: the "nearing its usage limit" framing from an earlier pass turned out not to block continuing — a later session picked this straight back up.)

## Current HEAD
Superseded — see `AION_AXON_CONTINUATION_HANDOFF.md`'s Update 5 and `git log`. This file's own P1 section below is now stale in the same way the rest of this paragraph is; read Update 5, not this file, for the current P1 state.

## Repository state
Clean, pushed to `origin/feat/beastmode-core-oagiwb` (this branch superseded `feat/beastmode-core` as the active development branch — see `git branch -a`).

## Project status
Technical completion reached. Distributed Firestore concurrency is now VERIFIED (see the "ONE remaining technical gap" section below — it is no longer open, kept here with a correction rather than deleted so the history stays honest).

## Completed systems
- Evaluator (structured JSON output, fail-closed validation)
- AST firewall (reflection/import/execution blocking, adversarially tested)
- API hardening (full route inventory, real bugs found + fixed: invalid risk enum, NaN/Infinity, whitespace-only input, body size limit, free-text max lengths)
- Authentication (owner bearer token, constant-time comparison, edge cases covered)
- Approval/install governance (server-side re-read, cross-capability binding proven impossible)
- Mission idempotency / replay protection
- Kill switch (propose/install/decide/execution_gate, including monitor execution)
- Monitor governance (kill-switch-blocked-tick failure-counter bug found + fixed)
- Ledger integrity (deterministic ordering fixed, tamper-evident forensic coverage)
- Rate limiting (per-process, LLM-calling routes)
- In-process concurrency (real threading tests, not sequential tests mislabeled)
- State machine (formal transition table, judge-visible endpoint)
- Judge Mode (backend `/beastmode/state-machine` + frontend `StateMachineCard`)
- Frontend reconciliation (`ALREADY_INSTALLED` handling, no optimistic READY)
- Test-flake fix (root-caused as a stale hardcoded `write_brief` assumption, not real flakiness — genuinely fixed, not just documented around)

## Current tests
Backend: 531 passed / 1 skipped / 0 failed
Frontend: 24 passed
Build: PASS

**No known test flakes.**

## ONE remaining technical gap — CLOSED (see AION_AXON_CONTINUATION_HANDOFF.md Update 5)
Was: distributed Firestore concurrency, unverified. Now: verified for real
against a real Firestore emulator, and a real race was found and fixed in
`app/synapse/engine.py`'s `install()` (a genuine TOCTOU gap — 10/10
concurrent installs succeeded before the fix, over real networked
Firestore, not a toy in-process test). Do not re-open this as "still
blocked" — a later session (different environment, Java present) closed
it. Full detail, including an honestly-disclosed local-emulator
contention caveat that does not change the verdict, is in
`AION_AXON_CONTINUATION_HANDOFF.md`'s Update 5.

## Why it was previously blocked, and how that changed
No Java on PATH in the earlier Windows sandbox (confirmed repeatedly across sessions). Docker Desktop's backend crashed on launch there too. Neither was assumed; both were genuinely attempted and failed with concrete evidence. A later session ran in a **different, Linux container environment** where Java (OpenJDK 21) was already present — the blocker was environment-specific, not a property of the project itself.

## Existing scaffold
`tests/test_concurrency_firestore_emulator.py` — uses the real `google-cloud-firestore` `Client.transaction()` API. Now run for real and passing. `tests/test_concurrency_firestore_emulator_engine.py` (new) exercises the actual `engine.py` code path the same way. Both skip cleanly (not fake) when their env-var gates aren't met. Exact run commands are in each file's own docstring, including how the emulator jar was fetched without `gcloud` (via `firebase-tools`'s `setup:emulators:firestore`, since `dl.google.com` was blocked by that environment's proxy but `storage.googleapis.com` was not).

## Next real action
None required for P1 — closed. See `AION_AXON_CONTINUATION_HANDOFF.md` for what else is open.

## Rate limiting limitation
Per-process, in-memory. Not a globally distributed Cloud Run rate limiter. Never describe it as distributed.

## Ledger limitation
Tamper-evident, not tamper-proof. Local seal file, not an immutable remote trust anchor. Never upgrade this claim.

## Production safety
No push to production Firestore, no deploy, no production ledger changes, no ledger reseal, no Mission #2, no production approval clicked. (The P1 fix above touched real code, pushed to the git branch, but every test run that verified it ran against a local emulator with no GCP credentials present in that environment — confirmed before running, not assumed.)

## Notion Source of Truth
https://app.notion.com/p/3c782243366881aea778e04c35afceba — "🧭 AION AXON — Source of Truth", nested under the existing "AION Axon — Hackathon Master Plan" page. Repository + verified tests + this handoff take precedence over Notion if they ever disagree; update Notion to match, never the reverse.

## Google/Devpost credit
Approximately $150 available. Not spent this pass. Treat as a project resource requiring an architecture/ROI decision before any spend — candidate future uses: CI/CD, Cloud Run, Firestore, Gemini/API workloads, observability, demo infrastructure. No spending decision has been made.

## Antigravity instructions
Continue from current HEAD. Read this file and `AION_AXON_CONTINUATION_HANDOFF.md` first (Update 5 there has the full P1 story). Do not repeat completed audits. Do not rewrite working systems. The distributed concurrency test HAS now been run and passed, and a real gap it found in `engine.py` has been fixed and verified — do not treat P1 as open again without new evidence. Do not deploy until explicitly authorized by the owner.
