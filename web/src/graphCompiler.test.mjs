import assert from "node:assert/strict";
import { compileGraphToPlan, planToGraph, topoOrder } from "./graphCompiler.js";

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

test("a graph with no edges compiles in node order, no $STEP_N needed", () => {
  const nodes = [
    { id: "a", description: "first", tool: "calculator", args: ["1 + 1"], risk: "LOW", kind: "READ_ANALYZE", action: "a" },
    { id: "b", description: "second", tool: "calculator", args: ["2 + 2"], risk: "LOW", kind: "READ_ANALYZE", action: "b" },
  ];
  const { plan, error } = compileGraphToPlan(nodes, [], "two calcs");
  assert.equal(error, null);
  assert.equal(plan.steps.length, 2);
  assert.equal(plan.steps[0].step, 1);
  assert.equal(plan.steps[1].step, 2);
  assert.deepEqual(plan.steps[0].args, ["1 + 1"]);
});

test("a dependency edge and an @id reference compile to real $STEP_N", () => {
  const nodes = [
    { id: "a", description: "n1", tool: "calculator", args: ["10 * 4"], risk: "LOW", kind: "READ_ANALYZE", action: "n1" },
    { id: "b", description: "n2", tool: "calculator", args: ["5 + 5"], risk: "LOW", kind: "READ_ANALYZE", action: "n2" },
    { id: "c", description: "combine", tool: "calculator", args: ["@a.result + @b.result"], risk: "LOW", kind: "READ_ANALYZE", action: "combine" },
  ];
  const edges = [{ from: "a", to: "c" }, { from: "b", to: "c" }];
  const { plan, error } = compileGraphToPlan(nodes, edges, "combine two");
  assert.equal(error, null);
  assert.equal(plan.steps.length, 3);
  const combineStep = plan.steps.find((s) => s.action === "combine");
  assert.equal(combineStep.step, 3);
  assert.deepEqual(combineStep.args, ["$STEP_1.result + $STEP_2.result"]);
});

test("edges determine execution order even when nodes are authored out of order", () => {
  // "b" depends on "a", but "a" is declared second in the array -- the
  // canvas lets a user draw nodes in any order, so the compiler must not
  // assume array order equals dependency order.
  const nodes = [
    { id: "b", description: "second", tool: "calculator", args: ["@a"], risk: "LOW", kind: "READ_ANALYZE", action: "b" },
    { id: "a", description: "first", tool: "calculator", args: ["1 + 1"], risk: "LOW", kind: "READ_ANALYZE", action: "a" },
  ];
  const edges = [{ from: "a", to: "b" }];
  const { plan, error } = compileGraphToPlan(nodes, edges, "ordered by edge");
  assert.equal(error, null);
  const aStep = plan.steps.find((s) => s.action === "a");
  const bStep = plan.steps.find((s) => s.action === "b");
  assert.ok(aStep.step < bStep.step);
  assert.deepEqual(bStep.args, [`$STEP_${aStep.step}`]);
});

test("a two-node cycle is rejected, not silently accepted", () => {
  const nodes = [
    { id: "a", description: "a", tool: "calculator", args: ["@b"], risk: "LOW", kind: "READ_ANALYZE", action: "a" },
    { id: "b", description: "b", tool: "calculator", args: ["@a"], risk: "LOW", kind: "READ_ANALYZE", action: "b" },
  ];
  const edges = [{ from: "a", to: "b" }, { from: "b", to: "a" }];
  const { plan, error } = compileGraphToPlan(nodes, edges, "cycle");
  assert.equal(plan, null);
  assert.match(error, /cycle/i);
});

test("a self-loop is rejected as a cycle", () => {
  const nodes = [{ id: "a", description: "a", tool: "calculator", args: ["@a"], risk: "LOW", kind: "READ_ANALYZE", action: "a" }];
  const edges = [{ from: "a", to: "a" }];
  const { error } = compileGraphToPlan(nodes, edges, "self loop");
  assert.match(error, /cycle/i);
});

test("an edge naming a node that was deleted is rejected honestly", () => {
  const nodes = [{ id: "a", description: "a", tool: "calculator", args: ["1"], risk: "LOW", kind: "READ_ANALYZE", action: "a" }];
  const edges = [{ from: "a", to: "ghost" }];
  const { plan, error } = compileGraphToPlan(nodes, edges, "dangling edge");
  assert.equal(plan, null);
  assert.match(error, /does not exist/);
});

test("a reference to a node id that was never wired as an edge is rejected, not silently left broken", () => {
  const nodes = [
    { id: "a", description: "a", tool: "calculator", args: ["1"], risk: "LOW", kind: "READ_ANALYZE", action: "a" },
    { id: "b", description: "b", tool: "calculator", args: ["@ghost"], risk: "LOW", kind: "READ_ANALYZE", action: "b" },
  ];
  const { plan, error } = compileGraphToPlan(nodes, [], "unknown ref");
  assert.equal(plan, null);
  assert.match(error, /unknown node "@ghost"/);
});

test("duplicate node ids are rejected", () => {
  const nodes = [
    { id: "a", description: "one", tool: "calculator", args: ["1"], risk: "LOW", kind: "READ_ANALYZE", action: "one" },
    { id: "a", description: "two", tool: "calculator", args: ["2"], risk: "LOW", kind: "READ_ANALYZE", action: "two" },
  ];
  const { plan, error } = compileGraphToPlan(nodes, [], "dup ids");
  assert.equal(plan, null);
  assert.match(error, /share the id "a"/);
});

test("an empty graph is rejected, not silently compiled to zero steps", () => {
  const { plan, error } = compileGraphToPlan([], [], "empty");
  assert.equal(plan, null);
  assert.match(error, /at least one node/);
});

test("a node left with no capability compiles tool: null -- an honest gap, not a crash", () => {
  const nodes = [{ id: "a", description: "unwired", tool: null, args: ["x"], risk: "LOW", kind: "READ_ANALYZE", action: "gap" }];
  const { plan, error } = compileGraphToPlan(nodes, [], "gap");
  assert.equal(error, null);
  assert.equal(plan.steps[0].tool, null);
});

test("topoOrder alone reports the same cycle error compileGraphToPlan surfaces", () => {
  const nodes = [{ id: "a" }, { id: "b" }];
  const edges = [{ from: "a", to: "b" }, { from: "b", to: "a" }];
  const { order, error } = topoOrder(nodes, edges);
  assert.equal(order, null);
  assert.match(error, /cycle/i);
});

test("planToGraph is the inverse of compileGraphToPlan for a simple dependent plan", () => {
  const plan = {
    goal: "roundtrip",
    steps: [
      { step: 1, description: "n1", tool: "calculator", args: ["10 * 4"], risk: "LOW", kind: "READ_ANALYZE", action: "n1" },
      { step: 2, description: "n2", tool: "calculator", args: ["5 + 5"], risk: "LOW", kind: "READ_ANALYZE", action: "n2" },
      { step: 3, description: "combine", tool: "calculator", args: ["$STEP_1.result + $STEP_2.result"], risk: "LOW", kind: "READ_ANALYZE", action: "combine" },
    ],
  };
  const { nodes, edges } = planToGraph(plan);
  assert.equal(nodes.length, 3);
  assert.equal(edges.length, 2);

  // Re-compiling the reconstructed graph must reproduce the same $STEP_N
  // wiring -- this is the property the text/voice -> graph convergence
  // path depends on: a planner-authored plan must round-trip through the
  // canvas without losing its dependency structure.
  const { plan: recompiled, error } = compileGraphToPlan(nodes, edges, plan.goal);
  assert.equal(error, null);
  const combineStep = recompiled.steps.find((s) => s.action === "combine");
  assert.deepEqual(combineStep.args, ["$STEP_1.result + $STEP_2.result"]);
});

test("planToGraph handles a plan with no dependencies at all (no edges invented)", () => {
  const plan = {
    goal: "no deps",
    steps: [{ step: 1, description: "solo", tool: "calculator", args: ["1+1"], risk: "LOW", kind: "READ_ANALYZE", action: "solo" }],
  };
  const { nodes, edges } = planToGraph(plan);
  assert.equal(nodes.length, 1);
  assert.equal(edges.length, 0);
});

if (failures > 0) {
  console.error(`\n${failures} test(s) failed.`);
  process.exit(1);
} else {
  console.log("\nAll graphCompiler tests passed.");
}
