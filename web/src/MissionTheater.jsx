import { useEffect, useState } from "react";
import { api, hasOwnerToken } from "./api.js";
import { Panel, Empty } from "./panels.jsx";

/**
 * Mission Theater — one real acquisition, watched stage by stage.
 *
 * POST /synapse/propose runs the actual governed pipeline synchronously
 * (research -> generate -> screen -> sandbox -> evaluate -> guardian ->
 * approval) and blocks until it reaches a terminal stage or stops at
 * AWAITING_APPROVAL. There is no separate streaming/polling channel for
 * an in-flight acquisition — this component is honest about that: the
 * "RUNNING" state below corresponds to one real in-flight HTTP request,
 * not a simulated multi-step animation, and every stage rendered after
 * it returns is reconstructed from the real terminal record, never
 * invented. See app/synapse/engine.py for the exact fields.
 */

const STAGE_ORDER = [
  "GUARDIAN_PRESCREEN",
  "RESEARCH",
  "GENERATE",
  "SAFETY_SCREEN",
  "SANDBOX_TEST",
  "EVALUATE",
  "GUARDIAN_SCREEN",
  "AWAITING_APPROVAL",
];

const TONE = {
  PASSED: "border-ok/40 text-ok",
  BLOCKED: "border-danger/40 text-danger",
  REFUSED: "border-danger/40 text-danger",
  REJECTED: "border-danger/40 text-danger",
  FAILED: "border-danger/40 text-danger",
  WAITING: "border-warn/40 text-warn",
  DONE: "border-ok/40 text-ok",
  SKIPPED: "border-edge text-muted",
};

function StageRow({ label, tone, detail, children }) {
  const cls = TONE[tone] || "border-edge text-muted";
  return (
    <div className={`border rounded px-3 py-2 ${cls.split(" ")[0]}`}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-white/90 tracking-[0.08em]">{label}</span>
        <span className={`text-[9px] tracking-[0.14em] ${cls.split(" ")[1]}`}>{tone}</span>
      </div>
      {detail && <p className="text-[10px] text-muted mt-1">{detail}</p>}
      {children}
    </div>
  );
}

/** Reconstructs the stage-by-stage picture from ONE real terminal record.
 *  Never fabricates a stage the record doesn't evidence. */
function deriveStages(record) {
  const stages = [];

  if (record.guardian?.decision === "REFUSE" && record.stage === "GUARDIAN_PRESCREEN") {
    stages.push({
      key: "GUARDIAN_PRESCREEN", label: "Guardian pre-screen", tone: "REFUSED",
      detail: `${record.guardian.policy_id || ""} — ${record.reason}`,
    });
    return stages; // pipeline never left the doorway
  }

  if (record.research?.status) {
    stages.push({
      key: "RESEARCH", label: "Research",
      tone: record.research.grounded ? "PASSED" : "WAITING",
      detail: `${record.research.source_count} source(s)${
        record.research.degraded_reason ? ` — degraded: ${record.research.degraded_reason}` : ""
      }`,
    });
  }

  if (record.attempts?.length) {
    record.attempts.forEach((a) => {
      const tone = a.outcome === "SANDBOX_PASSED" ? "PASSED"
        : a.outcome === "SANDBOX_UNREACHABLE" ? "BLOCKED"
        : "FAILED";
      stages.push({
        key: `attempt-${a.attempt}`,
        label: `Generate + sandbox — attempt ${a.attempt}${a.attempt > 1 ? " (retry, fed real stderr)" : ""}`,
        tone,
        detail: a.candidate ? `${a.candidate} — ${a.outcome}${a.detail ? `: ${String(a.detail).slice(0, 160)}` : ""}` : a.outcome,
      });
    });
  } else if (record.candidate) {
    stages.push({
      key: "GENERATE", label: "Generate",
      tone: "PASSED",
      detail: record.candidate.name,
    });
  }

  if (record.safety?.safe !== undefined) {
    stages.push({
      key: "SAFETY_SCREEN", label: "AST static screen",
      tone: record.safety.safe ? "PASSED" : "BLOCKED",
      detail: record.safety.findings?.length ? record.safety.findings.join("; ") : "no findings",
    });
  }

  if (record.tests?.status && !record.attempts?.length) {
    stages.push({
      key: "SANDBOX_TEST", label: "Sandbox",
      tone: record.tests.passed ? "PASSED" : record.tests.status === "UNREACHABLE" ? "BLOCKED" : "FAILED",
      detail: `exit ${record.tests.exit_code ?? "?"}`,
    });
  }

  if (record.evaluation?.status) {
    stages.push({
      key: "EVALUATE", label: "Independent evaluation",
      tone: record.evaluation.status === "SCORED"
        ? (record.evaluation.verdict === "PASS" ? "PASSED" : "REJECTED")
        : "WAITING",
      detail: `${record.evaluation.status}${record.evaluation.score != null ? ` — score ${record.evaluation.score}` : ""}${
        record.evaluation.reason_code ? ` (${record.evaluation.reason_code})` : ""
      }`,
    });
  }

  if (record.guardian?.decision && record.stage !== "GUARDIAN_PRESCREEN") {
    stages.push({
      key: "GUARDIAN_SCREEN", label: "Guardian screen",
      tone: record.guardian.decision === "REFUSE" ? "REFUSED"
        : record.guardian.decision === "APPROVAL_REQUIRED" ? "WAITING" : "PASSED",
      detail: `${record.guardian.policy_id || "no policy matched"}${record.guardian.reason ? ` — ${record.guardian.reason}` : ""}`,
    });
  }

  if (record.status === "AWAITING_APPROVAL") {
    stages.push({
      key: "AWAITING_APPROVAL", label: "Human approval", tone: "WAITING",
      detail: `request ${record.approval_request_id}`,
    });
  } else if (["REJECTED", "REFUSED", "BLOCKED", "FAILED"].includes(record.status)) {
    stages.push({ key: "TERMINAL", label: `Mission stopped — ${record.status}`, tone: record.status, detail: record.reason });
  }

  return stages;
}

function ApprovalGate({ record, onDecided }) {
  const [explain, setExplain] = useState(null);
  const [explainError, setExplainError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    api.explainApproval(record.approval_request_id)
      .then(setExplain)
      .catch((e) => setExplainError(e.message));
  }, [record.approval_request_id]);

  const decide = async (approved) => {
    setBusy(true);
    try {
      await api.decide(record.approval_request_id, approved);
      let installResult = null;
      if (approved) {
        installResult = await api.install(record.candidate.name);
      }
      setResult({ approved, installResult });
      onDecided?.(approved);
    } catch (err) {
      setResult({ approved, error: err.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border-2 border-warn/50 rounded-lg p-4 bg-warn/5">
      <p className="text-[11px] tracking-[0.14em] text-warn">⏸ HUMAN APPROVAL REQUIRED</p>
      <p className="text-[12px] text-white/90 mt-2">
        Capability: <span className="text-cyan">{record.candidate?.name}</span>
      </p>

      {explainError && <p className="text-xs text-danger mt-2">{explainError}</p>}
      {explain?.why_human && (
        <div className="mt-3 space-y-1.5 text-[10px]">
          <p className="text-muted">
            Risk <span className="text-white/80">{explain.why_human.risk_score.tier}</span> ({explain.why_human.risk_score.score}/100)
          </p>
          {explain.why_human.risk_score.factors.map((f, i) => (
            <p key={i} className="text-muted">· {f}</p>
          ))}
          <p className="text-muted pt-1 border-t border-edge mt-2">
            Sandbox: <span className={explain.why_human.sandbox_result.passed ? "text-ok" : "text-danger"}>
              {explain.why_human.sandbox_result.passed ? "PASSED" : "FAILED"}
            </span>
            {"  ·  "}Evaluator: <span className="text-white/80">
              {explain.why_human.evaluator_result.status}
              {explain.why_human.evaluator_result.score != null ? ` (${explain.why_human.evaluator_result.score})` : ""}
            </span>
          </p>
        </div>
      )}

      {!result ? (
        <div className="flex gap-2 mt-4">
          <button
            onClick={() => decide(false)}
            disabled={busy || !hasOwnerToken()}
            className="flex-1 text-[11px] tracking-[0.12em] py-2 rounded border border-danger/50 text-danger hover:bg-danger/10 disabled:opacity-40"
          >
            REJECT
          </button>
          <button
            onClick={() => decide(true)}
            disabled={busy || !hasOwnerToken()}
            className="flex-1 text-[11px] tracking-[0.12em] py-2 rounded border border-ok/50 text-ok hover:bg-ok/10 disabled:opacity-40"
          >
            APPROVE
          </button>
        </div>
      ) : (
        <div className="mt-4 text-[11px]">
          {result.error ? (
            <p className="text-danger">{result.error}</p>
          ) : result.approved ? (
            <div className="space-y-1">
              <p className="text-ok">✓ HUMAN APPROVED — install requested</p>
              <p className="text-muted">
                {result.installResult?.status === "INSTALLED"
                  ? "INSTALLED → ACTIVE. Mission's original need is now satisfiable."
                  : `Install: ${result.installResult?.status || result.installResult?.reason || "unknown"}`}
              </p>
            </div>
          ) : (
            <p className="text-danger">Rejected. Capability was not installed.</p>
          )}
        </div>
      )}
      {!hasOwnerToken() && !result && (
        <p className="text-[9px] text-muted mt-2">Owner token required to approve or reject — paste it above.</p>
      )}
    </div>
  );
}

const MEMORY_TONE = {
  REUSE_EXISTING_CAPABILITY: "border-ok/40 text-ok",
  DO_NOT_REUSE: "border-danger/40 text-danger",
  ESCALATE: "border-warn/40 text-warn",
  ACQUIRE_NEW: "border-edge text-muted",
};

function MemoryCheckPanel({ result, checking, error }) {
  if (checking) return <Empty>Searching prior capability history…</Empty>;
  if (error) return <p className="text-xs text-danger">{error}</p>;
  if (!result) return null;

  const cls = MEMORY_TONE[result.recommendation] || "border-edge text-muted";

  return (
    <div className={`border rounded-lg p-3 space-y-2 ${cls.split(" ")[0]}`}>
      <div className="flex items-center justify-between">
        <p className="text-[10px] tracking-[0.14em] text-white/80">MEMORY CHECK</p>
        <span className={`text-[9px] tracking-[0.12em] ${cls.split(" ")[1]}`}>
          {result.recommendation} · {result.confidence}
        </span>
      </div>
      <p className="text-[11px] text-white/90">{result.reason}</p>
      {result.matches.length > 0 && (
        <div className="space-y-1 pt-1 border-t border-edge">
          {result.matches.map((m) => (
            <div key={m.name} className="flex items-center justify-between text-[10px]">
              <span className="text-white/80">{m.name}</span>
              <span className="text-muted">
                match {Math.round(m.score * 100)}% · {m.implemented ? "installed" : m.state}
              </span>
            </div>
          ))}
        </div>
      )}
      {result.history.length > 0 && (
        <details className="text-[10px] text-muted">
          <summary className="cursor-pointer text-white/70">
            {result.history.length} prior attempt(s)
          </summary>
          <div className="mt-1 space-y-1">
            {result.history.map((h, i) => (
              <p key={i}>{h.timestamp} — {h.stage} → {h.status}{h.reason ? `: ${h.reason}` : ""}</p>
            ))}
          </div>
        </details>
      )}
      <p className="text-[9px] text-muted pt-1 border-t border-edge">{result.security_note}</p>
    </div>
  );
}

export default function MissionTheater() {
  const [need, setNeed] = useState("");
  const [allowRetry, setAllowRetry] = useState(true);
  const [running, setRunning] = useState(false);
  const [record, setRecord] = useState(null);
  const [error, setError] = useState(null);
  const [decided, setDecided] = useState(false);

  const [memory, setMemory] = useState(null);
  const [memoryChecking, setMemoryChecking] = useState(false);
  const [memoryError, setMemoryError] = useState(null);

  const checkMemory = async () => {
    if (!need.trim()) return;
    setMemoryChecking(true);
    setMemoryError(null);
    setMemory(null);
    try {
      const result = await api.memoryQuery(need.trim());
      setMemory(result);
    } catch (err) {
      setMemoryError(err.message);
    } finally {
      setMemoryChecking(false);
    }
  };

  const run = async () => {
    if (!need.trim()) return;
    setRunning(true);
    setError(null);
    setRecord(null);
    setDecided(false);
    try {
      const result = await api.proposeCapability(need.trim(), { allowRetry });
      setRecord(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  };

  const stages = record ? deriveStages(record) : [];

  return (
    <div className="space-y-4">
      <div className="border border-cyan/30 rounded-lg p-4 bg-cyan/5">
        <p className="text-[11px] text-cyan tracking-[0.14em]">MISSION THEATER — ONE REAL ACQUISITION</p>
        <p className="text-[11px] text-muted mt-1 leading-relaxed">
          This calls the real governed pipeline (<code>POST /synapse/propose</code>) with whatever
          you type below. It is a live network call against production — typically 10–30s,
          since it really invokes Gemini and the sandbox. There is no pre-recorded state:
          if you type a need that already has a satisfying capability, expect it to say so
          honestly rather than manufacture a new gap.
        </p>
      </div>

      <div className="border border-edge rounded-lg p-3 space-y-2">
        <label className="text-[10px] text-muted tracking-[0.1em]">CAPABILITY NEED</label>
        <textarea
          value={need}
          onChange={(e) => setNeed(e.target.value)}
          placeholder='e.g. "convert a list of prices from USD to INR"'
          rows={2}
          className="w-full bg-transparent border border-edge rounded px-2 py-1.5 text-[12px] text-white/90 outline-none focus:border-cyan/50 resize-none"
        />
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 text-[10px] text-muted">
            <input type="checkbox" checked={allowRetry} onChange={(e) => setAllowRetry(e.target.checked)} />
            allow one bounded retry-with-feedback on sandbox failure
          </label>
          <div className="flex gap-2">
            <button
              onClick={checkMemory}
              disabled={memoryChecking || !need.trim()}
              className="text-[11px] tracking-[0.12em] px-3 py-2 rounded border border-edge text-muted hover:border-cyan/40 hover:text-cyan disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {memoryChecking ? "CHECKING…" : "🔎 CHECK MEMORY"}
            </button>
            <button
              onClick={run}
              disabled={running || !need.trim() || !hasOwnerToken()}
              className="text-[11px] tracking-[0.12em] px-4 py-2 rounded border border-cyan/50 text-cyan hover:bg-cyan/10 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {running ? "RUNNING — LIVE CALL IN FLIGHT…" : "▶ RUN MISSION"}
            </button>
          </div>
        </div>
        {!hasOwnerToken() && (
          <p className="text-[9px] text-muted">Owner token required to run a mission — paste it above. Memory check is public.</p>
        )}
      </div>

      <MemoryCheckPanel result={memory} checking={memoryChecking} error={memoryError} />

      {error && <p className="text-xs text-danger">{error}</p>}

      {record && (
        <Panel title="Live governance spine — real terminal record">
          <div className="space-y-2">
            {stages.length === 0 && <Empty>No stages evidenced by this record.</Empty>}
            {stages.map((s) => (
              <StageRow key={s.key} label={s.label} tone={s.tone} detail={s.detail} />
            ))}
          </div>
        </Panel>
      )}

      {record?.status === "AWAITING_APPROVAL" && !decided && (
        <ApprovalGate record={record} onDecided={() => setDecided(true)} />
      )}

      {record && (
        <Panel title="Proof of Action">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[10px]">
            <span className="text-muted">Need</span><span className="text-white/80">{record.need}</span>
            <span className="text-muted">Final stage</span><span className="text-white/80">{record.stage}</span>
            <span className="text-muted">Status</span><span className="text-white/80">{record.status}</span>
            <span className="text-muted">Capability</span><span className="text-white/80">{record.candidate?.name || "—"}</span>
            <span className="text-muted">Attempts made</span><span className="text-white/80">{record.attempts?.length || 1}</span>
            <span className="text-muted">Approval request</span><span className="text-white/80">{record.approval_request_id || "—"}</span>
            {record.reason && (
              <>
                <span className="text-muted">Reason</span><span className="text-white/80">{record.reason}</span>
              </>
            )}
          </div>
        </Panel>
      )}
    </div>
  );
}
