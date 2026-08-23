import { motion } from "framer-motion";
import { Activity, Gauge, Lock, Maximize2, Unlock } from "lucide-react";

/**
 * v2 chrome: the floating navigation island and the shared small parts.
 *
 * Every value rendered here is passed in from the live API by AppV2 —
 * there are no defaults that would let a panel display a plausible number
 * when the real one is missing. A missing value renders as "—".
 */

export function MicroLabel({ children, className = "" }) {
  return (
    <p
      className={`text-[10px] tracking-wider uppercase font-semibold text-zinc-400 ${className}`}
    >
      {children}
    </p>
  );
}

export function Pill({ children, tone = "neutral", className = "" }) {
  const tones = {
    neutral: "border-white/10 text-zinc-300",
    ok: "border-emerald-400/30 text-emerald-300",
    warn: "border-amber-400/30 text-amber-300",
    danger: "border-red-400/30 text-red-300",
    electric: "border-cobalt/40 text-electric",
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] tracking-wider uppercase font-semibold ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

export function Dot({ tone = "ok", live = false }) {
  const colors = {
    ok: "#4ade80",
    warn: "#fbbf24",
    danger: "#f87171",
    idle: "#3a4657",
    electric: "#38bdf8",
  };

  return (
    <span
      className="h-1.5 w-1.5 rounded-full shrink-0"
      style={{
        background: colors[tone],
        boxShadow: live ? `0 0 8px ${colors[tone]}` : "none",
      }}
    />
  );
}

/**
 * The floating nav island.
 *
 * `verifiedPct`, `online` and `quota` are real readings. The quota pill in
 * particular says what is actually known: this project's Gemini free tier
 * is 20 generations/day and the surface should not imply headroom it
 * cannot see.
 */
export function NavIsland({ online, killed, verifiedPct, unlocked, quotaNote }) {
  return (
    <div className="sticky top-0 z-40 px-4 pt-4">
      <div className="glass glass-spec rounded-2xl px-4 py-2.5 flex items-center gap-4">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="h-7 w-7 rounded-lg grid place-items-center neon-soft bg-cobalt/10 shrink-0">
            <Activity size={14} className="text-electric" />
          </div>
          <div className="min-w-0">
            <p className="text-[13px] font-semibold tracking-tight leading-none">
              AION AXON
            </p>
            <p className="text-[9px] tracking-wider uppercase text-zinc-500 mt-1 truncate">
              Axon Node / asia-south1
            </p>
          </div>
        </div>

        <div className="hidden md:flex flex-1 justify-center">
          <div className="glass rounded-full px-3.5 py-1.5 flex items-center gap-2.5">
            <Dot tone={killed ? "danger" : online ? "ok" : "warn"} live={online && !killed} />
            <span className="text-[10px] tracking-wider uppercase font-semibold text-zinc-300">
              {killed
                ? "Halted — kill switch"
                : online
                ? "System nominal"
                : "Core unreachable"}
            </span>
            <span className="text-zinc-600">·</span>
            <span className="text-[10px] tracking-wider uppercase font-semibold text-zinc-400">
              Live — Cloud Run
            </span>
            {verifiedPct != null && (
              <>
                <span className="text-zinc-600">·</span>
                <span className="text-[10px] tracking-wider uppercase font-semibold text-electric">
                  {verifiedPct}% verified
                </span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 ml-auto md:ml-0">
          <Pill tone={unlocked ? "ok" : "neutral"} className="hidden sm:inline-flex">
            {unlocked ? <Unlock size={11} /> : <Lock size={11} />}
            {unlocked ? "Unlocked" : "Locked"}
          </Pill>

          {quotaNote && (
            <Pill tone="warn" className="hidden lg:inline-flex">
              <Gauge size={11} />
              {quotaNote}
            </Pill>
          )}

          {/* One icon, not three.
              Settings and Logs had nothing behind them -- there is no
              settings surface and no log viewer to open, so both could
              only ever ignore a click. Fullscreen is kept because it does
              something real, and is genuinely useful when recording. */}
          <button
            type="button"
            onClick={() => {
              const el = document.documentElement;
              if (document.fullscreenElement) document.exitFullscreen?.();
              else el.requestFullscreen?.();
            }}
            title="Toggle fullscreen"
            className="h-7 w-7 grid place-items-center rounded-lg border border-white/[0.08] text-zinc-500 hover:text-electric hover:border-cobalt/40 transition-colors"
          >
            <Maximize2 size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}

/** Session label above the command capsule.
 *
 * Labels, not buttons. The Framer design this borrows from has a session
 * switcher and a "new session" plus because it has multiple sessions to
 * switch between; this surface has one. Both controls were rendered as
 * buttons that ignored every click -- the same defect the follow-up send
 * button had, and the one docs/upgrade-plan.md warns about directly:
 * "judges clicking a dead Approve button is worse than no button."
 */
export function SessionBar({ sessionLabel }) {
  return (
    <div className="flex items-center gap-2 mb-2.5">
      <span className="glass rounded-full px-3 py-1.5 inline-flex items-center text-[10px] tracking-wider uppercase font-semibold text-zinc-400">
        {sessionLabel}
      </span>
    </div>
  );
}

export function Card({ children, className = "", spec = true, ...rest }) {
  return (
    <section
      className={`glass ${spec ? "glass-spec" : ""} rounded-2xl ${className}`}
      {...rest}
    >
      {children}
    </section>
  );
}

export function CardHead({ label, title, right }) {
  return (
    <div className="flex items-start justify-between gap-3 mb-4">
      <div className="min-w-0">
        <MicroLabel>{label}</MicroLabel>
        <h2 className="text-[15px] font-semibold tracking-tight mt-1.5">
          {title}
        </h2>
      </div>
      {right}
    </div>
  );
}

/** A metric that refuses to invent a value. */
export function Metric({ value, unit, label }) {
  return (
    <div>
      <p className="text-[22px] font-semibold tracking-tight leading-none tabular-nums">
        {value ?? "—"}
        {value != null && unit ? (
          <span className="text-[12px] text-zinc-500 ml-1">{unit}</span>
        ) : null}
      </p>
      <MicroLabel className="mt-2">{label}</MicroLabel>
    </div>
  );
}

export const fadeUp = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.25, ease: "easeOut" },
};

export function Reveal({ children, delay = 0, className = "" }) {
  return (
    <motion.div
      initial={fadeUp.initial}
      animate={fadeUp.animate}
      transition={{ ...fadeUp.transition, delay }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
