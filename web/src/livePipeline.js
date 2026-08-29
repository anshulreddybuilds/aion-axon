/**
 * Turns one real AcquisitionRecord snapshot (from GET
 * /synapse/propose/stream, or the plain POST /synapse/propose result)
 * into the { label, detail, tone } shape the execution-stream UI already
 * renders. Pure and framework-free so it's unit-testable without a
 * browser — see livePipeline.test.mjs.
 *
 * Every field read here comes directly off the record the backend sent;
 * this file adds no numbers, scores, or outcomes of its own. If a field
 * is missing, the label says so rather than inventing a value.
 */

const TERMINAL_TONE_STATUSES = new Set([
  "REFUSED", "REJECTED", "BLOCKED", "FAILED",
]);

export function toneForRecord(record) {
  if (TERMINAL_TONE_STATUSES.has(record?.status)) return "danger";
  if (record?.research?.status === "DEGRADED") return "warn";
  return "ok";
}

const STAGE_TITLES = {
  KILL_SWITCH: "Blocked — kill switch is active",
  GUARDIAN_PRESCREEN: "Guardian pre-screened the request",
  RESEARCH: "Researched an approach",
  GENERATE: "Generated a candidate implementation",
  SAFETY_SCREEN: "Static safety screen",
  SANDBOX_TEST: "Sandbox test",
  EVALUATE: "Independent evaluation",
  GUARDIAN_SCREEN: "Guardian reviewed the built capability",
  AWAITING_APPROVAL: "Stopped — awaiting your approval",
};

function detailFor(record) {
  const stage = record?.stage;

  if (stage === "KILL_SWITCH" || stage === "GUARDIAN_PRESCREEN") {
    if (record.status === "REFUSED") return record.reason || "Refused.";
    if (record.status === "BLOCKED") return record.reason || "Blocked.";
    return "Allowed — proceeding.";
  }

  if (stage === "RESEARCH") {
    const r = record.research || {};
    if (r.grounded) {
      return `${r.source_count ?? 0} source${r.source_count === 1 ? "" : "s"} found.`;
    }
    return r.degraded_reason
      ? `Ungrounded — ${r.degraded_reason}`
      : "Ungrounded — no citations available for this query.";
  }

  if (stage === "GENERATE") {
    if (record.status === "FAILED") return record.reason || "Generation failed.";
    const c = record.candidate;
    return c ? `${c.name} — ${c.description}` : "No candidate produced.";
  }

  if (stage === "SAFETY_SCREEN") {
    const s = record.safety;
    if (!s) return "No safety result recorded.";
    return s.safe
      ? "Passed — no unsafe constructs found."
      : (s.findings || []).join("; ") || "Rejected by the static screen.";
  }

  if (stage === "SANDBOX_TEST") {
    const t = record.tests;
    if (!t) return "No sandbox result recorded.";
    if (t.status === "UNREACHABLE") return `Sandbox unreachable — ${t.reason || "no detail"}.`;
    return t.passed
      ? "Passed its own test in the isolated sandbox."
      : (t.stderr || t.reason || "Failed its own test.").slice(0, 300);
  }

  if (stage === "EVALUATE") {
    const e = record.evaluation;
    if (!e) return "No evaluation recorded.";
    if (e.score == null) return `Unscored — ${e.reason || "no reason given"}.`;
    return `Scored ${e.score}/100 (${e.verdict || "no verdict"}) — ${e.reason || ""}`.trim();
  }

  if (stage === "GUARDIAN_SCREEN") {
    const g = record.guardian;
    if (!g) return "No Guardian decision recorded.";
    return `${g.decision} — ${g.reason || g.policy_title || ""}`.trim();
  }

  if (stage === "AWAITING_APPROVAL") {
    return record.approval_request_id
      ? `Request ${record.approval_request_id.slice(0, 8)} is waiting for a real human decision.`
      : "Waiting for a real human decision.";
  }

  return record?.reason || "";
}

export function describeStage(record) {
  if (!record || !record.stage) {
    return { label: "…", detail: "", tone: "ok" };
  }

  const title = STAGE_TITLES[record.stage] || record.stage;
  return {
    label: title,
    detail: detailFor(record),
    tone: toneForRecord(record),
  };
}

/**
 * Turns a mission's real step_results (from POST /missions/planned or
 * GET /missions/{id}) into the same { label, detail, tone } action-list
 * shape describeStage() above produces -- so a mission that completes
 * entirely by REUSING existing capabilities (no acquisition needed) still
 * shows a real execution trace, not an empty panel. Every field here is
 * read off the step the backend actually ran; nothing is invented for a
 * step that didn't execute.
 */
export function actionsFromMissionSteps(steps) {
  return (steps || []).map((s) => {
    const executed = s.status === "EXECUTED";
    return {
      label: s.tool
        ? `${s.tool} — ${s.description || s.action || ""}`.trim()
        : s.description || s.action || `step ${s.step ?? ""}`.trim(),
      detail: executed
        ? "completed"
        : s.reason || s.status || "not executed",
      tone: executed ? "ok" : "danger",
    };
  });
}
