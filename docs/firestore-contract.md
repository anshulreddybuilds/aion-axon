# Firestore Contract — the interface between Session A and Session B

**This file is the boundary.** Session A (core) WRITES these documents.
Session B (Holo-Deck UI) READS them with live listeners and writes nothing
except approval decisions via the HTTP API.

Freezing this first is what lets both sessions work in parallel without
waiting on each other. **Neither session may change a field name here
without telling the other** — a rename breaks the UI silently, because a
missing field renders as blank rather than as an error.

Field names below are what the code writes TODAY, verified against
`app/memory/firestore_store.py`. Where they differ from the Notion plan,
reality wins and the deviation is noted.

---

## `approval_requests/{request_id}`

The Holo-Deck approval card reads this.

> Notion §5 calls this `approvals/`. The code has always used
> `approval_requests/`. Keeping the code's name; renaming a working
> collection mid-hackathon buys nothing.

```json
{
  "action": "purchase item",
  "risk": "LOW | MEDIUM | HIGH",
  "reason": "Human approval is required before execution.",
  "status": "PENDING | APPROVED | REJECTED",
  "created_at": "ISO-8601 UTC",
  "decided_at": "ISO-8601 UTC | absent while PENDING",
  "decided_by": "owner | absent while PENDING",
  "approved": true
}
```

Live query for the approval card:
`where("status", "==", "PENDING")`

---

## `audit_events/{auto_id}`

The audit feed. Append-only. Never updated, never deleted.

```json
{
  "event_type": "GUARDIAN_DECISION | ACTION_EXECUTED | ACTION_FAILED | EXECUTION_BLOCKED | APPROVED_EXECUTION_BLOCKED | APPROVED_EXECUTION_AUTHORIZED | APPROVED_EXECUTION_GUARDIAN_RECHECK | HUMAN_APPROVAL_DECISION | CAPABILITY_GAP",
  "timestamp": "ISO-8601 UTC",
  "action": "string",
  "risk": "LOW | MEDIUM | HIGH",
  "decision": "ALLOW | APPROVAL_REQUIRED | REFUSE",
  "reason": "string"
}
```

Fields beyond `event_type` and `timestamp` vary by event type. **The UI
must tolerate missing fields** rather than assume every event carries
every key.

The red refusal flash triggers on `decision == "REFUSE"`.

---

## `missions/{mission_id}`

Mission status panel.

```json
{
  "mission_id": "uuid",
  "workflow_id": "uuid",
  "request": "the messy human request",
  "mode": "planned | absent for direct tool missions",
  "goal": "planner's one-line goal",
  "status": "EXECUTING | AWAITING_APPROVAL | BLOCKED | COMPLETED | REFUSED | FAILED",
  "plan_document": { "goal": "...", "steps": [ ... ] },
  "step_results": [
    {
      "step": 1,
      "description": "...",
      "tool": "calculator | null",
      "action": "...",
      "risk": "LOW",
      "kind": "READ_ANALYZE | EXTERNAL_EFFECT",
      "status": "EXECUTED",
      "result": { },
      "at": "ISO-8601 UTC"
    }
  ],
  "next_step_index": 0,
  "steps_completed": 0,
  "steps_total": 0,
  "approval_request_id": "uuid | null",
  "blocked_on": {
    "step": 2,
    "description": "...",
    "missing_capability": "write_brief | null",
    "reason": "...",
    "detected_at": "ISO-8601 UTC"
  },
  "created_at": "ISO-8601 UTC",
  "updated_at": "ISO-8601 UTC"
}
```

---

## `system/control`

The kill switch. Single document.

```json
{
  "kill_switch": false,
  "reason": "string | null",
  "updated_at": "ISO-8601 UTC"
}
```

---

## PLANNED — Session A writes these, Session B builds against this shape

Not yet implemented. **Session B may build the panels now**; they will be
empty until Session A ships them, and an empty panel is correct behaviour,
not a bug.

### `capabilities/{capability_id}`

```json
{
  "name": "fx_normalize",
  "description": "...",
  "state": "BLOCKED | LEARNING | VALIDATING | READY | DEPRECATED | DISABLED",
  "risk": "LOW | MEDIUM | HIGH",
  "implemented": true,
  "version": 1,
  "autonomy_pct": 32,
  "success_rate": 0.0,
  "intervention_rate": 0.0,
  "created_at": "ISO-8601 UTC",
  "verified_at": "ISO-8601 UTC | null"
}
```

The capability counter reads `count()` of this collection.
The autonomy gauge reads `autonomy_pct`.

### `evolution_events/{event_id}`

One per acquisition. Powers "WHY THIS SKILL EXISTS" (the Skill Passport).

```json
{
  "capability_id": "fx_normalize",
  "before": "AION could not normalize currency.",
  "change": "Acquired fx_normalize capability.",
  "reason": "Mission step 3 blocked on FX normalization.",
  "after": "AION can normalize currency. Registry 12 -> 13.",
  "research_citations": [ { "title": "...", "uri": "https://..." } ],
  "test_results": { "passed": true, "details": "..." },
  "approver": "owner",
  "approved_at": "ISO-8601 UTC",
  "autonomy_before": 32,
  "autonomy_after": 47,
  "timestamp": "ISO-8601 UTC"
}
```

**`research_citations` may be an empty list.** Search grounding is quota
limited on the free tier; when it degrades, the citation list is empty and
`grounded` is false. The UI must show "no sources — ungrounded" rather
than hide the section, because a Skill Passport that silently omits its
RESEARCH step is worse than one that admits it.

---

## Live URLs

- Core API: `https://aion-core-638298765129.asia-south1.run.app`
- Sandbox: `https://aion-sandbox-638298765129.asia-south1.run.app`
- GCP project: `aion-axon-2026`, Firestore Native, `asia-south1`

## HTTP endpoints the UI calls

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | LIVE badge + kill switch state + capability count |
| GET | `/capabilities` | counts + capability list |
| POST | `/missions/planned` | start a planned mission |
| GET | `/missions/{id}` | mission detail |
| POST | `/missions/{id}/resume-planned` | resume after approval |
| GET | `/approvals/pending` | pending approvals |
| POST | `/approvals/{id}/decide` | approve/reject |
| GET/POST | `/killswitch` | read / set kill switch |

**Cloud Run returns HTTP 411 on a POST with no body.** Always send a
body, even `{}`. This has already bitten once.
