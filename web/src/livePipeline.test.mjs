// Plain Node test, no framework -- same rationale/style as the other
// *.test.mjs files in this directory. Run with:
//   node web/src/livePipeline.test.mjs
import assert from "node:assert/strict";

import { describeStage, toneForRecord } from "./livePipeline.js";

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok - ${name}`);
}

console.log("livePipeline.test.mjs");

// --- The core generalization proof -----------------------------------
// Two different real records (as GET /synapse/propose/stream would
// actually send) must describe two different real capabilities -- never
// the same fixed example regardless of what was asked.

test("a GENERATE stage names the real candidate that was actually generated", () => {
  const celsius = describeStage({
    stage: "GENERATE",
    status: "IN_PROGRESS",
    candidate: { name: "convert_celsius_to_fahrenheit", description: "Converts C to F." },
  });
  const csv = describeStage({
    stage: "GENERATE",
    status: "IN_PROGRESS",
    candidate: { name: "detect_csv_anomalies", description: "Flags invalid CSV rows." },
  });

  assert.ok(celsius.detail.includes("convert_celsius_to_fahrenheit"));
  assert.ok(csv.detail.includes("detect_csv_anomalies"));
  assert.notEqual(celsius.detail, csv.detail);
  assert.ok(!celsius.detail.includes("calculate_birth_cagr"));
  assert.ok(!csv.detail.includes("calculate_birth_cagr"));
});

// --- Every field is real, nothing invented -----------------------------

test("RESEARCH reports the real source count when grounded", () => {
  const r = describeStage({
    stage: "RESEARCH",
    status: "IN_PROGRESS",
    research: { grounded: true, source_count: 3 },
  });
  assert.equal(r.detail, "3 sources found.");
});

test("RESEARCH reports the real degraded reason when ungrounded, not a fabricated one", () => {
  const r = describeStage({
    stage: "RESEARCH",
    status: "IN_PROGRESS",
    research: { grounded: false, degraded_reason: "Search grounding tier-blocked" },
  });
  assert.equal(r.detail, "Ungrounded — Search grounding tier-blocked");
});

test("SAFETY_SCREEN reports the real findings on rejection", () => {
  const r = describeStage({
    stage: "SAFETY_SCREEN",
    status: "REJECTED",
    safety: { safe: false, findings: ["blocked import: os"] },
  });
  assert.equal(r.detail, "blocked import: os");
  assert.equal(r.tone, "danger");
});

test("SANDBOX_TEST reports a real pass with no fabricated detail", () => {
  const r = describeStage({
    stage: "SANDBOX_TEST",
    status: "IN_PROGRESS",
    tests: { passed: true, status: "COMPLETED" },
  });
  assert.equal(r.tone, "ok");
  assert.ok(r.detail.toLowerCase().includes("passed"));
});

test("EVALUATE reports the real score and verdict", () => {
  const r = describeStage({
    stage: "EVALUATE",
    status: "IN_PROGRESS",
    evaluation: { score: 82, verdict: "PASS", reason: "solid" },
  });
  assert.ok(r.detail.includes("82"));
  assert.ok(r.detail.includes("PASS"));
});

test("GUARDIAN_SCREEN reports the real decision and reason", () => {
  const r = describeStage({
    stage: "GUARDIAN_SCREEN",
    status: "IN_PROGRESS",
    guardian: { decision: "ALLOW", reason: "low-risk, no policy match" },
  });
  assert.ok(r.detail.includes("ALLOW"));
  assert.ok(r.detail.includes("low-risk"));
});

test("AWAITING_APPROVAL names the real approval request id", () => {
  const r = describeStage({
    stage: "AWAITING_APPROVAL",
    status: "AWAITING_APPROVAL",
    approval_request_id: "297bc993-6304-40c7-9b9e-652a91912349",
  });
  assert.ok(r.detail.includes("297bc993"));
});

// --- Terminal outcomes are never disguised as progress -----------------

test("a REFUSED guardian pre-screen tone is danger, not ok", () => {
  const r = describeStage({
    stage: "GUARDIAN_PRESCREEN",
    status: "REFUSED",
    reason: "Policy G-04: credential access is prohibited.",
  });
  assert.equal(r.tone, "danger");
  assert.equal(r.detail, "Policy G-04: credential access is prohibited.");
});

test("toneForRecord treats every terminal-failure status as danger", () => {
  for (const status of ["REFUSED", "REJECTED", "BLOCKED", "FAILED"]) {
    assert.equal(toneForRecord({ status }), "danger");
  }
  assert.equal(toneForRecord({ status: "AWAITING_APPROVAL" }), "ok");
});

// --- Defensive on incomplete/missing data, never throws -----------------

test("describeStage never throws on a record missing its optional fields", () => {
  assert.doesNotThrow(() => describeStage({ stage: "GENERATE", status: "FAILED" }));
  assert.doesNotThrow(() => describeStage({}));
  assert.doesNotThrow(() => describeStage(null));
});

console.log(`\n${passed} passed`);
