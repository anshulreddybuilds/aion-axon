import assert from "node:assert/strict";
import { nodeStatuses, runOutcomeText, toneForMissionStatus } from "./graphExecutionState.js";

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

// ── toneForMissionStatus / runOutcomeText (BUG-011) ─────────────────────

test("toneForMissionStatus: COMPLETED is ok, BLOCKED/AWAITING_APPROVAL/APPROVAL_REQUIRED are warn (not danger), real failures are danger", () => {
  assert.equal(toneForMissionStatus("COMPLETED"), "ok");
  assert.equal(toneForMissionStatus("BLOCKED"), "warn");
  assert.equal(toneForMissionStatus("AWAITING_APPROVAL"), "warn");
  assert.equal(toneForMissionStatus("APPROVAL_REQUIRED"), "warn");
  assert.equal(toneForMissionStatus("FAILED"), "danger");
  assert.equal(toneForMissionStatus("REFUSED"), "danger");
  assert.equal(toneForMissionStatus("REJECTED"), "danger");
});

test("an unrecognized status defaults to warn, never a fabricated red failure", () => {
  assert.equal(toneForMissionStatus("SOMETHING_NEW"), "warn");
  assert.equal(toneForMissionStatus(undefined), "warn");
});

test("runOutcomeText: BUG-011 -- a FAILED mission's real reason is shown, not just the bare status word", () => {
  const result = {
    status: "FAILED",
    step_results: [{ step: 1, status: "FAILED", reason: "Capability reported ERROR." }],
  };
  const text = runOutcomeText(result);
  assert.match(text, /FAILED/);
  assert.match(text, /Capability reported ERROR\./);
});

test("runOutcomeText falls back to error when reason is absent, same reason/error class as BUG-005/007/008/009", () => {
  const result = {
    status: "FAILED",
    step_results: [{ step: 1, status: "FAILED", error: "Approval request not found." }],
  };
  assert.match(runOutcomeText(result), /Approval request not found\./);
});

test("runOutcomeText for a REFUSED mission with no per-step entries falls back to the summary's own reason", () => {
  const result = { status: "REFUSED", reason: "G-04 credential-access-prohibited.", step_results: [] };
  assert.match(runOutcomeText(result), /G-04 credential-access-prohibited\./);
});

test("runOutcomeText: a rejected step is reported as a rejection, not the ambiguous APPROVAL_REQUIRED status word", () => {
  const result = { status: "APPROVAL_REQUIRED", step_results: [] };
  const text = runOutcomeText(result, { rejected: true });
  assert.match(text, /rejected/i);
  assert.doesNotMatch(text, /APPROVAL_REQUIRED/);
});

test("runOutcomeText: a genuinely pending approval (not rejected) is distinguished from a rejection", () => {
  const result = { status: "AWAITING_APPROVAL", step_results: [] };
  const text = runOutcomeText(result, { rejected: false });
  assert.match(text, /human decision/i);
  assert.doesNotMatch(text, /rejected/i);
});

test("runOutcomeText: COMPLETED reports the real step count, not a fabricated one", () => {
  const result = { status: "COMPLETED", steps_completed: 3, step_results: [] };
  assert.equal(runOutcomeText(result), "Mission completed — 3 steps.");
});

test("runOutcomeText: BLOCKED reports the real gap reason", () => {
  const result = { status: "BLOCKED", blocked_on: { reason: "Capability 'fx_normalize' is not registered." } };
  assert.match(runOutcomeText(result), /fx_normalize/);
});

test("runOutcomeText never throws on a bare/empty result", () => {
  assert.equal(runOutcomeText(null), "");
  assert.doesNotThrow(() => runOutcomeText({ status: "UNKNOWN" }));
});

if (failures > 0) {
  console.error(`\n${failures} test(s) failed.`);
  process.exit(1);
} else {
  console.log("\nAll graphExecutionState tests passed.");
}
