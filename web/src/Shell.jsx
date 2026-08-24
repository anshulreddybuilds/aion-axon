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

export function Sidebar({ view, onView }) {
  const items = [
    { key: "command", label: "Command" },
    { key: "pipeline", label: "Pipeline" },
    { key: "ledger", label: "Autonomy ledger" },
    { key: "evidence", label: "Evidence" },
    { key: "judge", label: "Judge Mode" },
  ];

  return (
    <aside className="hidden lg:flex flex-col w-[210px] shrink-0 border-r border-edge bg-panel/40">
      <div className="px-5 py-5 border-b border-edge">
        <div className="flex items-center gap-2.5">
          <span className="h-7 w-7 rounded-md border border-cyan/50 grid place-items-center text-cyan text-[11px]">
            ◈
          </span>
          <div>
            <p className="text-[13px] tracking-[0.16em] leading-none">
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
        {items.map((item) => (
          <button
            key={item.key}
            onClick={() => onView(item.key)}
            className={`w-full text-left text-[12px] px-3 py-2 rounded-md mb-1 transition-colors ${
              view === item.key
                ? "bg-cyan/10 text-cyan border border-cyan/30"
                : "text-muted hover:text-white border border-transparent"
            }`}
          >
            {item.label}
          </button>
        ))}
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

export function TopStrip({ online, killed, revision }) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-5 py-3 border-b border-edge text-[9px] tracking-[0.16em]">
      <span className="text-muted">
        AXON NODE / ASIA-SOUTH1
      </span>
      <span className="flex items-center gap-1.5">
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            killed ? "bg-danger" : online ? "bg-ok" : "bg-danger"
          }`}
        />
        <span className={killed ? "text-danger" : online ? "text-ok" : "text-danger"}>
          {killed ? "HALTED — KILL SWITCH" : online ? "SYSTEM NOMINAL" : "UNREACHABLE"}
        </span>
      </span>

      <span className="ml-auto flex items-center gap-2 text-muted">
        <span className={`h-1.5 w-1.5 rounded-full ${online ? "bg-cyan" : "bg-edge"}`} />
        {online ? "LIVE — CLOUD RUN" : "OFFLINE"}
      </span>
    </div>
  );
}

export function Hero({ crumb, title, blurb, pendingCount }) {
  return (
    <div className="px-5 pt-6 pb-5">
      <p className="text-[9px] tracking-[0.22em] text-muted mb-3">
        —— MISSION CONTROL / {crumb}
      </p>

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-[560px]">
          <h1 className="text-[34px] leading-[1.1] font-semibold tracking-tight">
            {title}
          </h1>
          <p className="text-[12px] text-muted mt-3 leading-relaxed">
            {blurb}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`text-[10px] tracking-[0.14em] px-3 py-2 rounded-md border ${
              pendingCount
                ? "border-warn/50 text-warn"
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
    <section className="bg-panel border border-edge rounded-lg p-5">
      <div className="flex items-baseline justify-between">
        <p className="text-[9px] tracking-[0.22em] text-muted">SPINE STATUS</p>
        <p className="text-[9px] tracking-[0.14em] text-muted">
          LIVE / {pct}%
        </p>
      </div>

      <div className="grid place-items-center py-5">
        <svg viewBox="0 0 140 140" className="w-[150px]">
          <circle cx="70" cy="70" r={R} fill="none" stroke="#1b2432" strokeWidth="8" />
          <circle
            cx="70"
            cy="70"
            r={R}
            fill="none"
            stroke="#37e0d8"
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={C}
            strokeDashoffset={C - (C * pct) / 100}
            transform="rotate(-90 70 70)"
          />
          <text
            x="70"
            y="70"
            textAnchor="middle"
            className="fill-white"
            style={{ fontSize: 26, fontWeight: 600 }}
          >
            {pct}%
          </text>
          <text
            x="70"
            y="86"
            textAnchor="middle"
            style={{ fontSize: 7.5, fill: "#7d8899", letterSpacing: 1.4 }}
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
