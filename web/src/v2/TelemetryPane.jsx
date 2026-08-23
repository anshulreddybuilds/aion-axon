import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight, Clock, ShieldAlert, Zap } from "lucide-react";
import { buildLogLines, buildTrace, humanMs } from "./trace.js";
import { Card, Dot, MicroLabel, Metric, Pill } from "./Shell2.jsx";

/**
 * Right pane: reasoning trace, state inspector, autonomy ledger, log feed.
 *
 * The design brief asked for a "thinking drawer" streaming step-by-step
 * reasoning. Nothing in this system records a model's chain-of-thought, so
 * rendering an inner monologue would mean writing fiction into the one
 * surface whose entire job is to be checkable.
 *
 * What IS real is the pipeline trace with measured per-stage cost, and
 * that is what this renders. See trace.js for exactly which fields are
 * measured and which are deliberately absent.
 */

const TABS = [
  { id: "reasoning", label: "Pipeline trace" },
  { id: "state", label: "State inspector" },
  { id: "ledger", label: "Autonomy ledger" },
];

const TAG_TONE = {
  OK: "text-emerald-300",
  REFUSED: "text-red-300",
  BLOCKED: "text-red-300",
  DEGRADED: "text-amber-300",
};

function TraceStep({ step, index, open, onToggle }) {
  const tone =
    step.tone === "warn" ? "warn" : step.tone === "danger" ? "danger" : "ok";

  return (
    <div className="border border-white/[0.06] rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-white/[0.02] transition-colors text-left"
      >
        <motion.span
          animate={{ rotate: open ? 90 : 0 }}
          transition={{ duration: 0.15 }}
          className="text-zinc-600 shrink-0"
        >
          <ChevronRight size={13} />
        </motion.span>

        <span className="text-[9px] tracking-wider uppercase font-semibold text-zinc-600 tabular-nums shrink-0">
          {String(index + 1).padStart(2, "0")}
        </span>

        <Dot tone={tone} />

        <span className="text-[12px] font-medium tracking-tight flex-1 min-w-0 truncate">
          {step.label}
        </span>

        {step.ms != null ? (
          <span className="flex items-center gap-1 text-[10px] text-zinc-400 tabular-nums shrink-0">
            <Clock size={10} />
            {humanMs(step.ms)}
          </span>
        ) : (
          <span className="text-[9px] uppercase tracking-wider text-zinc-600 shrink-0">
            not timed
          </span>
        )}
      </button>

      {/* Opacity only, no height animation.
          `animate={{ height: "auto" }}` mounted the panel with a resolved
          height of 0 — the element was added to the DOM (child count went
          1 -> 2) and stayed invisible, so the accordion looked completely
          dead while actually working. Animating a property that can fail
          to resolve is not worth it for a drawer; the panel now simply
          renders when open. */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            <div className="px-3 pb-3 pl-[52px]">
              <p className="text-[10.5px] text-zinc-400 leading-relaxed">
                {step.note}
              </p>
              {step.stat ? (
                <p className="text-[10px] text-electric mt-1.5 tabular-nums font-medium">
                  {step.stat}
                </p>
              ) : (
                <p className="text-[10px] text-zinc-600 mt-1.5">
                  no measurement recorded — shown as absent rather than zero
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ReasoningTab({ data }) {
  const [open, setOpen] = useState({ 0: true });
  const steps = buildTrace({
    telemetry: data?.telemetry,
    evolution: data?.evolution,
    sandbox: data?.sandbox,
  });

  const measured = data?.telemetry?.model_calls;

  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap gap-2 mb-3.5">
        <Pill tone="electric">
          <Zap size={10} />
          {measured?.count ?? "—"} model calls
        </Pill>
        <Pill tone="neutral">
          {measured?.total_tokens?.toLocaleString() ?? "—"} tokens
        </Pill>
        {measured?.unmeasured ? (
          <Pill tone="warn">{measured.unmeasured} unmeasured</Pill>
        ) : null}
      </div>

      {steps.map((step, i) => (
        <TraceStep
          key={step.key}
          step={step}
          index={i}
          open={!!open[i]}
          onToggle={() => setOpen((o) => ({ ...o, [i]: !o[i] }))}
        />
      ))}

      <p className="text-[9px] text-zinc-600 leading-relaxed pt-1">
        Timings are averages measured from the model's own usage metadata, not
        estimates. This is the pipeline's real cost per stage — it is not a
        transcript of model reasoning, because nothing in this system records
        one.
      </p>
    </div>
  );
}

function StateTab({ data, stages }) {
  const rows = [
    ["kill switch", data?.root?.kill_switch_active ? "ACTIVE" : "released"],
    ["capabilities", `${data?.capabilities?.implemented ?? "—"} / ${data?.capabilities?.total ?? "—"}`],
    ["approval queue", `${data?.pending?.pending?.length ?? 0} waiting`],
    ["sandbox verdict", data?.sandbox?.verdict ?? "—"],
    ["evolution events", data?.evolution?.count ?? "—"],
    ["tool executions", data?.telemetry?.tool_executions?.count ?? "—"],
    ["exec p50", humanMs(data?.telemetry?.tool_executions?.p50_ms) ?? "—"],
    ["exec max", humanMs(data?.telemetry?.tool_executions?.max_ms) ?? "—"],
  ];

  return (
    <div className="space-y-1">
      {rows.map(([k, v]) => (
        <div
          key={k}
          className="flex items-center justify-between py-2 border-b border-white/[0.04] last:border-0"
        >
          <span className="text-[10px] tracking-wider uppercase font-semibold text-zinc-500">
            {k}
          </span>
          <span className="text-[11.5px] font-medium tabular-nums tracking-tight">
            {v}
          </span>
        </div>
      ))}
    </div>
  );
}

function LedgerTab({ data }) {
  const tracked = data?.autonomy?.capabilities || [];
  const threshold = data?.autonomy?.supervision_threshold ?? 40;

  if (!tracked.length) {
    return (
      <p className="text-[11px] text-zinc-500 italic">
        Nothing tracked yet — an empty ledger means nothing has been acquired,
        not that the panel failed.
      </p>
    );
  }

  return (
    <div className="space-y-2.5">
      {tracked.map((c) => {
        const pct = c.autonomy ?? c.autonomy_score ?? null;
        const below = pct != null && pct < threshold;

        return (
          <div
            key={c.name}
            className="border border-white/[0.06] rounded-xl px-3 py-2.5"
          >
            <div className="flex items-center gap-2">
              <Dot tone={below ? "warn" : "ok"} />
              <span className="text-[11.5px] font-medium tracking-tight flex-1 min-w-0 truncate">
                {c.name}
              </span>
              <span className="text-[11px] tabular-nums font-semibold">
                {pct != null ? `${pct}%` : "—"}
              </span>
            </div>

            {pct != null && (
              <div className="mt-2 h-1 rounded-full bg-white/[0.06] overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.min(100, Math.max(0, pct))}%`,
                    background: below ? "#fbbf24" : "#38bdf8",
                  }}
                />
              </div>
            )}

            {below && (
              <p className="flex items-center gap-1.5 text-[9.5px] text-amber-300 mt-2">
                <ShieldAlert size={10} />
                below the {threshold}% supervision threshold — a human is asked
                again
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function TelemetryPane({ data, stages }) {
  const [tab, setTab] = useState("reasoning");
  const logs = buildLogLines(data?.evolution);

  return (
    <div className="space-y-4">
      <Card className="p-5">
        <div className="flex items-center gap-1 mb-4 p-1 rounded-xl bg-obsidian/50 border border-white/[0.06]">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`flex-1 rounded-lg px-2 py-1.5 text-[10px] tracking-wider uppercase font-semibold transition-colors ${
                tab === t.id
                  ? "bg-cobalt/15 text-electric"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === "reasoning" && <ReasoningTab data={data} />}
        {tab === "state" && <StateTab data={data} stages={stages} />}
        {tab === "ledger" && <LedgerTab data={data} />}
      </Card>

      <Card className="p-5">
        <MicroLabel className="mb-3">Evidence feed</MicroLabel>

        {logs.length === 0 ? (
          <p className="text-[11px] text-zinc-500 italic">
            No evolution events recorded.
          </p>
        ) : (
          <div className="font-mono text-[10.5px] space-y-1.5 max-h-[280px] overflow-y-auto scroll-thin">
            {logs.map((line, i) => (
              <div key={i} className="flex gap-2.5">
                <span
                  className={`shrink-0 font-semibold ${
                    TAG_TONE[line.tag] || "text-zinc-400"
                  }`}
                >
                  [{line.tag}]
                </span>
                <span className="text-zinc-400 break-all">{line.text}</span>
              </div>
            ))}
          </div>
        )}

        <p className="text-[9px] text-zinc-600 mt-3.5 leading-relaxed">
          Tags come from recorded outcomes — a real sandbox exit code, a real
          citation count. DEGRADED on research means zero citations, which is
          the honest state while Search grounding is tier-blocked.
        </p>
      </Card>
    </div>
  );
}
