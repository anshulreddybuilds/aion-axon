import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";

/**
 * SYNAPSE THEATER — the hero visual (§5.1).
 *
 * The six runtime agents of §6.1 working side by side, with pulses
 * travelling the edges between them.
 *
 * The rule this component exists to honour: **every animation narrates a
 * real system event.** A pulse fires on an edge only when that agent's own
 * counter actually moved between two polls of the live API. Nothing here
 * loops for atmosphere. An idle theatre is a truthful theatre — if nothing
 * is animating, nothing is happening, and that is worth being able to see.
 *
 * Depth is done with layered SVG gradients, blur and a CSS perspective
 * tilt rather than WebGL. §5.1 bans heavy 3D for a specific reason: the
 * demo is screen-recorded on an 8GB machine, and a dropped frame reads to
 * a viewer as an unreliable system. This gets the dimensionality without
 * putting the video at risk.
 *
 * Every number rendered comes from the live API. An agent that has never
 * run is drawn dim and says so, rather than being hidden to keep the
 * picture tidy.
 */

const PULSE_MS = 1400;

/** The §6.1 runtime agents, in the order work actually flows through them. */
const AGENTS = [
  {
    key: "orchestrator",
    label: "ORCHESTRATOR",
    role: "owns the mission",
    model: "Flash",
  },
  {
    key: "researcher",
    label: "RESEARCHER",
    role: "finds approaches",
    model: "Flash + Search",
  },
  {
    key: "builder",
    label: "BUILDER",
    role: "writes the candidate",
    model: "Flash",
  },
  {
    key: "sandbox",
    label: "SANDBOX",
    role: "runs it in isolation",
    model: "service",
  },
  {
    key: "evaluator",
    label: "EVALUATOR",
    role: "scores the result",
    model: "Gemma",
  },
  {
    key: "guardian",
    label: "GUARDIAN",
    role: "deny by default",
    model: "policy",
  },
];

/**
 * Map the live API onto the six agents.
 *
 * `count` is the number this agent's pulse watches — when it rises between
 * polls, that agent genuinely did something and earns an animation.
 */
function readAgents({ telemetry, sandbox, pending, killed, capabilities }) {
  const stages = telemetry?.by_stage || {};
  const execs = telemetry?.tool_executions || {};

  // Research reports its stage as `research` when grounded and
  // `research_degraded` when the free tier refuses it. Both are the
  // Researcher working; collapsing them would hide the degraded case,
  // so the label below says which one actually happened.
  const research = stages.research || {};
  const degraded = stages.research_degraded || {};
  const researchCalls = (research.calls || 0) + (degraded.calls || 0);

  const generate = stages.generate || {};
  const evaluate = stages.evaluate || {};

  return {
    orchestrator: {
      count: capabilities?.implemented ?? 0,
      // Checking the FIELD, not the object. loadAll falls back to
      // `{ capabilities: [] }` on a failed fetch, which is truthy and
      // rendered "undefined/undefined skills" the first time this hit a
      // live endpoint it could not reach.
      stat:
        capabilities?.implemented != null
          ? `${capabilities.implemented}/${capabilities.total} skills`
          : "unreachable",
      detail: "capabilities it can delegate to",
      live: (capabilities?.implemented ?? 0) > 0,
    },
    researcher: {
      count: researchCalls,
      stat: researchCalls
        ? `${researchCalls} call${researchCalls === 1 ? "" : "s"}`
        : "never run",
      detail: degraded.calls
        ? `${degraded.calls} degraded — grounding quota-blocked`
        : "Search grounding",
      live: researchCalls > 0,
      warn: !!degraded.calls,
    },
    builder: {
      count: generate.calls || 0,
      stat: generate.calls
        ? `${generate.tokens?.toLocaleString() ?? 0} tokens`
        : "never run",
      detail: generate.calls
        ? `${generate.calls} candidate${generate.calls === 1 ? "" : "s"} written`
        : "generates capability code",
      live: (generate.calls || 0) > 0,
    },
    sandbox: {
      count: execs.count || 0,
      // Deliberately "gated runs", not "sandbox runs". `tool_executions`
      // counts everything that passed through the ExecutionGate, which
      // includes native tools that never touch the sandbox. Calling that
      // number "sandbox executions" would inflate the isolation claim,
      // and the isolation claim is one this project has to be able to
      // defend precisely. The verdict underneath is the sandbox's own.
      stat: execs.count
        ? `${execs.count} gated run${execs.count === 1 ? "" : "s"}`
        : "never run",
      detail:
        sandbox?.verdict === "ZERO_CREDENTIALS"
          ? "zero credentials — verified"
          : "isolation unverified",
      live: (execs.count || 0) > 0,
      warn: sandbox?.verdict !== "ZERO_CREDENTIALS",
    },
    evaluator: {
      count: evaluate.calls || 0,
      stat: evaluate.calls
        ? `${evaluate.calls} scored`
        : "never run",
      detail: evaluate.calls ? "Gemma second opinion" : "scores test output",
      live: (evaluate.calls || 0) > 0,
    },
    guardian: {
      // Guardian's "activity" is the queue it is holding. A rising queue
      // means it just stopped something, which is exactly when it should
      // light up.
      count: pending?.length ?? 0,
      stat: killed
        ? "HALTED"
        : pending?.length
        ? `${pending.length} held`
        : "clear",
      detail: killed ? "kill switch active" : "deny-by-default",
      live: true, // Guardian is always on. That is the point of Guardian.
      danger: killed || !!pending?.length,
    },
  };
}

export default function SynapseTheater(props) {
  const state = useMemo(() => readAgents(props), [props]);
  const { killed } = props;

  // Which agents fired recently. Populated only by a real counter delta.
  const [firing, setFiring] = useState({});
  const previous = useRef(null);

  useEffect(() => {
    const counts = Object.fromEntries(
      AGENTS.map(({ key }) => [key, state[key].count])
    );

    // First poll establishes a baseline. Treating initial values as
    // "activity" would light the whole board on page load and make the
    // animation a lie the very first time anyone looks at it.
    if (previous.current === null) {
      previous.current = counts;
      return;
    }

    const moved = AGENTS.filter(
      ({ key }) => counts[key] > (previous.current[key] ?? 0)
    ).map(({ key }) => key);

    previous.current = counts;

    if (!moved.length) return;

    const now = Date.now();
    setFiring((f) => ({
      ...f,
      ...Object.fromEntries(moved.map((k) => [k, now])),
    }));

    const timer = setTimeout(() => {
      setFiring((f) => {
        const next = { ...f };
        for (const k of moved) if (next[k] === now) delete next[k];
        return next;
      });
    }, PULSE_MS);

    return () => clearTimeout(timer);
  }, [state]);

  const COL = 172;
  const W = COL * AGENTS.length;
  const H = 210;
  const Y = 104;

  return (
    <section className="bg-panel border border-edge rounded-lg p-4 overflow-hidden">
      <div className="flex items-baseline justify-between mb-1">
        <h2 className="text-[11px] tracking-[0.2em] text-muted">
          SYNAPSE THEATER
        </h2>
        <span className="text-[9px] text-muted">
          six runtime agents · live
        </span>
      </div>
      <p className="text-[9px] text-muted mb-2">
        A node pulses only when its own counter moves. A still board means
        the system is genuinely idle.
      </p>

      <div
        className="overflow-x-auto scroll-thin"
        style={{ perspective: "1100px" }}
      >
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          style={{
            // Low enough that all SIX agents fit without horizontal
            // scroll on a laptop panel. Guardian being the one clipped
            // off the end would be a poor accident: it is the agent the
            // whole governance story rests on.
            minWidth: 620,
            transform: "rotateX(9deg)",
            transformOrigin: "50% 100%",
          }}
        >
          <defs>
            <linearGradient id="rail" x1="0" x2="1">
              <stop offset="0%" stopColor="#1b2432" />
              <stop offset="50%" stopColor="#243044" />
              <stop offset="100%" stopColor="#1b2432" />
            </linearGradient>
            <filter id="soft" x="-60%" y="-60%" width="220%" height="220%">
              <feGaussianBlur stdDeviation="7" />
            </filter>
            {["#37e0d8", "#4ade80", "#f87171", "#7d8899"].map((c, i) => (
              <radialGradient key={i} id={`halo${i}`} cx="50%" cy="50%">
                <stop offset="0%" stopColor={c} stopOpacity="0.55" />
                <stop offset="100%" stopColor={c} stopOpacity="0" />
              </radialGradient>
            ))}
          </defs>

          {/* The rail every agent sits on — the mission's path through them. */}
          <line
            x1={COL / 2}
            y1={Y}
            x2={W - COL / 2}
            y2={Y}
            stroke="url(#rail)"
            strokeWidth="2"
          />

          {AGENTS.map((agent, i) => {
            const s = state[agent.key];
            const x = COL * i + COL / 2;
            const isFiring = !!firing[agent.key];

            const colour = s.danger
              ? "#f87171"
              : s.warn
              ? "#4ade80"
              : s.live
              ? "#37e0d8"
              : "#7d8899";

            const haloIndex = s.danger ? 2 : s.warn ? 1 : s.live ? 0 : 3;

            const nextX = COL * (i + 1) + COL / 2;

            return (
              <g key={agent.key}>
                {/* Pulse travelling to the NEXT agent — drawn only while
                    this one is genuinely firing. */}
                {isFiring && i < AGENTS.length - 1 && (
                  <motion.circle
                    r="4"
                    fill={colour}
                    initial={{ cx: x, cy: Y, opacity: 0 }}
                    animate={{ cx: nextX, cy: Y, opacity: [0, 1, 1, 0] }}
                    transition={{ duration: PULSE_MS / 1000, ease: "easeInOut" }}
                  />
                )}

                {/* Depth halo. Dim agents get a dim halo; nothing glows
                    that has not earned it. */}
                <circle
                  cx={x}
                  cy={Y}
                  r={isFiring ? 54 : 40}
                  fill={`url(#halo${haloIndex})`}
                  filter="url(#soft)"
                  opacity={s.live ? (isFiring ? 1 : 0.5) : 0.18}
                />

                <motion.circle
                  cx={x}
                  cy={Y}
                  r="27"
                  fill="#0c1119"
                  stroke={colour}
                  strokeWidth={isFiring ? 2 : 1.3}
                  animate={isFiring ? { scale: [1, 1.14, 1] } : { scale: 1 }}
                  transition={{ duration: 0.55, repeat: isFiring ? 1 : 0 }}
                  style={{ transformOrigin: `${x}px ${Y}px` }}
                  opacity={s.live ? 1 : 0.45}
                />

                <text
                  x={x}
                  y={Y + 4}
                  textAnchor="middle"
                  style={{
                    fontSize: 15,
                    fontWeight: 600,
                    fill: colour,
                    opacity: s.live ? 1 : 0.5,
                  }}
                >
                  {i + 1}
                </text>

                <text
                  x={x}
                  y={Y - 44}
                  textAnchor="middle"
                  style={{
                    fontSize: 8.5,
                    letterSpacing: 1.3,
                    fill: s.live ? "#e6edf5" : "#7d8899",
                  }}
                >
                  {agent.label}
                </text>

                <text
                  x={x}
                  y={Y + 46}
                  textAnchor="middle"
                  style={{ fontSize: 9, fill: colour, fontWeight: 600 }}
                >
                  {s.stat}
                </text>
                <text
                  x={x}
                  y={Y + 60}
                  textAnchor="middle"
                  style={{ fontSize: 7.5, fill: "#7d8899" }}
                >
                  {s.detail}
                </text>
                <text
                  x={x}
                  y={Y + 73}
                  textAnchor="middle"
                  style={{ fontSize: 7, fill: "#4a5666", letterSpacing: 0.6 }}
                >
                  {agent.model}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {killed && (
        <p className="mt-2 text-[10px] text-danger">
          Kill switch is active. Guardian is holding the whole chain.
        </p>
      )}
    </section>
  );
}
