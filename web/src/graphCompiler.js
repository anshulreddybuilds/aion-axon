/**
 * Turns the visual mission builder's nodes/edges into the exact same
 * MissionPlan/MissionStep shape (see app/agents/plan_schema.py) the
 * Gemini-backed planner already produces for POST /missions/planned.
 *
 * This is the "compiler" in GRAPH -> MISSION COMPILER -> EXISTING MISSION
 * ENGINE. There is no second schema and no second engine: the object this
 * file builds is posted verbatim to POST /missions/from-graph, which hands
 * it to the identical mission_engine.run() every other mission goes
 * through. Everything here is pure and framework-free so it can be unit
 * tested without a browser -- see graphCompiler.test.mjs.
 *
 * A node references another node's output by writing `@id` (optionally
 * `@id.field`) inside its own args text -- e.g. a node with id "b" whose
 * arg reads "$STEP + @a.result" becomes step 2's arg
 * "$STEP + $STEP_1.result" once node "a" compiles to step 1. This is the
 * ONLY graph-specific notation anywhere in this file; the moment
 * compilation finishes, every trace of "@id" is gone and only the
 * engine's own $STEP_n convention remains.
 */

const REF_RE = /@([A-Za-z0-9_]+)(\.[A-Za-z0-9_.]+)?/g;

/** Kahn's algorithm with a stable tie-break (original node order). */
export function topoOrder(nodes, edges) {
  const ids = nodes.map((n) => n.id);
  const idSet = new Set(ids);

  const badEdge = (edges || []).find(
    (e) => !idSet.has(e.from) || !idSet.has(e.to)
  );
  if (badEdge) {
    return {
      order: null,
      error: `An edge references a node that does not exist (${badEdge.from} -> ${badEdge.to}).`,
    };
  }

  const indegree = new Map(ids.map((id) => [id, 0]));
  const adj = new Map(ids.map((id) => [id, []]));

  for (const e of edges || []) {
    adj.get(e.from).push(e.to);
    indegree.set(e.to, indegree.get(e.to) + 1);
  }

  const queue = ids.filter((id) => indegree.get(id) === 0);
  const order = [];

  while (queue.length) {
    const id = queue.shift();
    order.push(id);
    for (const next of adj.get(id)) {
      indegree.set(next, indegree.get(next) - 1);
      if (indegree.get(next) === 0) queue.push(next);
    }
  }

  if (order.length !== ids.length) {
    return {
      order: null,
      error: "The graph has a cycle -- a node cannot depend on its own result, directly or through others.",
    };
  }

  return { order, error: null };
}

/**
 * nodes: [{ id, description, tool, args: string[], risk, kind, action }]
 * edges: [{ from: nodeId, to: nodeId }]  -- "to" depends on "from"
 *
 * Returns { plan, error }. Exactly one is non-null. `plan` matches
 * MissionPlan: { goal, steps: MissionStep[] }.
 */
export function compileGraphToPlan(nodes, edges, goal) {
  if (!nodes || nodes.length === 0) {
    return { plan: null, error: "Add at least one node before compiling." };
  }

  const ids = nodes.map((n) => n.id);
  const dupe = ids.find((id, i) => ids.indexOf(id) !== i);
  if (dupe) {
    return { plan: null, error: `Two nodes share the id "${dupe}" -- node ids must be unique.` };
  }

  const { order, error } = topoOrder(nodes, edges);
  if (error) return { plan: null, error };

  const stepNumberById = new Map(order.map((id, i) => [id, i + 1]));
  const byId = new Map(nodes.map((n) => [n.id, n]));

  const unresolved = [];

  const steps = order.map((id) => {
    const n = byId.get(id);
    const args = (n.args || []).map((raw) =>
      String(raw).replace(REF_RE, (match, refId, field) => {
        const stepNum = stepNumberById.get(refId);
        if (stepNum == null) {
          unresolved.push(`node "${id}" references unknown node "@${refId}"`);
          return match;
        }
        return `$STEP_${stepNum}${field || ""}`;
      })
    );

    return {
      step: stepNumberById.get(id),
      description: n.description || n.id,
      kind: n.kind || "READ_ANALYZE",
      tool: n.tool || null,
      args,
      risk: n.risk || "LOW",
      action: n.action || n.id,
    };
  });

  if (unresolved.length) {
    return { plan: null, error: `Fix these references before compiling: ${unresolved.join("; ")}.` };
  }

  return { plan: { goal: goal || "Graph-authored mission", steps }, error: null };
}

/**
 * The inverse direction: given a MissionPlan (e.g. one the planner
 * produced from typed or spoken free text), reconstruct a graph a person
 * can see and edit before running it. Used by the "plan it, then show me
 * the graph" convergence path -- text/voice and the canvas end up editing
 * the same object.
 *
 * $STEP_n references inside args become edges FROM that earlier step's
 * node TO this one, and the args themselves are rewritten back to `@id`
 * form so the graph stays self-consistent if it is re-compiled unchanged.
 */
export function planToGraph(plan) {
  const steps = plan?.steps || [];
  const idOf = (n) => `n${n}`;

  const nodes = steps.map((s, i) => ({
    id: idOf(s.step ?? i + 1),
    description: s.description || "",
    tool: s.tool ?? null,
    risk: s.risk || "LOW",
    kind: s.kind || "READ_ANALYZE",
    action: s.action || idOf(s.step ?? i + 1),
    args: (s.args || []).map((raw) =>
      String(raw).replace(
        /\$STEP_(\d+)((?:\.[A-Za-z_][A-Za-z0-9_.]*)?)/g,
        (_m, n, field) => `@${idOf(Number(n))}${field}`
      )
    ),
  }));

  const edgeSet = new Set();
  const edges = [];
  for (const n of nodes) {
    for (const arg of n.args) {
      REF_RE.lastIndex = 0;
      let m;
      while ((m = REF_RE.exec(arg))) {
        const from = m[1];
        const key = `${from}->${n.id}`;
        if (from !== n.id && !edgeSet.has(key)) {
          edgeSet.add(key);
          edges.push({ from, to: n.id });
        }
      }
    }
  }

  return { nodes, edges, goal: plan?.goal || "" };
}
