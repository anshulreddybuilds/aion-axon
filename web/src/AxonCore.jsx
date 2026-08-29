import { motion, AnimatePresence } from "framer-motion";
import { describeStage } from "./livePipeline.js";

/**
 * AXON CORE — an original, state-driven visualization of the one
 * genuinely real-time process this system has: capability acquisition,
 * streamed stage-by-stage over GET /synapse/propose/stream (see
 * api.js's consumeStageStream and this file's sibling livePipeline.js).
 *
 * Every node corresponds to a real stage in the governed pipeline
 * (research -> generate -> screen -> sandbox -> evaluate -> guardian ->
 * approval) that exists in the backend today, app/synapse/engine.py.
 * Progress around the ring is read directly off `record.stage`, the
 * field the real backend sets on every streamed frame; nothing here
 * invents a stage the record hasn't reported, and nothing keeps
 * animating once the real stream stops or the record goes idle.
 *
 * Design law: calm when idle, alive while a real stage is in flight,
 * focused when a real approval gate is open, quiet on everything not
 * currently happening, expansive only at a real, meaningful moment — a
 * capability actually finishing installation.
 *
 * No face. No mascot. Identity comes from the pipeline's own real
 * shape and the colors that carry its meaning (see STAGE below).
 */

const RING_STAGES = [
  { key: "RESEARCH", label: "Research", color: "#37e0d8" },
  { key: "GENERATE", label: "Generate", color: "#c084fc" },
  { key: "SAFETY_SCREEN", label: "Screen", color: "#38bdf8" },
  { key: "SANDBOX_TEST", label: "Sandbox", color: "#38bdf8" },
  { key: "EVALUATE", label: "Evaluate", color: "#c084fc" },
  { key: "GUARDIAN_SCREEN", label: "Guardian", color: "#fbbf24" },
  { key: "AWAITING_APPROVAL", label: "Approval", color: "#fbbf24" },
];

const DANGER = "#f87171";
const OK = "#4ade80";
const CORE_IDLE = "#37e0d8";

function stageIndex(key) {
  return RING_STAGES.findIndex((s) => s.key === key);
}

export default function AxonCore({ record, running }) {
  const size = 380;
  const cx = size / 2;
  const cy = size / 2;
  const R = size * 0.34;

  // The pipeline's own doorway. Refused/blocked here means nothing past
  // it ever ran -- the ring must not imply progress that didn't happen.
  const stoppedAtDoor =
    record?.stage === "GUARDIAN_PRESCREEN" &&
    (record.status === "REFUSED" || record.status === "BLOCKED");

  const installed = record?.status === "INSTALLED";
  const terminalFailed =
    ["REJECTED", "REFUSED", "BLOCKED", "FAILED"].includes(record?.status) &&
    !stoppedAtDoor;

  const activeIdx = record ? stageIndex(record.stage) : -1;
  const current = record ? describeStage(record) : null;
  const idle = !running && !record;
  const coreColor = stoppedAtDoor || terminalFailed ? DANGER : installed ? OK : CORE_IDLE;

  return (
    <div className="relative flex flex-col items-center py-4">
      <svg viewBox={`0 0 ${size} ${size}`} className="w-full max-w-[340px]">
        {RING_STAGES.map((s, i) => {
          const angle = (i / RING_STAGES.length) * 2 * Math.PI - Math.PI / 2;
          const x = cx + R * Math.cos(angle);
          const y = cy + R * Math.sin(angle);
          const done = activeIdx > i || installed;
          const active = activeIdx === i && !installed;
          const failed = active && terminalFailed;
          return (
            <motion.line
              key={`line-${s.key}`}
              x1={cx}
              y1={cy}
              x2={x}
              y2={y}
              stroke={failed ? DANGER : done || active ? s.color : "#1b2432"}
              strokeWidth={active ? 2 : 1}
              animate={{ opacity: idle ? 0.12 : done ? 0.5 : active ? 0.9 : 0.15 }}
              transition={{ duration: 0.6 }}
            />
          );
        })}

        <motion.circle
          cx={cx}
          cy={cy}
          r={idle ? 32 : 40}
          fill="none"
          stroke={coreColor}
          strokeWidth={2}
          className={idle ? "orb-breathe" : ""}
          animate={{ r: idle ? 32 : 40 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          style={{ transformOrigin: `${cx}px ${cy}px` }}
        />
        <circle cx={cx} cy={cy} r={4} fill={coreColor} />

        {RING_STAGES.map((s, i) => {
          const angle = (i / RING_STAGES.length) * 2 * Math.PI - Math.PI / 2;
          const x = cx + R * Math.cos(angle);
          const y = cy + R * Math.sin(angle);
          const done = activeIdx > i || installed;
          const active = activeIdx === i && !installed;
          const failed = active && terminalFailed;
          const color = failed ? DANGER : done || active ? s.color : "#3a4657";

          return (
            <g key={s.key}>
              <motion.circle
                cx={x}
                cy={y}
                r={active ? 10 : done ? 7 : 5}
                fill={active || done ? color : "#0c1119"}
                stroke={color}
                strokeWidth={1.5}
                animate={{
                  r: active ? 10 : done ? 7 : 5,
                  opacity: idle ? 0.25 : active ? 1 : done ? 0.85 : 0.35,
                }}
                style={{ filter: active ? `drop-shadow(0 0 8px ${color})` : "none" }}
                transition={{ duration: 0.5 }}
              />
              <text
                x={x}
                y={y + (y > cy ? 18 : -14)}
                textAnchor="middle"
                style={{
                  fontSize: 8.5,
                  letterSpacing: 1,
                  fill: active ? color : "#7d8899",
                  opacity: idle ? 0.2 : active ? 1 : done ? 0.7 : 0.4,
                  fontWeight: active ? 600 : 400,
                }}
              >
                {s.label.toUpperCase()}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="mt-1 text-center min-h-[44px] max-w-[320px]">
        <AnimatePresence mode="wait">
          {idle && (
            <motion.p
              key="idle"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="text-[10px] tracking-[0.24em] text-muted"
            >
              AXON IS IDLE
            </motion.p>
          )}

          {!idle && !record && running && (
            <motion.p
              key="connecting"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="text-[10px] tracking-[0.24em] text-cyan"
            >
              CONNECTING TO THE PIPELINE…
            </motion.p>
          )}

          {stoppedAtDoor && (
            <motion.div key="door" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <p className="text-[10px] tracking-[0.2em] text-danger">
                REFUSED AT THE DOOR
              </p>
              <p className="text-[10px] text-muted mt-1">{record.reason}</p>
            </motion.div>
          )}

          {installed && (
            <motion.div
              key="installed"
              initial={{ opacity: 0, y: 8, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.5, ease: "easeOut" }}
            >
              <p className="text-[9px] tracking-[0.26em] text-ok/80">NEW CAPABILITY</p>
              <p className="font-display text-[14px] tracking-[0.04em] text-ok mt-0.5">
                {record.candidate?.name}
              </p>
              <p className="text-[10px] text-muted mt-1">welcome to AXON</p>
            </motion.div>
          )}

          {current && !installed && !stoppedAtDoor && (
            <motion.div
              key={current.label}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
            >
              <p className={`text-[11px] tracking-[0.08em] ${terminalFailed ? "text-danger" : "text-white"}`}>
                {current.label}
              </p>
              {current.detail && (
                <p className="text-[10px] text-muted mt-0.5">{current.detail}</p>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
