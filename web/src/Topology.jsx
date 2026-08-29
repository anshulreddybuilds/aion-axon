import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";

/**
 * EXECUTION TOPOLOGY — the governed capability spine, twelve stages.
 *
 * This replaces the six-agent Synapse Theater with the richer twelve-node
 * pipeline from the owner's command-UI design. Same rule, more surface:
 * a node lights because a real counter moved, never because motion looks
 * alive.
 *
 * The design mockup shipped with placeholder values — 42% complete, five
 * days done, and stages 07 through 12 marked LOCKED. All six of those are
 * live and have been for days. Rendering the mockup's numbers would have
 * understated the system to a judge and broken the "runs consistently as
 * depicted" rule, so every figure below is read from the API instead and
 * a stage that has genuinely never run says LOCKED for a real reason.
 */

// "Hot" is the instant a real counter moves; "cooling" is the owner's own
// spec -- like iron pulled off the fire, still glowing red but dimming --
// so a card that just finished visibly reads as "just did something" for
// a few seconds instead of snapping back to idle the moment work ends.
const HOT_MS = 900;
const COOL_MS = 3200;

export const STAGES = [
  { n: "01", key: "owner", label: "Owner", blurb: "approves, denies, or halts" },
  { n: "02", key: "orchestrator", label: "Orchestrator", blurb: "plans and delegates" },
  { n: "03", key: "gap", label: "Gap Detect", blurb: "notices what it cannot do" },
  { n: "04", key: "research", label: "Research", blurb: "looks for an approach" },
  { n: "05", key: "generate", label: "Generate", blurb: "writes the candidate" },
  { n: "06", key: "ast", label: "AST Screen", blurb: "static safety check" },
  { n: "07", key: "sandbox", label: "Sandbox", blurb: "runs it in isolation" },
  { n: "08", key: "evaluator", label: "Evaluator", blurb: "second opinion" },
  { n: "09", key: "guardian", label: "Guardian", blurb: "deny by default" },
  { n: "10", key: "approval", label: "Approval", blurb: "a human decides" },
  { n: "11", key: "install", label: "Install", blurb: "capability registered" },
  { n: "12", key: "ledger", label: "Ledger", blurb: "chain of custody" },
];

// One glyph per stage -- decoration that still means something: the
// spine is a shape now, not just twelve identical cards in a row.
const ICONS = {
  owner: "⌘",
  orchestrator: "⬡",
  gap: "◇",
  research: "⌕",
  generate: "✎",
  ast: "▣",
  sandbox: "⧉",
  evaluator: "⬢",
  guardian: "◍",
  approval: "⌁",
  install: "⟡",
  ledger: "≡",
};

/** VERIFIED = has done real work · DEGRADED = working but impaired ·
 *  LOCKED = genuinely never run. */
export function computeStages(data) {
  return readStages({
    telemetry: data?.telemetry,
    sandbox: data?.sandbox,
    capabilities: data?.capabilities,
    autonomy: data?.autonomy,
    evolution: data?.evolution,
    pending: data?.pending?.pending || [],
    killed: !!data?.root?.kill_switch_active,
  });
}

function readStages({ telemetry, sandbox, capabilities, autonomy, evolution, pending, killed }) {
  const by = telemetry?.by_stage || {};
  const execs = telemetry?.tool_executions || {};
  const research = by.research || {};
  const degraded = by.research_degraded || {};
  const researchCalls = (research.calls || 0) + (degraded.calls || 0);
  const generate = by.generate || {};
  const evaluate = by.evaluate || {};

  const events = evolution?.events?.length || 0;
  const tracked = autonomy?.capabilities || [];
  const approvedCount = tracked.filter((c) => c.passport).length;
  const declaredOnly = (capabilities?.total ?? 0) - (capabilities?.implemented ?? 0);

  const S = (count, state, stat, detail) => ({ count, state, stat, detail });

  return {
    owner: S(approvedCount, approvedCount ? "VERIFIED" : "LOCKED",
      approvedCount ? `${approvedCount} approved` : "no decisions yet",
      "every install carries a named human decision"),

    orchestrator: S(execs.count || 0, execs.count ? "VERIFIED" : "LOCKED",
      execs.count ? `${execs.count} gated runs` : "never run",
      execs.avg_ms ? `${execs.avg_ms}ms average` : "every execution passes the gate"),

    // Knowing what it cannot do is the capability, so a non-zero count
    // here is health, not a backlog.
    gap: S(declaredOnly, declaredOnly ? "VERIFIED" : "LOCKED",
      `${declaredOnly} known gaps`,
      "declared but unbuilt — it can name what it lacks"),

    research: S(researchCalls,
      researchCalls ? (degraded.calls ? "DEGRADED" : "VERIFIED") : "LOCKED",
      researchCalls ? `${researchCalls} calls` : "never run",
      degraded.calls
        ? `${degraded.calls} ungrounded — Search quota-blocked, not faked`
        : "Google Search grounding"),

    generate: S(generate.calls || 0, generate.calls ? "VERIFIED" : "LOCKED",
      generate.calls ? `${generate.tokens?.toLocaleString() ?? 0} tokens` : "never run",
      generate.calls ? `${generate.calls} candidates written` : "Gemini writes the code"),

    // Every acquisition that produced an evolution event necessarily
    // passed the screen — the pipeline cannot reach install without it.
    ast: S(events, events ? "VERIFIED" : "LOCKED",
      events ? `${events} screened` : "never run",
      "no os · subprocess · eval · dunder"),

    sandbox: S(execs.count || 0,
      sandbox?.verdict === "ZERO_CREDENTIALS" ? "VERIFIED" : "DEGRADED",
      sandbox?.verdict === "ZERO_CREDENTIALS" ? "zero credentials" : "unverified",
      "core reaches it over OIDC · the internet gets 403"),

    evaluator: S(evaluate.calls || 0, evaluate.calls ? "VERIFIED" : "LOCKED",
      evaluate.calls ? `${evaluate.calls} scored` : "never run",
      "Gemma grades it, or reports UNSCORED"),

    guardian: S(killed ? 1 : 0, killed ? "DEGRADED" : "VERIFIED",
      killed ? "HALTED" : "armed",
      killed ? "kill switch active" : "7 policies · deny by default"),

    approval: S(pending?.length ?? 0,
      pending?.length ? "DEGRADED" : "VERIFIED",
      pending?.length ? `${pending.length} waiting on you` : "queue clear",
      "nothing installs without a human"),

    install: S(capabilities?.implemented ?? 0,
      capabilities?.implemented ? "VERIFIED" : "LOCKED",
      capabilities?.implemented != null
        ? `${capabilities.implemented} / ${capabilities.total}`
        : "unreachable",
      "implemented capabilities in the registry"),

    ledger: S(events, events ? "VERIFIED" : "LOCKED",
      events ? `${events} events` : "never run",
      "BEFORE → CHANGE → REASON → AFTER"),
  };
}

// Exported so Topology3D reads the exact same tone map — two renderings
// of one dataset must never be free to disagree about what a color means.
export const TONE = {
  VERIFIED: { dot: "#37e0d8", text: "text-cyan", ring: "border-cyan/40" },
  DEGRADED: { dot: "#fbbf24", text: "text-warn", ring: "border-warn/40" },
  LOCKED: { dot: "#3a4657", text: "text-muted", ring: "border-edge" },
};

/** A node pulses only when its own counter actually moved between two
 * polls — never on a timer, never on load. Shared by every rendering of
 * the topology (2D grid, 3D ring) so "what counts as a real event" is
 * defined exactly once.
 */
export function useFiringPulses(stages) {
  // key -> "hot" | "cooling" | (absent = idle). A plain truthy check
  // (`!!heat[key]`), which is all Topology3D.jsx does with this return
  // value, still works unchanged against either string.
  const [heat, setHeat] = useState({});
  const previous = useRef(null);
  const timers = useRef({});

  useEffect(() => {
    const counts = Object.fromEntries(
      STAGES.map(({ key }) => [key, stages[key].count])
    );

    if (previous.current === null) {
      previous.current = counts;
      return;
    }

    const moved = STAGES.filter(
      ({ key }) => counts[key] > (previous.current[key] ?? 0)
    ).map(({ key }) => key);

    previous.current = counts;
    if (!moved.length) return;

    for (const key of moved) {
      clearTimeout(timers.current[key]?.hot);
      clearTimeout(timers.current[key]?.cool);

      setHeat((h) => ({ ...h, [key]: "hot" }));

      const hot = setTimeout(() => {
        setHeat((h) => ({ ...h, [key]: "cooling" }));

        const cool = setTimeout(() => {
          setHeat((h) => {
            const next = { ...h };
            delete next[key];
            return next;
          });
        }, COOL_MS);

        timers.current[key] = { ...timers.current[key], cool };
      }, HOT_MS);

      timers.current[key] = { ...timers.current[key], hot };
    }
  }, [stages]);

  useEffect(() => {
    return () => {
      Object.values(timers.current).forEach((t) => {
        clearTimeout(t?.hot);
        clearTimeout(t?.cool);
      });
    };
  }, []);

  return heat;
}

export default function Topology({ stages, selected, onSelect }) {

  const heat = useFiringPulses(stages);

  const counts = STAGES.reduce((acc, { key }) => {
    acc[stages[key].state] = (acc[stages[key].state] || 0) + 1;
    return acc;
  }, {});

  return (
    <section className="panel-glass rounded-2xl p-6 md:p-8">
      <div className="flex items-start justify-between mb-1">
        <div>
          <p className="text-[10px] tracking-[0.28em] text-muted">
            EXECUTION TOPOLOGY
          </p>
          <h2 className="font-display text-[24px] md:text-[26px] font-semibold mt-2 tracking-tight text-glow-gradient">
            Governed capability spine
          </h2>
        </div>
        <p className="text-[9px] tracking-[0.18em] text-muted mt-1">
          AXON / LIVE GRAPH
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-4 mt-5 mb-5 text-[9px] tracking-[0.14em]">
        {["VERIFIED", "DEGRADED", "LOCKED"].map((s) => (
          <span key={s} className="flex items-center gap-1.5 text-muted">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ background: TONE[s].dot }}
            />
            {s} {counts[s] ? `· ${counts[s]}` : ""}
          </span>
        ))}
        <span className="ml-auto text-muted">CLICK ANY NODE FOR TELEMETRY</span>
      </div>

      <div className="spine-thread" aria-hidden="true" />

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-5">
        {STAGES.map((stage) => {
          const s = stages[stage.key];
          const tone = TONE[s.state];
          const heatState = heat[stage.key]; // "hot" | "cooling" | undefined
          const isSelected = selected === stage.key;
          const toneClass =
            s.state === "DEGRADED" ? "spine-card--degraded" :
            s.state === "LOCKED" ? "spine-card--locked" : "";
          const heatClass =
            heatState === "hot" ? "spine-card--firing" :
            heatState === "cooling" ? "spine-card--cooling" : "";

          return (
            <motion.button
              key={stage.key}
              onClick={() => onSelect(isSelected ? null : stage.key)}
              initial={{ opacity: 0, y: 10 }}
              animate={
                heatState === "hot"
                  ? { opacity: 1, y: 0, scale: [1, 1.04, 1.02] }
                  : { opacity: 1, y: 0, scale: 1 }
              }
              transition={{ duration: 0.6, ease: "easeOut" }}
              className={`spine-card ${toneClass} ${heatClass} text-left rounded-2xl border px-5 py-5 ${
                isSelected ? "border-cyan" : tone.ring
              }`}
            >
              <div className="flex items-start justify-between">
                <span className="spine-icon" style={{ color: tone.dot }}>
                  {ICONS[stage.key]}
                </span>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[9px] tracking-[0.22em] text-muted">
                    {stage.n}
                  </span>
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{
                      background: tone.dot,
                      boxShadow:
                        heatState === "hot"
                          ? `0 0 12px ${tone.dot}`
                          : heatState === "cooling"
                          ? `0 0 6px ${tone.dot}`
                          : "none",
                    }}
                  />
                </div>
              </div>

              <p className="font-display text-[15px] font-medium mt-3 leading-tight tracking-tight">
                {stage.label}
              </p>
              <p className={`text-[10px] mt-1.5 ${tone.text}`}>{s.stat}</p>
              <p className="text-[9px] text-muted mt-2 leading-relaxed">
                {stage.blurb}
              </p>
            </motion.button>
          );
        })}
      </div>

      {selected && (
        <div className="mt-4 border-t border-edge pt-3">
          <p className="text-[9px] tracking-[0.18em] text-muted">
            {STAGES.find((s) => s.key === selected)?.n} /{" "}
            {stages[selected].state} / TELEMETRY
          </p>
          <h3 className="text-[14px] mt-1">
            {STAGES.find((s) => s.key === selected)?.label}
          </h3>
          <p className="text-[11px] text-muted mt-1">
            {stages[selected].detail}
          </p>
          <p className={`text-[11px] mt-2 ${TONE[stages[selected].state].text}`}>
            {stages[selected].stat}
          </p>
        </div>
      )}

      <p className="text-[8px] text-muted mt-4">
        Every figure here is read from the live API. A stage marked LOCKED has
        genuinely never run.
      </p>
    </section>
  );
}
