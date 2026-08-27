/**
 * Maps a REAL mission result (from POST /missions/from-graph, or a
 * refresh via GET /missions/{id}) onto the graph's nodes for visual
 * state -- COMPLETED / FAILED / BLOCKED / AWAITING APPROVAL / not yet
 * run. Pure and framework-free, like graphCompiler.js and livePipeline.js,
 * so it is unit-testable without a browser -- see
 * graphExecutionState.test.mjs.
 *
 * Every field read here comes off the real MissionEngine summary
 * (app/missions/engine.py's _summary()). Nothing here invents progress
 * for a step the backend has not actually reported on -- a node with no
 * matching step_results entry and no matching blocked_on/next_step_index
 * is reported "not yet run", never guessed at.
 */

export function nodeStatuses({ nodes, stepNumberById, missionResult }) {
  const map = new Map();
  if (!missionResult) return map;

  const resultsByStep = new Map(
    (missionResult.step_results || []).map((r) => [r.step, r])
  );

  for (const n of nodes) {
    const stepNum = stepNumberById.get(n.id);
    if (stepNum == null) continue; // not part of the last compiled plan

    const r = resultsByStep.get(stepNum);
    if (r) {
      map.set(
        n.id,
        r.status === "EXECUTED"
          ? { tone: "ok", label: "COMPLETED", detail: "" }
          : { tone: "danger", label: r.status || "FAILED", detail: r.reason || "" }
      );
      continue;
    }

    if (missionResult.blocked_on?.step === stepNum) {
      map.set(n.id, {
        tone: "warn",
        label: "BLOCKED — missing a capability",
        detail: missionResult.blocked_on.reason || "",
      });
      continue;
    }

    if (
      missionResult.status === "AWAITING_APPROVAL" &&
      missionResult.next_step_index === stepNum - 1
    ) {
      map.set(n.id, {
        tone: "warn",
        label: "AWAITING APPROVAL",
        detail: "Stopped for a real human decision.",
      });
      continue;
    }

    map.set(n.id, { tone: "idle", label: "not yet run", detail: "" });
  }

  return map;
}
