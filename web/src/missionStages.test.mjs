// Plain Node test, same style/rationale as missionApprovalReconcile.test.mjs
// -- this repo's frontend has zero test infra configured. deriveStages()
// is a pure function but lives in a .jsx file alongside StageRow (which
// uses real JSX), so it can't be imported by plain Node as-is. esbuild is
// already a project dependency (vite's own transform engine, not a test
// framework being added for this) -- used here only to strip JSX syntax
// at test time via its classic "transform" mode (no react/jsx-runtime
// import injected, since deriveStages() itself never uses JSX and
// StageRow's JSX is never invoked by this test). Run with:
//   node web/src/missionStages.test.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { transformSync } from "esbuild";

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok - ${name}`);
}

console.log("missionStages.test.mjs");

const filePath = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "missionStages.jsx"
);
const source = readFileSync(filePath, "utf8");
const { code } = transformSync(source, { loader: "jsx", format: "esm" });
const module = await import(
  "data:text/javascript;base64," + Buffer.from(code).toString("base64")
);
const { deriveStages } = module;

const BASE_RECORD = {
  need: "test",
  stage: "AWAITING_APPROVAL",
  approval_request_id: "req-1",
  candidate: { name: "detect_expense_anomalies" },
};

// CASE 1: a real INSTALLED record (reconcileRecord()'s own success
// status, see missionApprovalReconcile.js) must render a terminal stage
// row. Before this fix, deriveStages() only recognized
// AWAITING_APPROVAL and the four failure statuses -- INSTALLED matched
// neither branch, so the "Human approval — WAITING" row just vanished
// with nothing replacing it: the stage timeline went visually blank at
// the exact moment of success.
test("an INSTALLED record renders a terminal INSTALLED stage row, not a blank timeline", () => {
  const stages = deriveStages({ ...BASE_RECORD, status: "INSTALLED" });
  const installedStage = stages.find((s) => s.key === "INSTALLED");
  assert.ok(installedStage, "expected an INSTALLED stage row, got none");
  assert.equal(installedStage.tone, "INSTALLED");
  assert.equal(installedStage.detail, "detect_expense_anomalies");
});

// CASE 2: existing AWAITING_APPROVAL behavior is unchanged by the fix.
test("an AWAITING_APPROVAL record still renders the waiting stage row", () => {
  const stages = deriveStages({ ...BASE_RECORD, status: "AWAITING_APPROVAL" });
  const waiting = stages.find((s) => s.key === "AWAITING_APPROVAL");
  assert.ok(waiting, "expected the waiting stage row, got none");
  assert.equal(waiting.tone, "WAITING");
  assert.equal(stages.find((s) => s.key === "INSTALLED"), undefined);
});

// CASE 3: existing terminal-failure behavior is unchanged by the fix.
test("a REJECTED record still renders the existing TERMINAL stage row, not INSTALLED", () => {
  const stages = deriveStages({ ...BASE_RECORD, status: "REJECTED", reason: "no" });
  const terminal = stages.find((s) => s.key === "TERMINAL");
  assert.ok(terminal, "expected the existing TERMINAL stage row, got none");
  assert.equal(terminal.tone, "REJECTED");
  assert.equal(stages.find((s) => s.key === "INSTALLED"), undefined);
});

console.log(`${passed} passed`);
