/**
 * Demo Recovery Mode — a deterministic, zero-network fixture.
 *
 * DEMO FIXTURE. Not production evidence. This module makes NO fetch
 * calls, imports nothing from api.js, and touches no Firestore, ledger,
 * approval, or Cloud Run state — it is pure data plus pure functions.
 * Its purpose is narrow: give a judge a reproducible, interactive
 * walkthrough of AION's real failure -> diagnosis -> retry -> success
 * story without needing a live owner-authorized production mission
 * every time one is wanted.
 *
 * The record shape below is not invented -- it mirrors EXACTLY what
 * app/synapse/engine.py's AcquisitionRecord.to_dict() actually returns
 * for a real allow_retry=True acquisition that fails once and recovers
 * (attempts[].outcome values SANDBOX_FAILED/SANDBOX_PASSED, evaluation.
 * reason_code EVALUATOR_SCORED_PASS from app/synapse/evaluator.py). This
 * is deliberate: MissionTheater.jsx's real deriveStages() function is
 * reused UNMODIFIED against this fixture record, so a judge sees the
 * identical rendering a real recovered mission would produce. Only the
 * data source differs, and every screen using it says so.
 */

export const DEMO_FIXTURE_LABEL = "DEMO FIXTURE — deterministic recovery simulation, not production evidence";

export const DEMO_RECORD = Object.freeze({
  need: "detect year-over-year revenue anomalies from monthly totals",
  stage: "AWAITING_APPROVAL",
  status: "AWAITING_APPROVAL",
  mission_id: null,
  research: {
    status: "OK", grounded: true, sources: ["docs.python.org/3/library/statistics.html"],
    source_count: 1, findings: "Use the standard library statistics module for mean/stdev.",
    degraded_reason: null,
  },
  candidate: {
    name: "detect_yoy_revenue_anomalies",
    description: "Flags months where revenue deviates from the prior year by more than one standard deviation.",
    risk: "LOW",
  },
  safety: { safe: true, findings: [] },
  tests: { status: "COMPLETED", exit_code: 0, passed: true, stdout: "OK\n", stderr: "" },
  evaluation: {
    status: "SCORED", model: "gemma-4-26b-a4b-it", score: 88, verdict: "PASS",
    reason: "Test output demonstrates correct anomaly detection on a realistic input.",
    reason_code: "EVALUATOR_SCORED_PASS",
  },
  guardian: {
    decision: "APPROVAL_REQUIRED",
    reason: "Newly generated capability requires human review before installation.",
    policy_id: "INSTALL", policy_title: "Install Review",
  },
  approval_request_id: "demo-fixture-not-a-real-approval-id",
  attempts: [
    {
      attempt: 1, candidate: "detect_yoy_revenue_anomalies", outcome: "SANDBOX_FAILED",
      detail: "AssertionError: expected alert_level='HIGH' for a 2.3-stdev deviation, got 'MEDIUM' -- threshold comparison used > instead of >=, so a boundary value fell through to the wrong bucket.",
    },
    {
      attempt: 2, candidate: "detect_yoy_revenue_anomalies", outcome: "SANDBOX_PASSED",
      detail: null,
    },
  ],
  reason: null,
  started_at: null, // set at demo start, not baked into the frozen fixture
});

/** The narrative-only beats a real AcquisitionRecord has no field for --
 * commentary ABOUT the record, never presented as backend data. Kept
 * separate from DEMO_RECORD so nothing here could be mistaken for a
 * real API response shape. */
export const DEMO_STEPS = Object.freeze([
  { key: "start", kind: "narrative", title: "MISSION START", body: `Need: "${DEMO_RECORD.need}"` },
  { key: "plan", kind: "narrative", title: "PLAN",
    body: "Planner decision: ACQUIRE_NEW, strategy GENERATE_WITH_RETRY. No existing capability matched this need in memory." },
  { key: "attempt1", kind: "stage", title: "ATTEMPT 1", attemptIndex: 0 },
  { key: "diagnosis", kind: "narrative", title: "DIAGNOSIS",
    body: "The sandbox test failed on a boundary value: a 2.3-standard-deviation change should have scored HIGH but scored MEDIUM. Real stderr captured above." },
  { key: "recovery", kind: "narrative", title: "RECOVERY DECISION",
    body: "Retry permitted: YES (bounded, max 2 attempts). Feedback available: YES — the real stderr is fed into the next generation attempt." },
  { key: "replan", kind: "narrative", title: "REPLAN",
    body: "Generation retried with the failure's exact stderr as context, per app/synapse/engine.py's retry-with-feedback loop." },
  { key: "attempt2", kind: "stage", title: "ATTEMPT 2", attemptIndex: 1 },
  { key: "evaluate", kind: "narrative", title: "INDEPENDENT EVALUATION",
    body: `${DEMO_RECORD.evaluation.model} scored the corrected candidate ${DEMO_RECORD.evaluation.score}/100 — ${DEMO_RECORD.evaluation.verdict}.` },
  { key: "approval", kind: "approval", title: "HUMAN APPROVAL REQUIRED" },
]);

/** Pure function: given how many steps have been revealed, return the
 * slice to render. No timers, no side effects -- the calling component
 * owns pacing. */
export function visibleSteps(revealedCount) {
  return DEMO_STEPS.slice(0, Math.max(0, Math.min(revealedCount, DEMO_STEPS.length)));
}

export const TOTAL_DEMO_STEPS = DEMO_STEPS.length;
