import { AnimatePresence, motion } from "framer-motion";

/** Shared shell. Panels are calm by design — one hero effect only. */
export function Panel({ title, right, children, tone = "edge" }) {
  const border = tone === "danger" ? "border-danger/40" : "border-edge";

  return (
    <section className={`bg-panel border ${border} rounded-lg p-4`}>
      <header className="flex items-center justify-between mb-3">
        <h2 className="text-[10px] tracking-[0.18em] text-muted uppercase">
          {title}
        </h2>
        {right}
      </header>
      {children}
    </section>
  );
}

export function Empty({ children }) {
  // An empty panel is correct behaviour, not a bug. Never fake data to
  // make a panel look alive.
  return <p className="text-xs text-muted italic">{children}</p>;
}

export function LiveBadge({ online }) {
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span
        className={`h-2 w-2 rounded-full ${
          online ? "bg-ok" : "bg-danger"
        } ${online ? "orb-breathe" : ""}`}
      />
      <span className={online ? "text-ok" : "text-danger"}>
        {online ? "LIVE — Cloud Run / aion-core" : "OFFLINE"}
      </span>
    </div>
  );
}

export function CapabilityCounter({ implemented, total }) {
  return (
    <Panel title="Capability Registry">
      <div className="flex items-baseline gap-2">
        <motion.span
          key={implemented}
          initial={{ scale: 1.4, color: "#37e0d8" }}
          animate={{ scale: 1, color: "#ffffff" }}
          transition={{ duration: 0.45 }}
          className="text-4xl font-semibold tabular-nums"
        >
          {implemented ?? "—"}
        </motion.span>
        <span className="text-muted text-sm">/ {total ?? "—"} known</span>
      </div>
      <p className="text-[11px] text-muted mt-1">
        implemented · the rest are declared but unbuilt
      </p>
    </Panel>
  );
}

export function AutonomyLedger({ tracked, threshold }) {
  return (
    <Panel title="Autonomy Ledger">
      {!tracked?.length ? (
        <Empty>No capability has been scored yet.</Empty>
      ) : (
        <ul className="space-y-3">
          {tracked.map((c) => {
            const pct = Number(c.autonomy_pct ?? 0);
            const supervised = pct < threshold;

            return (
              <li key={c.name}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="font-mono">{c.name}</span>
                  <span
                    className={supervised ? "text-danger" : "text-ok"}
                    style={{ fontVariantNumeric: "tabular-nums" }}
                  >
                    {pct.toFixed(0)}%
                  </span>
                </div>
                <div className="h-1.5 bg-edge rounded overflow-hidden">
                  <motion.div
                    className={`h-full ${supervised ? "bg-danger" : "bg-ok"}`}
                    initial={false}
                    animate={{ width: `${Math.max(pct, 2)}%` }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                  />
                </div>
                {supervised && (
                  <p className="text-[10px] text-danger mt-1">
                    below {threshold}% — human verification required (G-07)
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

export function ApprovalCard({ pending, onDecide, busy }) {
  return (
    <Panel
      title="Human Approval"
      tone={pending?.length ? "danger" : "edge"}
      right={
        pending?.length ? (
          <span className="text-[10px] text-cyan">{pending.length} waiting</span>
        ) : null
      }
    >
      <AnimatePresence mode="popLayout">
        {!pending?.length ? (
          <Empty>Nothing is waiting on you.</Empty>
        ) : (
          pending.slice(0, 3).map((request) => (
            <motion.div
              key={request.request_id}
              layout
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              className="border border-cyan/40 rounded p-3 mb-2"
            >
              <p className="text-sm mb-1">{request.action}</p>
              <p className="text-[11px] text-muted mb-3">{request.reason}</p>
              <div className="flex gap-2">
                <button
                  disabled={busy}
                  onClick={() => onDecide(request.request_id, true)}
                  className="px-3 py-1 text-xs rounded bg-ok/15 text-ok border border-ok/40 hover:bg-ok/25 disabled:opacity-40"
                >
                  Approve
                </button>
                <button
                  disabled={busy}
                  onClick={() => onDecide(request.request_id, false)}
                  className="px-3 py-1 text-xs rounded bg-danger/15 text-danger border border-danger/40 hover:bg-danger/25 disabled:opacity-40"
                >
                  Reject
                </button>
              </div>
            </motion.div>
          ))
        )}
      </AnimatePresence>
    </Panel>
  );
}

export function EvidencePanel({ capability }) {
  const passport = capability?.passport;
  const tests = passport?.tests;
  const evaluation = passport?.evaluation;
  const research = passport?.research;

  const rows = passport
    ? [
        ["candidate generated", !!passport.candidate],
        ["static safety screen", passport.safety?.safe === true],
        ["sandbox tests passed", tests?.passed === true],
        ["evaluator scored", evaluation?.status === "SCORED"],
        ["research grounded", research?.grounded === true],
        ["human approved", !!capability.approved_by],
      ]
    : [];

  return (
    <Panel title="Evidence Engine">
      {!passport ? (
        <Empty>Select an acquired capability to see its evidence.</Empty>
      ) : (
        <>
          <ul className="space-y-1 font-mono text-[11px]">
            {rows.map(([label, ok]) => (
              <li key={label} className={ok ? "text-ok" : "text-muted"}>
                {ok ? "✓" : "✗"} {label}
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[11px] text-cyan">
            CONFIDENCE:{" "}
            {evaluation?.score != null
              ? `${Number(evaluation.score).toFixed(1)}%`
              : "UNSCORED"}
          </p>
          {evaluation?.status === "UNSCORED" && (
            <p className="text-[10px] text-muted mt-1">
              No machine score available — reported honestly rather than
              invented.
            </p>
          )}
        </>
      )}
    </Panel>
  );
}

export function SkillPassport({ capability }) {
  const passport = capability?.passport;

  return (
    <Panel title="Why this skill exists">
      {!passport ? (
        <Empty>No acquired capability selected.</Empty>
      ) : (
        <ol className="text-[11px] space-y-2">
          <Step label="NEED">{passport.need}</Step>
          <Step label="RESEARCH">
            {passport.research?.grounded
              ? `${passport.research.source_count} sources`
              : "ungrounded — no sources (grounding quota-blocked)"}
          </Step>
          <Step label="PROPOSAL">{passport.candidate?.description}</Step>
          <Step label="TESTS">
            {passport.tests?.passed ? "passed in sandbox" : "not passed"}
          </Step>
          <Step label="APPROVAL">
            {capability.approved_by
              ? `${capability.approved_by} · ${capability.installed_at?.slice(0, 19)}`
              : "not approved"}
          </Step>
          <Step label="VERSION">{capability.version ?? "—"}</Step>
        </ol>
      )}
    </Panel>
  );
}

function Step({ label, children }) {
  return (
    <li>
      <span className="text-cyan tracking-wider">{label}</span>
      <p className="text-muted mt-0.5">{children || "—"}</p>
    </li>
  );
}

export function AuditFeed({ events }) {
  return (
    <Panel title="Evolution Events">
      {!events?.length ? (
        <Empty>No capability has been acquired yet.</Empty>
      ) : (
        <ul className="space-y-3 max-h-56 overflow-y-auto scroll-thin pr-1">
          {events.map((event, index) => (
            <motion.li
              key={event.event_id || index}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: Math.min(index * 0.05, 0.3) }}
              className="border-l-2 border-cyan/40 pl-3"
            >
              <p className="text-xs text-white">{event.change}</p>
              <p className="text-[10px] text-muted mt-0.5">{event.after}</p>
              <p className="text-[10px] text-muted">
                approved by {event.approver || "—"} ·{" "}
                {(event.research_citations?.length ?? 0)} citations
              </p>
            </motion.li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export function MonitorPanel({ monitors }) {
  return (
    <Panel title="Background Monitors">
      {!monitors?.length ? (
        <Empty>No monitors scheduled.</Empty>
      ) : (
        <ul className="space-y-2 text-[11px]">
          {monitors.map((m) => (
            <li key={m.monitor_id} className="flex justify-between">
              <span className="truncate mr-2">{m.name}</span>
              <span
                className={m.state === "ACTIVE" ? "text-ok" : "text-muted"}
              >
                {m.state} · {m.run_count ?? 0} runs
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export function TrustBoundary({ sandbox }) {
  const clean = sandbox?.verdict === "ZERO_CREDENTIALS";

  return (
    <Panel title="Trust Boundary">
      <p className={`text-sm ${clean ? "text-ok" : "text-danger"}`}>
        {sandbox?.verdict || "UNKNOWN"}
      </p>
      <p className="text-[11px] text-muted mt-1">
        aion-sandbox holds {sandbox?.credentials_found ?? "?"} credentials ·
        no IAM roles · unreachable from the public internet
      </p>
    </Panel>
  );
}

export function KillSwitch({ active, onToggle, busy }) {
  return (
    <Panel title="Kill Switch" tone={active ? "danger" : "edge"}>
      <button
        disabled={busy}
        onClick={() => onToggle(!active)}
        className={`w-full py-2 rounded text-xs tracking-wider border disabled:opacity-40 ${
          active
            ? "bg-danger/20 text-danger border-danger/50"
            : "bg-transparent text-muted border-edge hover:border-danger/50 hover:text-danger"
        }`}
      >
        {active ? "ACTIVE — RELEASE" : "STOP EVERYTHING"}
      </button>
      {active && (
        <p className="text-[10px] text-danger mt-2">
          All execution halted, including scheduled background work.
        </p>
      )}
    </Panel>
  );
}
