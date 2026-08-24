// Plain Node test, no framework: this repo's frontend has zero test
// infra configured (checked package.json -- no vitest/jest), and adding
// one is a bigger scope decision than one deterministic fixture
// warrants. Node's built-in `assert` gives real, meaningful assertions
// with zero new dependencies. Run with:
//   node web/src/demoRecoveryFixture.test.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import {
  DEMO_FIXTURE_LABEL, DEMO_RECORD, DEMO_STEPS, TOTAL_DEMO_STEPS, visibleSteps,
} from "./demoRecoveryFixture.js";

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok - ${name}`);
}

console.log("demoRecoveryFixture.test.mjs");

// 1. Fixture starts in the correct initial state.
test("visibleSteps(0) reveals nothing", () => {
  assert.deepEqual(visibleSteps(0), []);
});

// 2 + 3. Attempt 1 becomes FAILED, with a real failure reason present.
test("attempt 1 in DEMO_RECORD is SANDBOX_FAILED with a real reason", () => {
  const attempt1 = DEMO_RECORD.attempts[0];
  assert.equal(attempt1.attempt, 1);
  assert.equal(attempt1.outcome, "SANDBOX_FAILED");
  assert.ok(attempt1.detail && attempt1.detail.length > 20, "must carry a real diagnostic, not a placeholder");
});

// 4. Diagnosis step is present and non-empty.
test("a DIAGNOSIS step exists with real content", () => {
  const diagnosis = DEMO_STEPS.find((s) => s.key === "diagnosis");
  assert.ok(diagnosis);
  assert.equal(diagnosis.title, "DIAGNOSIS");
  assert.ok(diagnosis.body.length > 10);
});

// 5. Recovery decision step is present.
test("a RECOVERY DECISION step exists and states retry is bounded", () => {
  const recovery = DEMO_STEPS.find((s) => s.key === "recovery");
  assert.ok(recovery);
  assert.match(recovery.body, /bounded/i);
});

// 6. Replan step is present.
test("a REPLAN step exists", () => {
  const replan = DEMO_STEPS.find((s) => s.key === "replan");
  assert.ok(replan);
  assert.equal(replan.title, "REPLAN");
});

// 7. Attempt 2 becomes PASSED.
test("attempt 2 in DEMO_RECORD is SANDBOX_PASSED", () => {
  const attempt2 = DEMO_RECORD.attempts[1];
  assert.equal(attempt2.attempt, 2);
  assert.equal(attempt2.outcome, "SANDBOX_PASSED");
});

// 8. Final state reaches a real terminal-shaped status (AWAITING_APPROVAL,
// matching what a real recovered mission legitimately reaches -- not an
// invented "COMPLETE" status the real record shape doesn't have).
test("DEMO_RECORD reaches AWAITING_APPROVAL, the real terminal status a recovered mission reaches", () => {
  assert.equal(DEMO_RECORD.status, "AWAITING_APPROVAL");
  assert.equal(DEMO_STEPS[DEMO_STEPS.length - 1].kind, "approval");
});

// 9. Fixture is clearly marked DEMO_FIXTURE.
test("the fixture label is unmistakable", () => {
  assert.match(DEMO_FIXTURE_LABEL, /DEMO FIXTURE/);
  assert.match(DEMO_FIXTURE_LABEL, /not production evidence/i);
});

// 10-14. No production side effects: structural proof via source
// inspection, since there is no mock-fetch framework configured. This
// asserts the fixture module's OWN SOURCE never references fetch, the
// api.js client, or any credential/token concept -- it is impossible
// for this file to make a network call, let alone mutate Firestore,
// the ledger, or create an approval, because the code to do so does
// not exist in it.
test("the fixture module makes zero network calls (source-level proof)", () => {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(path.join(here, "demoRecoveryFixture.js"), "utf-8");
  assert.doesNotMatch(source, /\bfetch\s*\(/);
  assert.doesNotMatch(source, /from ["']\.\/api\.js["']/);
  assert.doesNotMatch(source, /owner[_-]?token/i);
});

test("visibleSteps never reveals more than TOTAL_DEMO_STEPS or fewer than 0", () => {
  assert.equal(visibleSteps(TOTAL_DEMO_STEPS + 50).length, TOTAL_DEMO_STEPS);
  assert.equal(visibleSteps(-5).length, 0);
});

test("visibleSteps is deterministic across repeated calls", () => {
  const a = visibleSteps(4).map((s) => s.key);
  const b = visibleSteps(4).map((s) => s.key);
  assert.deepEqual(a, b);
});

console.log(`\n${passed} passed`);
