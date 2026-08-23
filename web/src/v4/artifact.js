import { api } from "../api.js";

/**
 * The artifact a mission actually produced — fetched, never invented.
 *
 * Framer Agents' canvas shows a generated web page at three viewport
 * widths, and its sidebar narrates "Added 3 layers, edited 1". AION Axon
 * does not generate web pages or layers, so cloning those literally would
 * mean rendering a product that does not exist.
 *
 * What it DOES generate is a Python capability, and the API exposes the
 * whole chain of custody for one: the real source Gemini wrote, the real
 * test, the real AST findings, the real sandbox exit code, the real Gemma
 * verdict with its reasoning, and the named human who approved it.
 *
 * So the three "viewports" are three views of that real artifact —
 * Source, Test, Evidence — and the code card shows code the system
 * genuinely produced rather than a decorative snippet.
 */

export const VIEWS = [
  { id: "source", label: "Source", hint: "what Gemini wrote" },
  { id: "test", label: "Test", hint: "what ran in the sandbox" },
  { id: "evidence", label: "Evidence", hint: "why it was allowed" },
];

/** Ordered pipeline actions with their real measured cost. */
export function buildActions({ telemetry, passport }) {
  const by = telemetry?.by_stage || {};
  const exec = telemetry?.tool_executions || {};
  const p = passport?.passport || {};

  const research = by.research || {};
  const degraded = by.research_degraded || {};

  return [
    {
      label: "Researched an approach",
      ms: research.avg_ms ?? degraded.avg_ms ?? null,
      detail: p.research?.grounded
        ? `${p.research.source_count} sources`
        : "0 citations — Search grounding tier-blocked",
      tone: p.research?.grounded ? "ok" : "warn",
    },
    {
      label: "Wrote the candidate capability",
      ms: by.generate?.avg_ms ?? null,
      detail: p.candidate?.name
        ? `${p.candidate.name} · risk ${p.candidate.risk || "?"}`
        : "no candidate recorded",
      tone: "ok",
    },
    {
      label: "Screened it statically",
      ms: exec.p50_ms ?? null,
      detail:
        p.safety?.safe === true
          ? `safe · ${(p.safety.findings || []).length} findings`
          : "not screened",
      tone: p.safety?.safe === true ? "ok" : "danger",
    },
    {
      label: "Ran it in the zero-credential sandbox",
      ms: exec.max_ms ?? null,
      detail: p.tests
        ? `${p.tests.status} · exit ${p.tests.exit_code} · stdout ${JSON.stringify(
            p.tests.stdout || ""
          )}`
        : "no sandbox result",
      tone: p.tests?.passed ? "ok" : "danger",
    },
    {
      label: "Took a second opinion",
      ms: by.evaluate?.avg_ms ?? null,
      detail: p.evaluation
        ? `${p.evaluation.model} · ${p.evaluation.verdict} ${p.evaluation.score}`
        : "unscored",
      tone: p.evaluation?.verdict === "PASS" ? "ok" : "warn",
    },
    {
      label: "Asked a human",
      ms: null,
      detail: passport?.approved_by
        ? `approved by ${passport.approved_by}`
        : "awaiting a decision",
      tone: "ok",
    },
  ];
}

/** The reasoning drawer text — quoted, never authored here. */
export function buildThought(passport) {
  const p = passport?.passport || {};
  return {
    need: p.need || null,
    evaluatorReason: p.evaluation?.reason || null,
    guardian: p.guardian || null,
  };
}

export async function loadArtifact(name) {
  const [passport, telemetry, capabilities, autonomy] = await Promise.allSettled([
    api.passport(name),
    api.telemetry(),
    api.capabilities(),
    api.autonomy(),
  ]);

  const val = (s) => (s.status === "fulfilled" ? s.value : null);

  const p = val(passport);
  const t = val(telemetry);

  return {
    passport: p,
    telemetry: t,
    capabilities: val(capabilities),
    autonomy: val(autonomy),
    actions: buildActions({ telemetry: t, passport: p }),
    thought: buildThought(p),
  };
}

export function humanMs(ms) {
  if (ms == null || Number.isNaN(ms)) return null;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * The ANSWER a mission produced — the thing that was actually asked for.
 *
 * v4 could show the whole apparatus (code, tests, evidence, timings) and
 * never show the result. For a product whose closing claim is "it finishes
 * the job by itself", the finished job was the one thing missing from the
 * screen. The owner asked "where is the final result?" and the honest
 * answer was: nowhere.
 *
 * Reads the last EXECUTED step's payload. Returns null rather than
 * inventing a shape when a mission has not produced one.
 */
export function extractAnswer(mission) {
  if (!mission) return null;

  const steps = (mission.step_results || []).filter(
    (s) => s.status === "EXECUTED"
  );
  if (!steps.length) return null;

  const last = steps[steps.length - 1];

  // Results arrive either bare or wrapped in a {status, result} envelope.
  const raw = last.result || {};
  const payload = raw.result && typeof raw.result === "object" ? raw.result : raw;

  // Show the substantive fields, not the bookkeeping ones.
  const SKIP = new Set(["status", "rows", "truncated", "cache_hit"]);
  const fields = Object.entries(payload).filter(
    ([k, v]) =>
      !SKIP.has(k) && (typeof v === "number" || typeof v === "string")
  );

  if (!fields.length) return null;

  return {
    tool: last.tool,
    missionStatus: mission.status,
    missionId: mission.mission_id,
    request: mission.request,
    fields,
  };
}

/** Numbers readable at a glance; long strings left alone. */
export function prettyValue(v) {
  if (typeof v === "number") {
    if (Number.isInteger(v)) return v.toLocaleString();
    return Number(v.toFixed(4)).toLocaleString();
  }
  return String(v);
}
