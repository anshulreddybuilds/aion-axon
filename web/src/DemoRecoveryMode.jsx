import { useEffect, useRef, useState } from "react";
import { Panel, Empty } from "./panels.jsx";
import { deriveStages, StageRow } from "./missionStages.jsx";
import {
  DEMO_FIXTURE_LABEL, DEMO_RECORD, DEMO_STEPS, TOTAL_DEMO_STEPS, visibleSteps,
} from "./demoRecoveryFixture.js";

/**
 * Demo Recovery Mode — a deterministic, zero-network walkthrough of
 * AION's real failure -> diagnosis -> retry -> success story.
 *
 * DEMO FIXTURE. This component makes NO API calls (grep this file: no
 * import of api.js, no fetch). Every stage row for Attempt 1 / Attempt 2
 * is rendered by the SAME deriveStages()/StageRow the real Mission
 * Theater uses against a real terminal record — reused unmodified
 * against the fixture data in demoRecoveryFixture.js, so what a judge
 * sees here is visually identical to a real recovered mission. Only the
 * data source differs, and every screen says so unmistakably.
 */

const STEP_INTERVAL_MS = 1800;

function DemoBadge() {
  return (
    <div className="border-2 border-warn/50 rounded-lg px-3 py-2 bg-warn/5 flex items-center gap-2">
      <span className="text-warn text-[13px]">⚠</span>
      <p className="text-[10px] tracking-[0.1em] text-warn">{DEMO_FIXTURE_LABEL}</p>
    </div>
  );
}

function NarrativeStep({ step }) {
  return (
    <div className="border border-edge rounded px-3 py-2">
      <p className="text-[11px] text-white/90 tracking-[0.08em]">{step.title}</p>
      <p className="text-[10px] text-muted mt-1">{step.body}</p>
    </div>
  );
}

function DemoApprovalPanel({ onDecide, decision }) {
  return (
    <div className="border-2 border-warn/50 rounded-lg p-4 bg-warn/5">
      <p className="text-[11px] tracking-[0.14em] text-warn">⏸ HUMAN APPROVAL REQUIRED (DEMO)</p>
      <p className="text-[12px] text-white/90 mt-2">
        Capability: <span className="text-cyan">{DEMO_RECORD.candidate.name}</span>
      </p>
      <div className="mt-3 space-y-1.5 text-[10px] text-muted">
        <p>Risk <span className="text-white/80">LOW</span></p>
        <p>Sandbox: <span className="text-ok">PASSED</span> (after retry)
          {"  ·  "}Evaluator: <span className="text-white/80">
            {DEMO_RECORD.evaluation.status} ({DEMO_RECORD.evaluation.score})
          </span>
        </p>
      </div>

      {!decision ? (
        <div className="flex gap-2 mt-4">
          <button
            onClick={() => onDecide(false)}
            className="flex-1 text-[11px] tracking-[0.12em] py-2 rounded border border-danger/50 text-danger hover:bg-danger/10"
          >
            REJECT (DEMO)
          </button>
          <button
            onClick={() => onDecide(true)}
            className="flex-1 text-[11px] tracking-[0.12em] py-2 rounded border border-ok/50 text-ok hover:bg-ok/10"
          >
            APPROVE (DEMO)
          </button>
        </div>
      ) : (
        <p className="mt-4 text-[11px] text-muted">
          {decision === "approved"
            ? "✓ Demo approval recorded locally. Nothing was installed and no production record was created."
            : "Demo rejection recorded locally. Nothing was installed."}
        </p>
      )}
      <p className="text-[9px] text-warn/80 mt-3 pt-2 border-t border-warn/30">
        DEMO FIXTURE — NO REAL APPROVAL. This click updates local UI state only.
      </p>
    </div>
  );
}

export default function DemoRecoveryMode() {
  const [running, setRunning] = useState(false);
  const [revealed, setRevealed] = useState(0);
  const [decision, setDecision] = useState(null);
  const timerRef = useRef(null);

  useEffect(() => () => clearTimeout(timerRef.current), []);

  const advance = (next) => {
    setRevealed(next);
    if (next < TOTAL_DEMO_STEPS) {
      timerRef.current = setTimeout(() => advance(next + 1), STEP_INTERVAL_MS);
    } else {
      setRunning(false);
    }
  };

  const run = () => {
    clearTimeout(timerRef.current);
    setDecision(null);
    setRunning(true);
    advance(1);
  };

  const reset = () => {
    clearTimeout(timerRef.current);
    setRunning(false);
    setRevealed(0);
    setDecision(null);
  };

  const steps = visibleSteps(revealed);
  const derivedStages = deriveStages(DEMO_RECORD);
  const stageFor = (attemptIndex) => derivedStages.find((s) => s.key === `attempt-${attemptIndex + 1}`);

  return (
    <div className="space-y-4">
      <DemoBadge />

      <div className="border border-edge rounded-lg p-4">
        <p className="text-[11px] text-cyan tracking-[0.14em] mb-1">DEMO RECOVERY MODE</p>
        <p className="text-[11px] text-muted leading-relaxed mb-3">
          A deterministic, reproducible walkthrough of AION's failure → diagnosis → retry → success
          story — the same story a real <code>allow_retry=True</code> mission tells, replayed here so
          it doesn't require a live owner-authorized production run every time it's wanted. No network
          call is made anywhere in this component.
        </p>
        <div className="flex gap-2">
          <button
            onClick={run}
            disabled={running}
            className="text-[11px] tracking-[0.12em] px-4 py-2 rounded border border-cyan/50 text-cyan hover:bg-cyan/10 disabled:opacity-40"
          >
            {running ? "RUNNING…" : "▶ RUN RECOVERY DEMO"}
          </button>
          <button
            onClick={reset}
            disabled={revealed === 0 && !running}
            className="text-[11px] tracking-[0.12em] px-3 py-2 rounded border border-edge text-muted hover:border-cyan/40 hover:text-cyan disabled:opacity-40"
          >
            ↺ RESET
          </button>
        </div>
      </div>

      {steps.length === 0 && <Empty>Click RUN RECOVERY DEMO to start the sequence.</Empty>}

      <div className="space-y-2">
        {steps.map((step) => {
          if (step.kind === "narrative") return <NarrativeStep key={step.key} step={step} />;
          if (step.kind === "stage") {
            const s = stageFor(step.attemptIndex);
            return s ? (
              <StageRow key={step.key} label={`${step.title} — ${s.label}`} tone={s.tone} detail={s.detail} />
            ) : null;
          }
          if (step.kind === "approval") {
            return <DemoApprovalPanel key={step.key} onDecide={(ok) => setDecision(ok ? "approved" : "rejected")} decision={decision} />;
          }
          return null;
        })}
      </div>

      {decision && (
        <Panel title="Demo Evidence Summary">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[10px]">
            <span className="text-muted">Need</span><span className="text-white/80">{DEMO_RECORD.need}</span>
            <span className="text-muted">Capability</span><span className="text-white/80">{DEMO_RECORD.candidate.name}</span>
            <span className="text-muted">Attempts made</span><span className="text-white/80">{DEMO_RECORD.attempts.length}</span>
            <span className="text-muted">Attempt 1</span><span className="text-danger">SANDBOX_FAILED</span>
            <span className="text-muted">Attempt 2</span><span className="text-ok">SANDBOX_PASSED</span>
            <span className="text-muted">Evaluator</span><span className="text-white/80">{DEMO_RECORD.evaluation.reason_code}</span>
            <span className="text-muted">Demo decision</span>
            <span className={decision === "approved" ? "text-ok" : "text-danger"}>{decision.toUpperCase()} (DEMO ONLY)</span>
          </div>
          <p className="text-[9px] text-warn/80 mt-3 pt-2 border-t border-edge">
            {DEMO_FIXTURE_LABEL} — no Firestore write, ledger event, or Cloud Run call occurred.
          </p>
        </Panel>
      )}
    </div>
  );
}
