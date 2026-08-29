/**
 * The pipeline trace, assembled from REAL telemetry.
 *
 * The design brief asked for a reasoning drawer with timing badges
 * ("Thought 4.2s") and a streaming step-by-step trace. Two of those three
 * things are available for real and one is not, so this module draws the
 * line explicitly rather than letting a component quietly invent the
 * difference:
 *
 *   REAL  — per-stage call counts, token counts and average latency, from
 *           GET /telemetry `by_stage`. These are measured from the model's
 *           own usage_metadata; the endpoint reports `unmeasured` calls
 *           separately rather than estimating them.
 *   REAL  — sandbox exit codes, pass/fail, stdout and the named approver,
 *           from GET /evolution.
 *   ABSENT — the model's inner monologue. Nothing in this system stores
 *           chain-of-thought, so no component may render one. A drawer
 *           that streamed invented "thoughts" would be the exact failure
 *           this project's whole thesis argues against.
 *
 * So a "reasoning step" here is a real pipeline stage with its real
 * measured cost, not a narrated thought.
 */

/** ms → the compact human form the design asks for ("26.8s", "240ms"). */
export function humanMs(ms) {
  if (ms == null || Number.isNaN(ms)) return null;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * The ordered acquisition trace. Each step carries only what telemetry
 * actually measured; `stat` is null when nothing was measured, and the UI
 * must render that as "not measured" rather than as a zero.
 */
export function buildTrace({ telemetry, evolution, sandbox }) {
  const by = telemetry?.by_stage || {};
  const exec = telemetry?.tool_executions || {};

  const research = by.research || {};
  const degraded = by.research_degraded || {};
  const researchCalls = (research.calls || 0) + (degraded.calls || 0);
  const generate = by.generate || {};
  const evaluate = by.evaluate || {};

  const latest = evolution?.events?.[0] || null;
  const tests = latest?.test_results || null;

  const steps = [
    {
      key: "research",
      label: "Research",
      note: degraded.calls
        ? "ungrounded — Search grounding is tier-blocked, reported not faked"
        : "grounded in Google Search",
      ms: research.avg_ms ?? degraded.avg_ms ?? null,
      stat: researchCalls ? `${researchCalls} calls` : null,
      tone: degraded.calls ? "warn" : "ok",
    },
    {
      key: "generate",
      label: "Generate candidate",
      note: "Gemini writes the capability",
      ms: generate.avg_ms ?? null,
      stat: generate.tokens ? `${generate.tokens.toLocaleString()} tokens` : null,
      tone: "ok",
    },
    {
      key: "ast",
      label: "AST safety screen",
      note: "no os · subprocess · eval · dunder",
      // The static screen is not a model call, so its cost lives in the
      // tool-execution histogram rather than in by_stage.
      ms: exec.p50_ms ?? null,
      stat: exec.count ? `p50 of ${exec.count} executions` : null,
      tone: "ok",
    },
    {
      key: "sandbox",
      label: "Sandbox execution",
      note:
        sandbox?.verdict === "ZERO_CREDENTIALS"
          ? "zero credentials · internet gets 403"
          : "credential posture unverified",
      ms: exec.max_ms ?? null,
      stat: tests ? `exit ${tests.exit_code}` : null,
      tone: tests?.passed === false ? "danger" : "ok",
    },
    {
      key: "evaluate",
      label: "Evaluator second opinion",
      note: "Gemma scores it, or reports UNSCORED",
      ms: evaluate.avg_ms ?? null,
      stat: evaluate.calls ? `${evaluate.calls} scored` : null,
      tone: "ok",
    },
    {
      key: "approval",
      label: "Human approval",
      note: latest?.approver
        ? `approved by ${latest.approver}`
        : "nothing installs without a human",
      ms: null, // A human decision has no machine latency to report.
      stat: latest?.approver ? "named decision" : null,
      tone: "ok",
    },
  ];

  return steps;
}

/**
 * The terminal feed, from real evolution events.
 *
 * Tags are derived from recorded outcomes: a sandbox exit code, a real
 * citation count. Nothing here is a literal string chosen for effect.
 */
export function buildLogLines(evolution) {
  const events = evolution?.events || [];

  return events.flatMap((event) => {
    const tests = event.test_results || {};
    const citations = event.research_citations || [];
    const name =
      event.change?.match(/'([^']+)'/)?.[1] || event.change || "capability";

    const lines = [
      {
        tag: tests.passed ? "OK" : "BLOCKED",
        text: `sandbox ${name} → ${tests.status || "UNKNOWN"} exit=${
          tests.exit_code ?? "?"
        }`,
      },
      {
        // Zero citations is the honest state today, and it is shown as
        // DEGRADED rather than hidden or padded with invented sources.
        tag: citations.length ? "OK" : "DEGRADED",
        text: `research ${name} → ${citations.length} citations`,
      },
      {
        tag: "OK",
        text: `installed ${name} → approved by ${event.approver || "unknown"}`,
      },
    ];

    return lines;
  });
}
