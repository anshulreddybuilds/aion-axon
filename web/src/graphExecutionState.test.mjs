import assert from "node:assert/strict";
import { nodeStatuses } from "./graphExecutionState.js";

let failures = 0;
function test(name, fn) {
  try {
    fn();
    console.log(`ok - ${name}`);
  } catch (err) {
    failures++;
    console.error(`FAIL - ${name}`);
    console.error(err);
  }
}

const stepNumberById = new Map([["a", 1], ["b", 2], ["c", 3]]);
const nodes = [{ id: "a" }, { id: "b" }, { id: "c" }];

test("no mission result yet -> empty map, nothing invented", () => {
  const map = nodeStatuses({ nodes, stepNumberById, missionResult: null });
  assert.equal(map.size, 0);
});

test("a completed mission marks every executed step ok", () => {
  const missionResult = {
    status: "COMPLETED",
    step_results: [
      { step: 1, status: "EXECUTED" },
      { step: 2, status: "EXECUTED" },
      { step: 3, status: "EXECUTED" },
    ],
  };
  const map = nodeStatuses({ nodes, stepNumberById, missionResult });
  assert.equal(map.get("a").tone, "ok");
  assert.equal(map.get("b").tone, "ok");
  assert.equal(map.get("c").tone, "ok");
});

test("a step with a real gap is BLOCKED, later steps are 'not yet run' not fabricated as failed", () => {
  const missionResult = {
    status: "BLOCKED",
    step_results: [{ step: 1, status: "EXECUTED" }],
    blocked_on: { step: 2, reason: "Capability 'fx_normalize' is not registered." },
    next_step_index: 1,
  };
  const map = nodeStatuses({ nodes, stepNumberById, missionResult });
  assert.equal(map.get("a").tone, "ok");
  assert.equal(map.get("b").tone, "warn");
  assert.match(map.get("b").detail, /fx_normalize/);
  assert.equal(map.get("c").tone, "idle");
});

test("a step suspended for approval is marked AWAITING APPROVAL, not FAILED", () => {
  const missionResult = {
    status: "AWAITING_APPROVAL",
    step_results: [{ step: 1, status: "EXECUTED" }],
    next_step_index: 1,
    approval_request_id: "req-123",
  };
  const map = nodeStatuses({ nodes, stepNumberById, missionResult });
  assert.equal(map.get("b").tone, "warn");
  assert.match(map.get("b").label, /APPROVAL/);
  assert.equal(map.get("c").tone, "idle");
});

test("a real tool failure (not a gap, not approval) is reported danger with the real reason", () => {
  const missionResult = {
    status: "FAILED",
    step_results: [{ step: 1, status: "FAILED", reason: "Capability reported ERROR." }],
  };
  const map = nodeStatuses({ nodes, stepNumberById, missionResult });
  assert.equal(map.get("a").tone, "danger");
  assert.equal(map.get("a").detail, "Capability reported ERROR.");
});

test("a node not part of the last compiled plan is left unmapped, not guessed", () => {
  const staleStepNumberById = new Map([["a", 1]]); // "b"/"c" were added after the last run
  const missionResult = { status: "COMPLETED", step_results: [{ step: 1, status: "EXECUTED" }] };
  const map = nodeStatuses({ nodes, stepNumberById: staleStepNumberById, missionResult });
  assert.equal(map.has("a"), true);
  assert.equal(map.has("b"), false);
  assert.equal(map.has("c"), false);
});

if (failures > 0) {
  console.error(`\n${failures} test(s) failed.`);
  process.exit(1);
} else {
  console.log("\nAll graphExecutionState tests passed.");
}
