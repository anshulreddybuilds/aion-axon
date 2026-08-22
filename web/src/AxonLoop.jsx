import { motion } from "framer-motion";

/**
 * The hero visual: AXON at the centre, ringed by the four phases of the
 * governed loop.
 *
 * Only THREE states animate (§5.1): working, approval, refusal. Idle is
 * deliberately still. Motion here narrates a real event — a node pulses
 * because that phase is actually active, never because movement looks
 * good. Inline SVG, no WebGL: the demo is recorded and jank is visible.
 */

const NODES = [
  { key: "understand", label: "UNDERSTAND", angle: -90 },
  { key: "execute", label: "EXECUTE", angle: 0 },
  { key: "learn", label: "LEARN", angle: 90 },
  { key: "govern", label: "GOVERN", angle: 180 },
];

const RADIUS = 118;

function position(angle) {
  const radians = (angle * Math.PI) / 180;
  return { x: 180 + RADIUS * Math.cos(radians), y: 170 + RADIUS * Math.sin(radians) };
}

export default function AxonLoop({ state, activePhase }) {
  const accent =
    state === "refusal" ? "#f87171" : state === "approval" ? "#4ade80" : "#37e0d8";

  const busy = state === "working";

  return (
    <svg viewBox="0 0 360 340" className="w-full max-w-[420px] mx-auto">
      <defs>
        <radialGradient id="core" cx="50%" cy="50%">
          <stop offset="0%" stopColor={accent} stopOpacity="0.85" />
          <stop offset="70%" stopColor={accent} stopOpacity="0.12" />
          <stop offset="100%" stopColor={accent} stopOpacity="0" />
        </radialGradient>
      </defs>

      <circle
        cx="180"
        cy="170"
        r={RADIUS}
        fill="none"
        stroke="#1b2432"
        strokeWidth="1"
      />

      {/* The ring fills only while work is actually happening. */}
      {busy && (
        <motion.circle
          cx="180"
          cy="170"
          r={RADIUS}
          fill="none"
          stroke={accent}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeDasharray={2 * Math.PI * RADIUS}
          initial={{ strokeDashoffset: 2 * Math.PI * RADIUS }}
          animate={{ strokeDashoffset: 0 }}
          transition={{ duration: 2.4, repeat: Infinity, ease: "linear" }}
          opacity="0.7"
        />
      )}

      {/* The glow is always drawn; it only BREATHES while the system is
          actually working. It used to breathe unconditionally, which made
          it the one piece of motion on the page that narrated nothing —
          a page that claims every animation is a real event cannot also
          have a pulse that means "still on". An idle orb is now still. */}
      <circle
        cx="180"
        cy="170"
        r="74"
        fill="url(#core)"
        className={busy ? "orb-breathe" : undefined}
        opacity={busy ? 1 : 0.55}
      />

      <motion.circle
        cx="180"
        cy="170"
        r="38"
        fill="#0c1119"
        stroke={accent}
        strokeWidth="1.5"
        animate={
          state === "refusal"
            ? { scale: [1, 1.08, 1], stroke: ["#f87171", "#ffffff", "#f87171"] }
            : { scale: 1 }
        }
        transition={{ duration: 0.45, repeat: state === "refusal" ? 2 : 0 }}
        style={{ transformOrigin: "180px 170px" }}
      />

      <text
        x="180"
        y="167"
        textAnchor="middle"
        className="fill-white"
        style={{ fontSize: 15, letterSpacing: 3, fontWeight: 600 }}
      >
        AXON
      </text>
      <text
        x="180"
        y="184"
        textAnchor="middle"
        style={{ fontSize: 9, letterSpacing: 1.5, fill: accent }}
      >
        {state === "refusal"
          ? "REFUSED"
          : state === "approval"
          ? "AWAITING YOU"
          : busy
          ? "WORKING"
          : "IDLE"}
      </text>

      {NODES.map((node) => {
        const { x, y } = position(node.angle);
        const active = activePhase === node.key;

        return (
          <g key={node.key}>
            <line
              x1="180"
              y1="170"
              x2={x}
              y2={y}
              stroke={active ? accent : "#1b2432"}
              strokeWidth={active ? 1.4 : 1}
              opacity={active ? 0.8 : 0.5}
            />
            <motion.circle
              cx={x}
              cy={y}
              r="9"
              fill={active ? accent : "#0c1119"}
              stroke={active ? accent : "#1b2432"}
              strokeWidth="1.5"
              animate={active ? { scale: [1, 1.25, 1] } : { scale: 1 }}
              transition={{
                duration: 1.1,
                repeat: active ? Infinity : 0,
                ease: "easeInOut",
              }}
              style={{ transformOrigin: `${x}px ${y}px` }}
            />
            <text
              x={x}
              y={y + (node.angle === 90 ? 26 : node.angle === -90 ? -18 : 4)}
              textAnchor="middle"
              style={{
                fontSize: 8.5,
                letterSpacing: 1.4,
                fill: active ? accent : "#7d8899",
              }}
            >
              {node.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
