import { motion } from "framer-motion";
import { backendLabel } from "./backendLabel.js";
import { STAGES } from "./Topology.jsx";

/**
 * The command-surface chrome: sidebar, top strip, hero, completion ring.
 *
 * Modelled on the owner's command-UI design. Where that design carried
 * placeholder figures — 42% build, five days complete, seven locked — this
 * derives the equivalent numbers from the live topology instead, because a
 * dashboard that understates a finished system is as dishonest as one that
 * overstates an unfinished one, and only one of those is usually noticed.
 */

// Shared by Sidebar (desktop, lg and up) and MobileNav (below lg) so the
// two can never drift out of sync -- a page reachable from one was
// unreachable from the other before MobileNav existed, since Sidebar's
// "hidden lg:flex" had no narrower-viewport equivalent at all: below
// 1024px, Pipeline/Autonomy Ledger/Evidence/Mission Theater/Judge Mode
// were not just visually hidden but structurally unreachable -- there is
// no separate URL per view (view is plain useState in App.jsx), so a
// phone or an unmaximized window landing on Command had no way to reach
// the other five screens at all.
const NAV_ITEMS = [
  { key: "command", label: "Command" },
  { key: "pipeline", label: "Pipeline" },
  { key: "ledger", label: "Autonomy ledger" },
  { key: "evidence", label: "Evidence" },
  { key: "theater", label: "Mission Theater" },
  { key: "judge", label: "Judge Mode" },
];

export function MobileNav({ view, onView }) {
  return (
    <nav className="lg:hidden flex gap-1.5 overflow-x-auto px-4 py-2.5 border-b border-edge bg-panel/40">
      {NAV_ITEMS.map((item) => {
        const active = view === item.key;
        return (
          <button
            key={item.key}
            onClick={() => onView(item.key)}
            className={`relative shrink-0 text-[11px] px-3 py-1.5 rounded-full whitespace-nowrap transition-colors duration-300 ${
              active
                ? "text-cyan bg-cyan/10 border border-cyan/30 shadow-[0_0_12px_rgba(55,224,216,0.18)]"
                : "text-muted border border-transparent hover:text-white"
            }`}
          >
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}

export function Sidebar({ view, onView }) {
  const items = NAV_ITEMS;

  return (
    <aside className="hidden lg:flex flex-col w-[210px] shrink-0 border-r border-edge bg-panel/40">
      <div className="px-5 py-5 border-b border-edge">
        <div className="flex items-center gap-2.5">
          <span className="h-8 w-8 rounded-lg border border-cyan/50 grid place-items-center text-cyan text-[13px] shadow-[0_0_16px_rgba(55,224,216,0.35)]">
            ◈
          </span>
          <div>
            <p className="font-display text-[13px] tracking-[0.16em] leading-none">
              AION AXON
            </p>
            <p className="text-[8px] tracking-[0.2em] text-muted mt-1">
              COMMAND / 01
            </p>
          </div>
        </div>
      </div>

      <nav className="px-3 py-4">
        <p className="text-[8px] tracking-[0.22em] text-muted px-2 mb-2">
          MISSION CONTROL
        </p>
        {items.map((item) => {
          const active = view === item.key;
          return (
            <button
              key={item.key}
              onClick={() => onView(item.key)}
              className={`relative w-full text-left text-[12px] px-3 py-2 rounded-md mb-1 transition-colors duration-300 ${
                active
                  ? "text-cyan"
                  : "text-muted hover:text-white"
              }`}
            >
              {active && (
                <motion.span
                  layoutId="navActivePill"
                  transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  className="absolute inset-0 rounded-md bg-cyan/10 border border-cyan/30 shadow-[0_0_18px_rgba(55,224,216,0.18)]"
                />
              )}
              <span className="relative">{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="mt-auto px-5 py-4 border-t border-edge">
        <p className="text-[8px] text-muted leading-relaxed">
          Every number on this surface is read from the live API. Nothing is
          mocked.
        </p>
      </div>
    </aside>
  );
}

export function TopStrip({ online, killed }) {
  const { node, live } = backendLabel();

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-5 py-3 border-b border-edge text-[9px] tracking-[0.16em]">
      <span className="text-muted">
        {node}
      </span>
      <span className="flex items-center gap-1.5">
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            killed ? "bg-danger" : online ? "bg-ok animate-pulse" : "bg-danger"
          }`}
          style={online && !killed ? { boxShadow: "0 0 8px rgba(74,222,128,0.7)" } : undefined}
        />
        <span className={killed ? "text-danger" : online ? "text-ok" : "text-danger"}>
          {killed ? "HALTED — KILL SWITCH" : online ? "SYSTEM NOMINAL" : "UNREACHABLE"}
        </span>
      </span>

      <span className="ml-auto flex items-center gap-2 text-muted">
        <span className={`h-1.5 w-1.5 rounded-full ${online ? "bg-cyan" : "bg-edge"}`} />
        {online ? live : "OFFLINE"}
      </span>
    </div>
  );
}

export function Hero({ crumb, title, blurb, pendingCount }) {
  return (
    <div className="px-5 pt-6 pb-5">
      <p className="flex items-center gap-2 text-[9px] tracking-[0.22em] text-muted mb-3">
        <span
          className="h-1.5 w-1.5 rounded-full bg-cyan animate-pulse"
          style={{ boxShadow: "0 0 8px rgba(55,224,216,0.8)" }}
        />
        MISSION CONTROL / {crumb}
      </p>

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-[560px]">
          <h1 className="font-display text-[36px] md:text-[42px] leading-[1.08] font-semibold tracking-tight text-glow-gradient">
            {title}
          </h1>
          <p className="text-[12px] text-muted mt-3 leading-relaxed">
            {blurb}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`text-[10px] tracking-[0.14em] px-3 py-2 rounded-md border transition-shadow ${
              pendingCount
                ? "border-warn/50 text-warn shadow-[0_0_16px_rgba(251,191,36,0.2)]"
                : "border-edge text-muted"
            }`}
          >
            APPROVAL QUEUE {String(pendingCount).padStart(2, "0")}
          </span>
        </div>
      </div>
    </div>
  );
}

/**
 * Completion ring. The design showed a hard-coded 42%; this counts how many
 * of the twelve spine stages are actually VERIFIED right now, so the number
 * moves when the system does and cannot silently go stale.
 */
export function CompletionRing({ stageStates }) {
  const verified = STAGES.filter((s) => stageStates[s.key] === "VERIFIED").length;
  const degraded = STAGES.filter((s) => stageStates[s.key] === "DEGRADED").length;
  const locked = STAGES.length - verified - degraded;
  const pct = Math.round((verified / STAGES.length) * 100);

  const R = 54;
  const C = 2 * Math.PI * R;

  return (
    <section className="panel-glass rounded-2xl p-6">
      <div className="flex items-baseline justify-between">
        <p className="text-[9px] tracking-[0.22em] text-muted">SPINE STATUS</p>
        <p className="text-[9px] tracking-[0.14em] text-muted">
          LIVE / {pct}%
        </p>
      </div>

      <div className="grid place-items-center py-6">
        <svg viewBox="0 0 170 170" className="w-[190px] overflow-visible">
          <defs>
            <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#37e0d8" />
              <stop offset="55%" stopColor="#38bdf8" />
              <stop offset="100%" stopColor="#8b5cf6" />
            </linearGradient>
            <filter id="ringGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {Array.from({ length: 24 }).map((_, i) => {
            const angle = (i / 24) * 2 * Math.PI;
            const x1 = 85 + (R + 12) * Math.cos(angle);
            const y1 = 85 + (R + 12) * Math.sin(angle);
            const x2 = 85 + (R + 16) * Math.cos(angle);
            const y2 = 85 + (R + 16) * Math.sin(angle);
            return (
              <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#1b2432" strokeWidth="2" />
            );
          })}

          <circle cx="85" cy="85" r={R} fill="none" stroke="#141b26" strokeWidth="9" />
          <circle
            cx="85"
            cy="85"
            r={R}
            fill="none"
            stroke="url(#ringGrad)"
            strokeWidth="9"
            strokeLinecap="round"
            strokeDasharray={C}
            strokeDashoffset={C - (C * pct) / 100}
            transform="rotate(-90 85 85)"
            filter="url(#ringGlow)"
            style={{ transition: "stroke-dashoffset 0.9s cubic-bezier(0.16,1,0.3,1)" }}
          />
          <text
            x="85"
            y="83"
            textAnchor="middle"
            className="fill-white font-display"
            style={{ fontSize: 30, fontWeight: 600 }}
          >
            {pct}%
          </text>
          <text
            x="85"
            y="101"
            textAnchor="middle"
            style={{ fontSize: 8, fill: "#7d8899", letterSpacing: 1.6 }}
          >
            STAGES VERIFIED
          </text>
        </svg>
      </div>

      <p className="text-[10px] text-muted leading-relaxed text-center">
        {verified} of {STAGES.length} spine stages have done real work and can
        prove it.
      </p>

      <div className="grid grid-cols-3 gap-2 mt-4 pt-4 border-t border-edge text-center">
        <div>
          <p className="text-[17px] text-cyan">{String(verified).padStart(2, "0")}</p>
          <p className="text-[8px] tracking-[0.16em] text-muted mt-0.5">VERIFIED</p>
        </div>
        <div>
          <p className="text-[17px] text-warn">{String(degraded).padStart(2, "0")}</p>
          <p className="text-[8px] tracking-[0.16em] text-muted mt-0.5">DEGRADED</p>
        </div>
        <div>
          <p className="text-[17px] text-muted">{String(locked).padStart(2, "0")}</p>
          <p className="text-[8px] tracking-[0.16em] text-muted mt-0.5">LOCKED</p>
        </div>
      </div>
    </section>
  );
}
