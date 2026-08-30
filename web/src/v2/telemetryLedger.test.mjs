import assert from "node:assert/strict";
import {
  autonomyLedgerRow,
  DEFAULT_SUPERVISION_THRESHOLD,
} from "./telemetryLedger.js";

let passed = 0;

function test(name, fn) {
  fn();
  passed += 1;
  console.log("  ok - " + name);
}

console.log("telemetryLedger.test.mjs");

test("missing autonomy score remains unknown, not 0%", () => {
  const row = autonomyLedgerRow({ name: "capability_without_score" });

  assert.equal(row.pct, null);
  assert.equal(row.belowThreshold, false);
  assert.equal(row.widthPct, null);
});

test("effective_autonomy_pct takes precedence over autonomy_pct", () => {
  const row = autonomyLedgerRow({
    name: "precedence",
    effective_autonomy_pct: 75,
    autonomy_pct: 20,
  });

  assert.equal(row.pct, 75);
  assert.equal(row.widthPct, 75);
  assert.equal(row.belowThreshold, false);
});

test("autonomy_pct is used when effective_autonomy_pct is absent", () => {
  const row = autonomyLedgerRow({
    name: "fallback",
    autonomy_pct: 25,
  });

  assert.equal(row.pct, 25);
  assert.equal(row.widthPct, 25);
  assert.equal(row.belowThreshold, true);
});

test("40% is exactly at the default supervision threshold", () => {
  const row = autonomyLedgerRow({
    name: "threshold",
    autonomy_pct: 40,
  });

  assert.equal(row.pct, 40);
  assert.equal(row.belowThreshold, false);
});

test("values below 40% require supervision", () => {
  const row = autonomyLedgerRow({
    name: "below",
    autonomy_pct: 39,
  });

  assert.equal(row.belowThreshold, true);
});

test("values above 40% do not require supervision", () => {
  const row = autonomyLedgerRow({
    name: "above",
    autonomy_pct: 41,
  });

  assert.equal(row.belowThreshold, false);
});

test("custom supervision threshold is respected", () => {
  const row = autonomyLedgerRow(
    {
      name: "custom",
      autonomy_pct: 55,
    },
    60
  );

  assert.equal(row.belowThreshold, true);
});

test("display width is clamped to 0..100", () => {
  assert.equal(
    autonomyLedgerRow({ autonomy_pct: -20 }).widthPct,
    0
  );

  assert.equal(
    autonomyLedgerRow({ autonomy_pct: 140 }).widthPct,
    100
  );
});

test("invalid numeric scores remain unknown rather than becoming misleading values", () => {
  const row = autonomyLedgerRow({
    name: "invalid",
    effective_autonomy_pct: "not-a-number",
  });

  assert.equal(row.pct, null);
  assert.equal(row.widthPct, null);
  assert.equal(row.belowThreshold, false);
});

assert.equal(DEFAULT_SUPERVISION_THRESHOLD, 40);

console.log(passed + " passed");
