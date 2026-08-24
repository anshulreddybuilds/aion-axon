// Plain Node test, no framework -- same rationale and style as
// demoRecoveryFixture.test.mjs: this repo's frontend has zero test infra
// configured, and reconcileRecord() is a pure function with no JSX, so a
// framework buys nothing here. Run with:
//   node web/src/missionApprovalReconcile.test.mjs
import assert from "node:assert/strict";

import { reconcileRecord } from "./missionApprovalReconcile.js";

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok - ${name}`);
}

console.log("missionApprovalReconcile.test.mjs");

const AWAITING_RECORD = {
  need: "Review this expense series and flag anything that looks like an anomaly.",
  stage: "AWAITING_APPROVAL",
  status: "AWAITING_APPROVAL",
  approval_request_id: "297bc993-6304-40c7-9b9e-652a91912349",
  candidate: { name: "detect_expense_anomalies" },
  reason: null,
};

// CASE 1: a real INSTALLED confirmation reconciles the record to a
// terminal, non-AWAITING_APPROVAL state -- reusing api.install()'s own
// canonical success status, not an invented one.
test("a real INSTALLED result reconciles status/stage away from AWAITING_APPROVAL", () => {
  const installResult = {
    status: "INSTALLED",
    capability: "detect_expense_anomalies",
    evolution_event_id: "XB418NZfp7zLQQQmXdCk",
    implemented_count: 12,
  };

  const reconciled = reconcileRecord(AWAITING_RECORD, {
    approved: true,
    installResult,
  });

  assert.equal(reconciled.status, "INSTALLED");
  assert.equal(reconciled.stage, "INSTALLED");
  assert.notEqual(reconciled.status, "AWAITING_APPROVAL");
  // Reconciliation must not touch fields it has no new information about.
  assert.equal(reconciled.candidate.name, "detect_expense_anomalies");
  assert.equal(reconciled.approval_request_id, AWAITING_RECORD.approval_request_id);
});

// CASE 2: approval succeeded but install did NOT confirm -- must never
// show an installed/successful state on an unconfirmed install, and must
// surface the real reason rather than a fabricated one.
test("an install failure never reconciles to INSTALLED, and carries the real reason", () => {
  const installResult = { status: "FAILED", error: "Unknown capability." };

  const reconciled = reconcileRecord(AWAITING_RECORD, {
    approved: true,
    installResult,
  });

  assert.notEqual(reconciled.status, "INSTALLED");
  assert.equal(reconciled.status, "FAILED");
  assert.equal(reconciled.reason, "Unknown capability.");
});

test("an APPROVAL_REQUIRED install response (race) also never reconciles to INSTALLED", () => {
  const installResult = {
    status: "APPROVAL_REQUIRED",
    reason: "Human approval has not been granted.",
  };

  const reconciled = reconcileRecord(AWAITING_RECORD, {
    approved: true,
    installResult,
  });

  assert.notEqual(reconciled.status, "INSTALLED");
  assert.equal(reconciled.reason, "Human approval has not been granted.");
});

// CASE 3: a real rejection reconciles to the backend's own REJECTED
// status -- already a recognized terminal in deriveStages() -- and must
// never install.
test("a rejection reconciles to REJECTED and never to an installed state", () => {
  const reconciled = reconcileRecord(AWAITING_RECORD, {
    approved: false,
    installResult: null,
  });

  assert.equal(reconciled.status, "REJECTED");
  assert.equal(reconciled.stage, "REJECTED");
  assert.notEqual(reconciled.status, "INSTALLED");
});

// The function must be pure: it must not mutate its input, since the
// caller passes the previous React state value directly.
test("reconcileRecord does not mutate the input record", () => {
  const before = JSON.stringify(AWAITING_RECORD);
  reconcileRecord(AWAITING_RECORD, {
    approved: true,
    installResult: { status: "INSTALLED" },
  });
  assert.equal(JSON.stringify(AWAITING_RECORD), before);
});

console.log(`\n${passed} passed`);
