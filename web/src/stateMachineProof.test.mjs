// Plain Node test, same style/rationale as demoRecoveryFixture.test.mjs
// and missionApprovalReconcile.test.mjs: zero test framework configured,
// this is pure JS with no JSX, a framework buys nothing here.
//   node web/src/stateMachineProof.test.mjs
import assert from "node:assert/strict";

import {
  checkSelfAuthorizationShortcuts,
  formatPath,
  isLegalTransition,
  SELF_AUTHORIZATION_SHORTCUTS,
} from "./stateMachineProof.js";

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok - ${name}`);
}

console.log("stateMachineProof.test.mjs");

test("formatPath joins states with an arrow", () => {
  assert.equal(formatPath(["A", "B", "C"]), "A → B → C");
});

test("formatPath handles an empty/missing list without throwing", () => {
  assert.equal(formatPath([]), "");
  assert.equal(formatPath(undefined), "");
});

test("isLegalTransition finds a real legal pair", () => {
  const transitions = { AWAITING_APPROVAL: ["APPROVED", "APPROVAL_REJECTED"] };
  assert.equal(isLegalTransition(transitions, "AWAITING_APPROVAL", "APPROVED"), true);
});

test("isLegalTransition correctly reports a missing pair as illegal", () => {
  const transitions = { AWAITING_APPROVAL: ["APPROVED", "APPROVAL_REJECTED"] };
  assert.equal(isLegalTransition(transitions, "AWAITING_APPROVAL", "INSTALLED"), false);
});

test("isLegalTransition never throws on an unknown source state", () => {
  assert.equal(isLegalTransition({}, "NOT_A_REAL_STATE", "INSTALLED"), false);
});

// The actual real transition table, copied from the live backend
// endpoint's response shape (app/beastmode/state_machine.py's
// _TRANSITIONS, as returned by GET /beastmode/state-machine) -- not
// invented, mirrors tests/test_state_machine_api.py's assertions on the
// Python side so both layers agree on the same real data shape.
const REAL_TRANSITIONS = {
  REQUESTED: ["MEMORY_CHECKED", "POLICY_REFUSED"],
  MEMORY_CHECKED: ["PLANNED"],
  PLANNED: ["GENERATING", "QUARANTINED"],
  GENERATING: ["SCREENING", "GENERATION_FAILED"],
  SCREENING: ["SANDBOX_TESTING", "SAFETY_REJECTED"],
  SANDBOX_TESTING: ["EVALUATING", "SANDBOX_FAILED", "SANDBOX_UNREACHABLE"],
  EVALUATING: ["AWAITING_APPROVAL", "EVALUATION_FAILED", "EVALUATION_UNSCORED"],
  EVALUATION_UNSCORED: ["AWAITING_APPROVAL"],
  AWAITING_APPROVAL: ["APPROVED", "APPROVAL_REJECTED"],
  APPROVED: ["INSTALLING", "POLICY_REFUSED"],
  INSTALLING: ["INSTALLED", "INSTALL_FAILED"],
  INSTALLED: ["EXECUTING", "ROLLED_BACK"],
  EXECUTING: ["COMPLETED", "EXECUTION_FAILED"],
  COMPLETED: ["ROLLED_BACK"],
};

test("every self-authorization shortcut this card checks is actually blocked by the real table", () => {
  const results = checkSelfAuthorizationShortcuts(REAL_TRANSITIONS);
  assert.equal(results.length, SELF_AUTHORIZATION_SHORTCUTS.length);
  for (const r of results) {
    assert.equal(r.blocked, true, `${r.from} -> ${r.to} must be blocked but wasn't`);
  }
});

test("the legitimate approval path is NOT flagged as a shortcut", () => {
  // Negative control: AWAITING_APPROVAL -> APPROVED is the real, legal,
  // human-authorized path -- must never appear in the shortcut list.
  const flagged = SELF_AUTHORIZATION_SHORTCUTS.some(
    (s) => s.from === "AWAITING_APPROVAL" && s.to === "APPROVED"
  );
  assert.equal(flagged, false);
});

console.log(`\n${passed} passed`);
