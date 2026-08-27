/**
 * Shared stage-rendering pieces used by both MissionTheater.jsx (real,
 * live records) and DemoRecoveryMode.jsx (the deterministic fixture).
 * Split out to avoid a circular import between the two — DemoRecoveryMode
 * needs deriveStages()/StageRow but must not import MissionTheater.jsx,
 * which itself imports DemoRecoveryMode.jsx for the LIVE/DEMO toggle.
 */

export const TONE = {
  PASSED: "border-ok/40 text-ok",
  BLOCKED: "border-danger/40 text-danger",
  REFUSED: "border-danger/40 text-danger",
  REJECTED: "border-danger/40 text-danger",
  FAILED: "border-danger/40 text-danger",
  WAITING: "border-warn/40 text-warn",
  DONE: "border-ok/40 text-ok",
  INSTALLED: "border-ok/40 text-ok",
  SKIPPED: "border-edge text-muted",
};

export function StageRow({ label, tone, detail, children }) {
  const cls = TONE[tone] || "border-edge text-muted";
  return (
    <div className={`border rounded px-3 py-2 ${cls.split(" ")[0]}`}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-white/90 tracking-[0.08em]">{label}</span>
        <span className={`text-[9px] tracking-[0.14em] ${cls.split(" ")[1]}`}>{tone}</span>
      </div>
      {detail && <p className="text-[10px] text-muted mt-1">{detail}</p>}
      {children}
    </div>
  );
}

/** Reconstructs the stage-by-stage picture from ONE real terminal record.
 *  Never fabricates a stage the record doesn't evidence. */
export function deriveStages(record) {
  const stages = [];

  if (record.guardian?.decision === "REFUSE" && record.stage === "GUARDIAN_PRESCREEN") {
    stages.push({
      key: "GUARDIAN_PRESCREEN", label: "Guardian pre-screen", tone: "REFUSED",
      detail: `${record.guardian.policy_id || ""} — ${record.reason}`,
    });
    return stages; // pipeline never left the doorway
  }

  if (record.research?.status) {
    stages.push({
      key: "RESEARCH", label: "Research",
      tone: record.research.grounded ? "PASSED" : "WAITING",
      detail: `${record.research.source_count} source(s)${
        record.research.degraded_reason ? ` — degraded: ${record.research.degraded_reason}` : ""
      }`,
    });
  }

  if (record.attempts?.length) {
    record.attempts.forEach((a) => {
      const tone = a.outcome === "SANDBOX_PASSED" ? "PASSED"
        : a.outcome === "SANDBOX_UNREACHABLE" ? "BLOCKED"
        : "FAILED";
      stages.push({
        key: `attempt-${a.attempt}`,
        label: `Generate + sandbox — attempt ${a.attempt}${a.attempt > 1 ? " (retry, fed real stderr)" : ""}`,
        tone,
        detail: a.candidate ? `${a.candidate} — ${a.outcome}${a.detail ? `: ${String(a.detail).slice(0, 160)}` : ""}` : a.outcome,
      });
    });
  } else if (record.candidate) {
    stages.push({
      key: "GENERATE", label: "Generate",
      tone: "PASSED",
      detail: record.candidate.name,
    });
  }

  if (record.safety?.safe !== undefined) {
    stages.push({
      key: "SAFETY_SCREEN", label: "AST static screen",
      tone: record.safety.safe ? "PASSED" : "BLOCKED",
      detail: record.safety.findings?.length ? record.safety.findings.join("; ") : "no findings",
    });
  }

  if (record.tests?.status && !record.attempts?.length) {
    stages.push({
      key: "SANDBOX_TEST", label: "Sandbox",
      tone: record.tests.passed ? "PASSED" : record.tests.status === "UNREACHABLE" ? "BLOCKED" : "FAILED",
      detail: `exit ${record.tests.exit_code ?? "?"}`,
    });
  }

  if (record.evaluation?.status) {
    stages.push({
      key: "EVALUATE", label: "Independent evaluation",
      tone: record.evaluation.status === "SCORED"
        ? (record.evaluation.verdict === "PASS" ? "PASSED" : "REJECTED")
        : "WAITING",
      detail: `${record.evaluation.status}${record.evaluation.score != null ? ` — score ${record.evaluation.score}` : ""}${
        record.evaluation.reason_code ? ` (${record.evaluation.reason_code})` : ""
      }`,
    });
  }

  if (record.guardian?.decision && record.stage !== "GUARDIAN_PRESCREEN") {
    stages.push({
      key: "GUARDIAN_SCREEN", label: "Guardian screen",
      tone: record.guardian.decision === "REFUSE" ? "REFUSED"
        : record.guardian.decision === "APPROVAL_REQUIRED" ? "WAITING" : "PASSED",
      detail: `${record.guardian.policy_id || "no policy matched"}${record.guardian.reason ? ` — ${record.guardian.reason}` : ""}`,
    });
  }

  if (record.status === "AWAITING_APPROVAL") {
    stages.push({
      key: "AWAITING_APPROVAL", label: "Human approval", tone: "WAITING",
      detail: `request ${record.approval_request_id}`,
    });
  } else if (["REJECTED", "REFUSED", "BLOCKED", "FAILED"].includes(record.status)) {
    stages.push({ key: "TERMINAL", label: `Mission stopped — ${record.status}`, tone: record.status, detail: record.reason });
  } else if (record.status === "INSTALLED") {
    // reconcileRecord() (missionApprovalReconcile.js) sets status to
    // INSTALLED after a real approve+install round trip. Without this
    // branch the "Human approval — WAITING" row above just disappears
    // at the exact moment of success and nothing replaces it -- the
    // stage timeline goes visually blank right when the mission
    // actually finished, even though Proof of Action (which reads the
    // same record) correctly shows INSTALLED.
    stages.push({
      key: "INSTALLED", label: "Capability installed", tone: "INSTALLED",
      detail: record.candidate?.name,
    });
  }

  return stages;
}
