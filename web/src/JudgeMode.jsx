import { useEffect, useState } from "react";
import { api, hasOwnerToken } from "./api.js";
import { Panel, Empty } from "./panels.jsx";

/**
 * Judge Mode — a Proof Center over the real /beastmode/* API.
 *
 * Every card below calls a real endpoint on mount and renders exactly
 * what came back. There is no seeded/demo state: an endpoint that fails
 * renders NOT AVAILABLE with the real error, never a fabricated result.
 * This mirrors the same honesty rule the rest of the Holo-Deck already
 * follows in api.js/loadAll() — a dead panel says so instead of lying.
 */

const STATUS_COLOR = {
  VERIFIED: "text-ok border-ok/40",
  PASSED: "text-ok border-ok/40",
  MISMATCH: "text-danger border-danger/40",
  NO_SEAL: "text-muted border-edge",
  NOT_AVAILABLE: "text-muted border-edge",
  ERROR: "text-danger border-danger/40",
};

function StatusPill({ status }) {
  const cls = STATUS_COLOR[status] || "text-muted border-edge";
  return (
    <span className={`text-[9px] tracking-[0.14em] px-2 py-0.5 rounded border ${cls}`}>
      {status}
    </span>
  );
}

/** One card = one endpoint. Fetches once, offers a manual re-run. */
function ProofCard({ title, fetcher, render, needsOwner = false }) {
  const [state, setState] = useState({ loading: true, data: null, error: null });

  const run = () => {
    setState({ loading: true, data: null, error: null });
    fetcher()
      .then((data) => setState({ loading: false, data, error: null }))
      .catch((err) => setState({ loading: false, data: null, error: err.message }));
  };

  useEffect(run, []); // eslint-disable-line react-hooks/exhaustive-deps

  const status = state.error ? "ERROR" : state.loading ? null : "LIVE";

  return (
    <Panel
      title={title}
      right={
        <div className="flex items-center gap-2">
          {status && !state.loading && (
            <span
              className={`text-[9px] tracking-[0.14em] px-2 py-0.5 rounded border ${
                state.error ? "text-danger border-danger/40" : "text-cyan border-cyan/40"
              }`}
            >
              {state.error ? "NOT AVAILABLE" : "LIVE"}
            </span>
          )}
          <button
            onClick={run}
            disabled={needsOwner && !hasOwnerToken()}
            className="text-[9px] tracking-[0.12em] px-2 py-1 rounded border border-edge text-muted hover:border-cyan/40 hover:text-cyan disabled:opacity-40 disabled:cursor-not-allowed"
            title={needsOwner && !hasOwnerToken() ? "Owner token required" : "Re-run against the live API"}
          >
            ↻ RE-RUN
          </button>
        </div>
      }
    >
      {state.loading && <Empty>Calling the live endpoint…</Empty>}
      {state.error && (
        <p className="text-xs text-danger">
          {state.error}
          {needsOwner && !hasOwnerToken() && (
            <span className="block text-muted mt-1">
              This action is owner-gated — paste the owner token above and re-run.
            </span>
          )}
        </p>
      )}
      {!state.loading && !state.error && render(state.data)}
    </Panel>
  );
}

function RedTeamCard() {
  return (
    <ProofCard
      title="Red Team — live adversarial screen"
      fetcher={api.redTeam}
      render={(d) => (
        <div className="space-y-2">
          <div className="flex items-baseline gap-3 text-[11px]">
            <span className="text-cyan text-lg leading-none">{d.contained_at_layer_tested}</span>
            <span className="text-muted">/ {d.total} attack vectors contained</span>
            {d.genuine_misses > 0 && (
              <span className="text-danger ml-auto">{d.genuine_misses} genuine miss(es)</span>
            )}
          </div>
          <div className="max-h-56 overflow-y-auto space-y-1.5 pr-1">
            {(d.results || []).map((r, i) => (
              <div
                key={i}
                className={`text-[10px] border rounded px-2 py-1.5 ${
                  r.blocked
                    ? "border-ok/30"
                    : r.expected_miss_here
                    ? "border-edge"
                    : "border-danger/40"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-white/90 truncate">{r.vector}</span>
                  <span className={r.blocked ? "text-ok" : r.expected_miss_here ? "text-muted" : "text-danger"}>
                    {r.blocked ? "BLOCKED" : r.expected_miss_here ? "EXPECTED MISS" : "NOT BLOCKED"}
                  </span>
                </div>
                <p className="text-muted mt-0.5">{r.layer} · {r.ms}ms</p>
              </div>
            ))}
          </div>
        </div>
      )}
    />
  );
}

function LedgerCard() {
  return (
    <ProofCard
      title="Autonomy Ledger — hash-chain verification"
      fetcher={api.ledgerVerify}
      render={(d) => (
        <div className="space-y-2 text-[11px]">
          <StatusPill status={d.status} />
          <p className="text-muted">{d.detail}</p>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px] text-muted mt-2">
            <span>Events (current)</span><span className="text-white/80">{d.event_count}</span>
            {"sealed_event_count" in d && (
              <>
                <span>Events (sealed)</span><span className="text-white/80">{d.sealed_event_count}</span>
              </>
            )}
            <span>Current hash</span>
            <span className="text-white/80 truncate" title={d.current_final_hash}>
              {(d.current_final_hash || "").slice(0, 16)}…
            </span>
            {d.sealed_final_hash && (
              <>
                <span>Sealed hash</span>
                <span className="text-white/80 truncate" title={d.sealed_final_hash}>
                  {d.sealed_final_hash.slice(0, 16)}…
                </span>
              </>
            )}
          </div>
        </div>
      )}
    />
  );
}

function LedgerSealCard() {
  return (
    <ProofCard
      title="Ledger Seal — owner-gated, writes a new baseline"
      fetcher={api.ledgerSeal}
      needsOwner
      render={(d) => (
        <div className="text-[11px] space-y-1">
          <p className="text-ok">New seal written over the current live ledger.</p>
          <p className="text-muted">{d.event_count} events sealed.</p>
          <p className="text-muted truncate" title={d.final_hash}>hash: {(d.final_hash || "").slice(0, 24)}…</p>
        </div>
      )}
    />
  );
}

function QuarantineCard() {
  return (
    <ProofCard
      title="Quarantine — derived from real audit events"
      fetcher={api.quarantine}
      render={(d) =>
        d.count === 0 ? (
          <Empty>No capability is currently quarantined.</Empty>
        ) : (
          <div className="space-y-1.5">
            {d.quarantined.map((q) => (
              <div key={q.capability} className="text-[10px] border border-danger/40 rounded px-2 py-1.5">
                <div className="flex justify-between">
                  <span className="text-white/90">{q.capability}</span>
                  <span className="text-danger">{q.status}</span>
                </div>
                <p className="text-muted mt-0.5">{q.stage} · {q.reason || "no reason recorded"}</p>
              </div>
            ))}
          </div>
        )
      }
    />
  );
}

function LineageCard({ capability }) {
  return (
    <ProofCard
      title={`Lineage — ${capability}`}
      fetcher={() => api.lineage(capability)}
      render={(d) =>
        d.history.length === 0 ? (
          <Empty>No acquisition history recorded for this capability.</Empty>
        ) : (
          <div className="space-y-1.5">
            <p className="text-[10px] text-muted">
              current version <span className="text-cyan">v{d.current_version}</span>
              {d.currently_installed ? "  ·  installed" : "  ·  not installed"}
            </p>
            {d.history.map((s) => (
              <div key={s.event_id} className="text-[10px] border border-edge rounded px-2 py-1.5">
                <div className="flex justify-between">
                  <span className="text-white/90">v{s.version} — {s.kind}</span>
                  <span className="text-muted">{s.timestamp}</span>
                </div>
                <p className="text-muted mt-0.5">{s.change}</p>
              </div>
            ))}
          </div>
        )
      }
    />
  );
}

function MemoryHistoryCard({ capability }) {
  return (
    <ProofCard
      title={`Capability Memory — ${capability}`}
      fetcher={() => api.memoryHistory(capability)}
      render={(d) =>
        !d.known ? (
          <Empty>Memory has no record of this capability name.</Empty>
        ) : (
          <div className="text-[10px] space-y-2">
            <div className="grid grid-cols-2 gap-x-3 gap-y-1">
              <span className="text-muted">State</span><span className="text-white/90">{d.state}</span>
              <span className="text-muted">Implemented</span>
              <span className={d.implemented ? "text-ok" : "text-muted"}>{String(d.implemented)}</span>
              <span className="text-muted">Attempts</span><span className="text-white/90">{d.attempts}</span>
            </div>
            {d.history.length > 0 && (
              <div className="space-y-1 pt-1 border-t border-edge">
                {d.history.map((h, i) => (
                  <p key={i} className="text-muted">
                    {h.timestamp} — {h.stage} → <span className="text-white/80">{h.status}</span>
                    {h.reason ? `: ${h.reason}` : ""}
                  </p>
                ))}
              </div>
            )}
          </div>
        )
      }
    />
  );
}

function ContractCard({ capability }) {
  return (
    <ProofCard
      title={`Capability Contract — ${capability}`}
      fetcher={() => api.contract(capability)}
      render={(d) =>
        d.status !== "OK" ? (
          <Empty>Not yet acquired — no passport to build a contract from.</Empty>
        ) : (
          <div className="text-[10px] space-y-2">
            <div className="grid grid-cols-2 gap-x-3 gap-y-1">
              <span className="text-muted">Risk</span><span className="text-white/90">{d.contract.risk}</span>
              <span className="text-muted">Network</span><span className="text-white/90">{d.contract.permissions.network}</span>
              <span className="text-muted">Credentials</span><span className="text-white/90">{d.contract.permissions.credentials}</span>
              <span className="text-muted">Filesystem</span><span className="text-white/90">{d.contract.permissions.filesystem}</span>
              <span className="text-muted">AST safe</span>
              <span className={d.contract.static_screen.safe ? "text-ok" : "text-danger"}>
                {String(d.contract.static_screen.safe)}
              </span>
            </div>
            {d.contract.static_screen.findings.length > 0 && (
              <div>
                <p className="text-muted mb-1">Findings</p>
                {d.contract.static_screen.findings.map((f, i) => (
                  <p key={i} className="text-danger">{f}</p>
                ))}
              </div>
            )}
          </div>
        )
      }
    />
  );
}

/** Human Approval 2.0 — "why does this need a human?", live, per request. */
function ApprovalExplainCard({ requestId }) {
  return (
    <ProofCard
      title={`Why does this need a human? — ${requestId}`}
      fetcher={() => api.explainApproval(requestId)}
      render={(d) =>
        d.status === "NOT_FOUND" ? (
          <Empty>No approval request with this ID.</Empty>
        ) : (
          <div className="text-[10px] space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-white/90">{d.capability}</span>
              <StatusPill status={d.why_human.risk_score.tier} />
              <span className="text-muted ml-auto">score {d.why_human.risk_score.score}/100</span>
            </div>
            <div>
              {d.why_human.risk_score.factors.map((f, i) => (
                <p key={i} className="text-muted">· {f}</p>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 pt-1 border-t border-edge">
              <span className="text-muted">Sandbox</span>
              <span className={d.why_human.sandbox_result.passed ? "text-ok" : "text-danger"}>
                {d.why_human.sandbox_result.passed ? "PASSED" : "FAILED"} (exit {d.why_human.sandbox_result.exit_code})
              </span>
              <span className="text-muted">Evaluator</span>
              <span className="text-white/80">
                {d.why_human.evaluator_result.status} — score {d.why_human.evaluator_result.score ?? "none"}
                {d.why_human.evaluator_result.reason_code && (
                  <span className="text-muted"> ({d.why_human.evaluator_result.reason_code})</span>
                )}
              </span>
              <span className="text-muted">Policy</span>
              <span className="text-white/80">{d.why_human.policy_id || "none matched"}</span>
            </div>
          </div>
        )
      }
    />
  );
}

function PlannerCard() {
  const [need, setNeed] = useState("");
  const [state, setState] = useState({ loading: false, data: null, error: null });

  const run = () => {
    if (!need.trim()) return;
    setState({ loading: true, data: null, error: null });
    api.plan(need.trim())
      .then((data) => setState({ loading: false, data, error: null }))
      .catch((err) => setState({ loading: false, data: null, error: err.message }));
  };

  return (
    <Panel
      title="Planner / Decision Trace"
      right={
        <span className="text-[9px] tracking-[0.14em] px-2 py-0.5 rounded border border-edge text-muted">
          POST /beastmode/plan
        </span>
      }
    >
      <div className="flex gap-2 mb-3">
        <input
          value={need}
          onChange={(e) => setNeed(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
          placeholder="a capability need, e.g. 'detect year-over-year anomalies'"
          className="flex-1 bg-transparent border border-edge rounded px-2 py-1.5 text-[11px] text-white/90 outline-none focus:border-cyan/50"
        />
        <button
          onClick={run}
          disabled={state.loading || !need.trim()}
          className="text-[10px] tracking-[0.1em] px-3 py-1.5 rounded border border-cyan/50 text-cyan hover:bg-cyan/10 disabled:opacity-40"
        >
          {state.loading ? "…" : "PLAN"}
        </button>
      </div>

      {state.loading && <Empty>Consulting memory and building a plan…</Empty>}
      {state.error && <p className="text-xs text-danger">{state.error}</p>}
      {state.data && (
        <div className="text-[10px] space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-white/90">{state.data.decision}</span>
            {state.data.capability && <span className="text-cyan">{state.data.capability}</span>}
          </div>
          <p className="text-muted">{state.data.reason}</p>
          {state.data.strategy && (
            <p className="text-muted">
              strategy: <span className="text-white/80">{state.data.strategy}</span>
              {state.data.planned_attempts ? ` (${state.data.planned_attempts} attempts)` : ""}
            </p>
          )}
          {state.data.memory?.matches?.length > 0 && (
            <div className="pt-1 border-t border-edge space-y-1">
              <p className="text-white/70">evidence</p>
              {state.data.memory.matches.map((m) => (
                <p key={m.name} className="text-muted">
                  {m.name} — match {Math.round(m.score * 100)}%, {m.implemented ? "installed" : m.state}
                </p>
              ))}
            </div>
          )}
          {state.data.required_checks?.length > 0 && (
            <p className="text-muted">
              required: <span className="text-white/80">{state.data.required_checks.join(", ")}</span>
            </p>
          )}
          <p className="text-muted pt-1 border-t border-edge">{state.data.authorization_note}</p>
        </div>
      )}
    </Panel>
  );
}

export default function JudgeMode({ pending, acquiredNames }) {
  const [inspectCapability, setInspectCapability] = useState(acquiredNames?.[0] || "");
  const [explainRequestId, setExplainRequestId] = useState(pending?.[0]?.request_id || "");

  return (
    <div className="space-y-4">
      <div className="border border-cyan/30 rounded-lg p-4 bg-cyan/5">
        <p className="text-[11px] text-cyan tracking-[0.14em]">JUDGE MODE — PROOF CENTER</p>
        <p className="text-[11px] text-muted mt-1 leading-relaxed">
          Every card on this page is a live call to the same governed API the rest of the
          Holo-Deck uses — nothing here is seeded or replayed. A card that fails says{" "}
          <span className="text-danger">NOT AVAILABLE</span> with the real error rather than
          showing a fabricated result. Re-run any card to prove it isn't cached.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <RedTeamCard />
        <LedgerCard />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <QuarantineCard />
        <LedgerSealCard />
      </div>

      <PlannerCard />

      <div className="border border-edge rounded-lg p-3 flex flex-wrap items-center gap-3">
        <label className="text-[10px] text-muted tracking-[0.1em]">
          INSPECT CAPABILITY
        </label>
        <input
          value={inspectCapability}
          onChange={(e) => setInspectCapability(e.target.value)}
          placeholder="capability name"
          className="flex-1 min-w-[140px] bg-transparent border border-edge rounded px-2 py-1 text-[11px] text-white/90 outline-none focus:border-cyan/50"
        />
        <label className="text-[10px] text-muted tracking-[0.1em]">
          APPROVAL REQUEST ID
        </label>
        <input
          value={explainRequestId}
          onChange={(e) => setExplainRequestId(e.target.value)}
          placeholder="request id"
          className="flex-1 min-w-[140px] bg-transparent border border-edge rounded px-2 py-1 text-[11px] text-white/90 outline-none focus:border-cyan/50"
        />
      </div>

      {inspectCapability && (
        <div className="grid gap-4 lg:grid-cols-2">
          <ContractCard capability={inspectCapability} />
          <LineageCard capability={inspectCapability} />
          <MemoryHistoryCard capability={inspectCapability} />
        </div>
      )}

      {explainRequestId && <ApprovalExplainCard requestId={explainRequestId} />}
    </div>
  );
}
