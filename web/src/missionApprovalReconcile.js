/**
 * Reconciles Mission Theater's local AcquisitionRecord snapshot with the
 * real outcome of a decide()/install() cycle.
 *
 * `record` is captured once from the original POST /synapse/propose
 * response and never re-fetched. Without this, the Proof of Action panel
 * keeps rendering record.status/record.stage = "AWAITING_APPROVAL" even
 * after the backend has actually decided and installed -- the backend
 * moved on, the UI snapshot didn't (found during Mission #1, the first
 * real production mission: detect_expense_anomalies installed and
 * READY server-side while the page still showed AWAITING_APPROVAL).
 *
 * Reuses the backend's own terminal vocabulary rather than inventing one:
 * "INSTALLED" is api.install()'s own success status (app/synapse/engine.py
 * install()'s return value), "REJECTED" is decide()'s own reject status
 * (app/api.py's decide_approval), and "FAILED" is already a recognized
 * terminal status in deriveStages() (missionStages.jsx). Never fabricates
 * a success the install call didn't actually confirm.
 */
export function reconcileRecord(record, { approved, installResult }) {
  if (!approved) {
    return { ...record, status: "REJECTED", stage: "REJECTED" };
  }

  if (installResult?.status === "INSTALLED") {
    return { ...record, status: "INSTALLED", stage: "INSTALLED" };
  }

  // Approval succeeded but install did not confirm -- never show
  // INSTALLED/READY on an unconfirmed install. Surface whatever real
  // reason the backend gave (FAILED: unknown capability, or
  // APPROVAL_REQUIRED if a race meant install() re-read a non-APPROVED
  // decision), not a fabricated one.
  return {
    ...record,
    status: "FAILED",
    stage: "FAILED",
    reason:
      installResult?.error ||
      installResult?.reason ||
      "Install did not confirm success.",
  };
}
