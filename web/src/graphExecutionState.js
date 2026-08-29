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
 *
 * Real-time boundary, stated explicitly rather than papered over: there
 * is no backend endpoint that streams per-step progress for a plan's
 * normal execution -- mission_engine.run() executes synchronously and
 * returns one terminal (or suspended) summary. Per-node EXECUTING state
 * during that call would have to be invented client-side, which is
 * exactly what this project's own rules forbid ("never fabricate node
 * progress"). The one piece of this pipeline that IS genuinely
 * streamed -- capability acquisition, via GET /missions/{id}/acquire/
 * stream -- gets its own live per-node treatment in AppV5.jsx, driven
 * by the real SSE stages livePipeline.js already decodes. Everywhere
 * else, a single honest "running" indicator (not a per-node fabrication)
 * covers the in-flight period, and real per-node state appears the
 * instant the real result arrives.
 */

const APPROVAL_STATUSES = new Set(["AWAITING_APPROVAL", "APPROVAL_REQUIRED"]);

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
      APPROVAL_STATUSES.has(missionResult.status) &&
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

/**
 * The tone for the mission's OVERALL status word (shown once, not per
 * node). COMPLETED is the only "ok". BLOCKED/AWAITING_APPROVAL/
 * APPROVAL_REQUIRED are cautionary, not failures -- a mission stopped to
 * ask a real question, it did not break. Only FAILED/REFUSED/REJECTED
 * are genuine failures. An unrecognized status defaults to "warn", not
 * "danger": painting a status word this UI has never seen bright red
 * would be inventing a severity judgement the backend never made.
 */
export function toneForMissionStatus(status) {
  if (status === "COMPLETED") return "ok";
  if (status === "FAILED" || status === "REFUSED" || status === "REJECTED") return "danger";
  return "warn";
}

/**
 * The one real sentence to show (and, if voice output is on, speak) for
 * a mission's current terminal-for-now state.
 *
 * BUG-011: the graph builder's run panel originally showed only the bare
 * status word -- "FAILED", "REFUSED", "APPROVAL_REQUIRED" -- with no
 * reason at all, even though the real explanation was sitting one field
 * over in step_results[last].reason the whole time. The exact same
 * contract-reading class as BUG-005/007/008/009, just not yet checked
 * in this new surface. Reads step_results' own "reason" (already
 * coalesced from reason/error by mission_engine.run() before it ever
 * reaches here -- see that file's own BUG-007 comment) plus the
 * summary's own top-level reason/error, falling back through both
 * rather than trusting either alone.
 *
 * `rejected` is passed explicitly by the caller when it knows -- from
 * approval_manager.decide()'s OWN response, which does distinguish
 * REJECTED from "not yet decided" -- that a human just said no.
 * resume-planned's re-derived status word cannot tell the two apart on
 * its own (approve_and_resume() maps BOTH to "APPROVAL_REQUIRED"), so
 * trusting only that word would silently relabel a real rejection as
 * "still waiting", which is a different and misleading claim.
 */
export function runOutcomeText(result, { rejected = false } = {}) {
  if (!result) return "";
  const status = result.status;

  if (status === "COMPLETED") {
    const n = result.steps_completed ?? 0;
    return `Mission completed — ${n} step${n === 1 ? "" : "s"}.`;
  }

  if (rejected) {
    return "Not approved — this step was rejected. The mission did not proceed past it.";
  }

  if (status === "BLOCKED") {
    return `Blocked — ${result.blocked_on?.reason || "missing a capability"}.`;
  }

  if (APPROVAL_STATUSES.has(status)) {
    return "Stopped for a real human decision.";
  }

  const results = result.step_results || [];
  const last = results[results.length - 1];
  const reason = last?.reason || last?.error || result.reason || result.error;

  return `${status || "UNKNOWN"}${reason ? " — " + reason : ""}.`;
}
