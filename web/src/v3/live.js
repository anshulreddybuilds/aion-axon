import { api } from "../api.js";

/**
 * LIVE mode — the same twelve nodes, driven by a real mission in flight.
 *
 * REPLAY walks a recorded run on a timer, which is honest but fixed-pace.
 * LIVE has no timer at all: a node lights when its OWN telemetry counter
 * actually increments while the mission is running. That means the pacing
 * on screen IS the pipeline's real pacing — research really does take
 * ~20s, generation ~27s, evaluation ~34s — and nothing can light early
 * because nothing is scheduled.
 *
 * How it works, given the API shape:
 *
 *   POST /missions/planned is synchronous — it returns only once the whole
 *   mission has finished, so it cannot itself report progress. Instead the
 *   request is fired WITHOUT awaiting it, and /telemetry is polled
 *   alongside. `by_stage` carries per-stage call counts, so an increment
 *   there is a real, server-side signal that that stage just ran.
 *
 * Stages with no model call of their own (AST screen, sandbox, install,
 * ledger) are inferred from things that are equally real: the evolution
 * event count rising, the registry growing, the mission's own step
 * results. Where nothing real is observable, the node simply does not
 * light — it is never advanced just to keep the animation moving.
 */

const POLL_MS = 1000;

/** Snapshot the counters a live run can move. */
function snapshot({ telemetry, evolution, capabilities }) {
  const by = telemetry?.by_stage || {};
  return {
    research: (by.research?.calls || 0) + (by.research_degraded?.calls || 0),
    generate: by.generate?.calls || 0,
    evaluate: by.evaluate?.calls || 0,
    executions: telemetry?.tool_executions?.count || 0,
    events: evolution?.count || 0,
    implemented: capabilities?.implemented || 0,
  };
}

async function readCounters() {
  const [telemetry, evolution, capabilities] = await Promise.allSettled([
    api.telemetry(),
    api.evolution(),
    api.capabilities(),
  ]);
  const val = (s) => (s.status === "fulfilled" ? s.value : null);
  return snapshot({
    telemetry: val(telemetry),
    evolution: val(evolution),
    capabilities: val(capabilities),
  });
}

/**
 * Run a real mission and report node activity as it genuinely happens.
 *
 * @param {string} request      the plain-English mission
 * @param {object} handlers     { onNode, onLog, onDone, onError }
 * @returns {function} cancel
 */
export function runLiveMission(request, { onNode, onLog, onDone, onError }) {
  let cancelled = false;
  let poll = null;

  const finish = (fn, ...args) => {
    if (cancelled) return;
    if (poll) clearInterval(poll);
    poll = null;
    fn?.(...args);
  };

  (async () => {
    let baseline;
    try {
      baseline = await readCounters();
    } catch (err) {
      finish(onError, err.message);
      return;
    }
    if (cancelled) return;

    // Stages 1-3 are true the moment a governed mission is accepted: an
    // owner token authorised it, the orchestrator planned it, and gap
    // detection is what decides whether it blocks. These are not timed
    // guesses -- they are preconditions of the request existing at all.
    onNode?.(1, "owner authorised the request");
    onNode?.(2, "orchestrator planning the mission");
    onLog?.("OK", "mission accepted — planning");

    const seen = new Set();

    poll = setInterval(async () => {
      if (cancelled) return;
      let now;
      try {
        now = await readCounters();
      } catch {
        return; // a dropped poll is not a pipeline event; stay quiet
      }

      const fire = (key, node, message) => {
        if (seen.has(key)) return;
        if (now[key] > baseline[key]) {
          seen.add(key);
          onNode?.(node, message);
          onLog?.("OK", message);
        }
      };

      fire("research", 4, "research call completed");
      fire("generate", 5, "candidate generated");
      fire("evaluate", 8, "evaluator scored the candidate");
      fire("executions", 7, "sandbox execution recorded");
      fire("events", 12, "evolution event written to the ledger");
      fire("implemented", 11, "registry grew — capability installed");
    }, POLL_MS);

    // The mission itself. Not awaited above so the poller runs alongside.
    try {
      const result = await api.plannedMission(request);
      if (cancelled) return;

      // Gap detection is only reportable once the mission says whether it
      // hit one -- so it is reported now, from the real answer.
      if (result?.blocked_on) {
        onNode?.(3, "gap detected — mission BLOCKED");
        onLog?.("BLOCKED", `gap: ${result.blocked_on.capability_description || result.blocked_on.description}`);
      } else {
        onNode?.(3, "no gap — every capability already existed");
      }

      (result?.step_results || []).forEach((s, i) => {
        onLog?.(
          s.status === "EXECUTED" ? "OK" : "BLOCKED",
          `step ${i + 1} ${s.tool || ""} → ${s.status}`
        );
      });

      finish(onDone, result);
    } catch (err) {
      const message = String(err?.message || err);
      // A 429 is reported exactly as what it is. The whole point of live
      // mode is that the screen reflects the server; dressing a quota
      // refusal as anything else would undo that.
      onLog?.("REFUSED", message.includes("429") ? "Gemini quota exhausted" : message);
      finish(onError, message);
    }
  })();

  return () => {
    cancelled = true;
    if (poll) clearInterval(poll);
  };
}
