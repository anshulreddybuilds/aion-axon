// The top strip must describe the backend this browser is ACTUALLY
// talking to. It previously rendered "AXON NODE / ASIA-SOUTH1" and
// "LIVE — CLOUD RUN" as static text regardless of CORE, so pointing the
// dev server at a local backend produced a strip confidently claiming a
// Cloud Run deployment in a region it had never contacted -- three
// panels away from the sidebar's own promise that "Every number on this
// surface is read from the live API. Nothing is mocked."
//
// Run with: node web/src/backendLabel.test.mjs
import assert from "node:assert/strict";

import { backendLabel } from "./backendLabel.js";

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok - ${name}`);
}

console.log("backendLabel.test.mjs");

test("a local backend is never described as Cloud Run", () => {
  const { node, live } = backendLabel("http://127.0.0.1:8099");
  assert.equal(live, "LIVE — LOCAL");
  assert.ok(!live.includes("CLOUD RUN"));
  assert.ok(node.includes("LOCAL:8099"));
  assert.ok(!node.includes("ASIA-SOUTH1"));
});

test("localhost and ::1 are recognised as local too", () => {
  assert.equal(backendLabel("http://localhost:5173").live, "LIVE — LOCAL");
  assert.equal(backendLabel("http://[::1]:8080").live, "LIVE — LOCAL");
});

test("a real Cloud Run URL reports Cloud Run and its OWN region", () => {
  const { node, live } = backendLabel(
    "https://aion-core-638298765129.asia-south1.run.app"
  );
  assert.equal(live, "LIVE — CLOUD RUN");
  assert.equal(node, "AXON NODE / ASIA-SOUTH1");
});

test("the region is read from the URL, not assumed to be asia-south1", () => {
  const { node } = backendLabel(
    "https://aion-core-123.europe-west1.run.app"
  );
  assert.equal(node, "AXON NODE / EUROPE-WEST1");
});

test("a non-Cloud-Run remote host is not claimed to be Cloud Run", () => {
  const { node, live } = backendLabel("https://axon.example.com");
  assert.equal(live, "LIVE");
  assert.equal(node, "AXON NODE / AXON.EXAMPLE.COM");
});

test("a malformed CORE says UNKNOWN rather than inventing a location", () => {
  const { node, live } = backendLabel("not a url at all");
  assert.equal(node, "AXON NODE / UNKNOWN");
  assert.equal(live, "LIVE");
});

console.log(`\n${passed} passed`);
