import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Box,
  CheckCircle2,
  CircleDot,
  Clock,
  Database,
  GitBranch,
  Lock,
  Mic,
  Network,
  Plus,
  RefreshCw,
  Shield,
  ShieldAlert,
  Terminal,
  Trash2,
  Unlock,
  Volume2,
  VolumeX,
  XCircle,
  Zap,
} from "lucide-react";
import { api, CORE, hasOwnerToken, loadAll, setOwnerToken } from "../api.js";
import { compileGraphToPlan, planToGraph, topoOrder } from "../graphCompiler.js";
import {
  nodeStatuses,
  runOutcomeText,
  toneForMissionStatus,
} from "../graphExecutionState.js";
import { actionsFromMissionSteps, describeStage } from "../livePipeline.js";
import {
  speak,
  speechSynthesisSupported,
  stopSpeaking,
} from "../speechOutput.js";
import { extractAnswer, extractStepAnswer, prettyValue } from "../v4/artifact.js";
import { useSpeechInput } from "../useSpeechInput.js";
import "./axonV5.css";

const NODE_W = 218;
const NODE_H = 118;

const TONE_COLOR = {
  ok: "#34d399",
  danger: "#fb7185",
  warn: "#fbbf24",
  idle: "#64748b",
  acquiring: "#22d3ee",
};

const STATE_STYLE = {
  idle: {
    color: "#64748b",
    bg: "rgba(100,116,139,0.08)",
    border: "rgba(148,163,184,0.14)",
  },
  active: {
    color: "#22d3ee",
    bg: "rgba(34,211,238,0.1)",
    border: "rgba(34,211,238,0.34)",
  },
  complete: {
    color: "#34d399",
    bg: "rgba(52,211,153,0.1)",
    border: "rgba(52,211,153,0.28)",
  },
  waiting: {
    color: "#fbbf24",
    bg: "rgba(251,191,36,0.1)",
    border: "rgba(251,191,36,0.32)",
  },
  stopped: {
    color: "#fb7185",
    bg: "rgba(251,113,133,0.1)",
    border: "rgba(251,113,133,0.3)",
  },
  recorded: {
    color: "#a78bfa",
    bg: "rgba(167,139,250,0.1)",
    border: "rgba(167,139,250,0.26)",
  },
};

function emptyNode(id, x, y) {
  return {
    id,
    description: "",
    tool: null,
    args: [""],
    risk: "LOW",
    kind: "READ_ANALYZE",
    x,
    y,
  };
}

function cx(...parts) {
  return parts.filter(Boolean).join(" ");
}

function Panel({ className = "", children }) {
  return <section className={cx("axon-panel", className)}>{children}</section>;
}

function IconButton({ children, className = "", ...props }) {
  return (
    <button {...props} className={cx("axon-icon-button", className)}>
      {children}
    </button>
  );
}

function ActionButton({
  children,
  tone = "primary",
  className = "",
  ...props
}) {
  return (
    <button
      {...props}
      className={cx("axon-action", `axon-action--${tone}`, className)}
    >
      {children}
    </button>
  );
}

function MicroLabel({ children, className = "" }) {
  return <p className={cx("axon-label", className)}>{children}</p>;
}

function StatusDot({ tone = "idle" }) {
  return (
    <span
      className="axon-dot"
      style={{ background: TONE_COLOR[tone] || TONE_COLOR.idle }}
    />
  );
}

function Field({ label, value }) {
  return (
    <div className="axon-field">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function stateForMission(status) {
  if (!status) return "idle";
  if (status === "COMPLETED") return "complete";
  if (status === "AWAITING_APPROVAL" || status === "APPROVAL_REQUIRED") {
    return "waiting";
  }
  if (status === "BLOCKED") return "waiting";
  return "stopped";
}

function isImageUrl(value) {
  return /^https?:\/\/.+\.(png|jpe?g|gif|webp|avif)(\?.*)?$/i.test(
    String(value || "")
  );
}

function urlsIn(value) {
  const text = String(value || "");
  return [...text.matchAll(/https?:\/\/[^\s)"']+/g)].map((m) =>
    m[0].replace(/[.,;]+$/, "")
  );
}

function ValueView({ value }) {
  const text = prettyValue(value);
  const images = urlsIn(text).filter(isImageUrl).slice(0, 4);

  return (
    <div className="axon-value">
      <span>{text}</span>
      {images.length > 0 && (
        <div className="axon-image-strip">
          {images.map((url) => (
            <a
              key={url}
              href={url}
              target="_blank"
              rel="noreferrer"
              className="axon-image-link"
            >
              <img src={url} alt="Mission result" loading="lazy" />
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

function ResultCard({ title, answer }) {
  if (!answer) return null;
  return (
    <div className="axon-result-card">
      <MicroLabel>{title}</MicroLabel>
      <div className="axon-result-grid">
        {answer.fields.map(([k, v]) => (
          <div key={k} className="axon-result-row">
            <span>{k}</span>
            <ValueView value={v} />
          </div>
        ))}
      </div>
    </div>
  );
}

function MissionTimeline({
  missionResult,
  running,
  planning,
  directApproval,
  acquisition,
  answer,
  lastCompiled,
}) {
  const steps = [
    {
      label: "Plan",
      detail: lastCompiled
        ? `${lastCompiled.plan.steps.length} step${
            lastCompiled.plan.steps.length === 1 ? "" : "s"
          }`
        : "No plan yet",
      state: planning ? "active" : lastCompiled ? "complete" : "idle",
    },
    {
      label: "Govern",
      detail: directApproval
        ? "Human decision required"
        : missionResult
        ? "Policy state returned"
        : "Waiting for mission",
      state: directApproval ? "waiting" : missionResult ? "complete" : "idle",
    },
    {
      label: "Capability",
      detail:
        acquisition?.record?.status ||
        (acquisition
          ? "Acquiring"
          : missionResult?.blocked_on
          ? "Gap found"
          : "Registry only"),
      state: acquisition
        ? "active"
        : missionResult?.blocked_on
        ? "waiting"
        : missionResult
        ? "recorded"
        : "idle",
    },
    {
      label: "Execute",
      detail: running ? "Running real engine" : missionResult?.status || "Not started",
      state: running ? "active" : stateForMission(missionResult?.status),
    },
    {
      label: "Verify",
      detail: answer
        ? "Final result captured"
        : missionResult
        ? "No final artifact yet"
        : "Waiting",
      state: answer ? "complete" : missionResult ? "recorded" : "idle",
    },
  ];

  return (
    <div className="axon-timeline">
      {steps.map((step, index) => {
        const style = STATE_STYLE[step.state] || STATE_STYLE.idle;
        return (
          <div
            key={step.label}
            className="axon-timeline-step"
            style={{ borderColor: style.border, background: style.bg }}
          >
            <span className="axon-timeline-index" style={{ color: style.color }}>
              {String(index + 1).padStart(2, "0")}
            </span>
            <div>
              <strong>{step.label}</strong>
              <small>{step.detail}</small>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function HealthStack({ snapshot, loading, error, onRefresh }) {
  const pending = snapshot?.pending?.pending?.length ?? 0;
  const capabilityRows = snapshot?.capabilities?.capabilities || [];
  const implemented =
    snapshot?.capabilities?.implemented ??
    capabilityRows.filter((c) => c.implemented).length;
  const total = snapshot?.capabilities?.total ?? capabilityRows.length;
  const rows = [
    {
      label: "Core API",
      value: snapshot?.online ? "online" : "not verified",
      tone: snapshot?.online ? "ok" : "warn",
      icon: Activity,
    },
    {
      label: "Kill switch",
      value: snapshot?.root?.kill_switch_active ? "active" : "released",
      tone: snapshot?.root?.kill_switch_active ? "danger" : "ok",
      icon: Lock,
    },
    {
      label: "Sandbox",
      value: snapshot?.sandbox?.verdict || "unknown",
      tone: snapshot?.sandbox?.verdict ? "ok" : "warn",
      icon: Shield,
    },
    {
      label: "Approvals",
      value: `${pending} waiting`,
      tone: pending ? "warn" : "ok",
      icon: ShieldAlert,
    },
    {
      label: "Capabilities",
      value: `${implemented}/${total}`,
      tone: total ? "ok" : "warn",
      icon: Database,
    },
  ];

  return (
    <Panel className="axon-health">
      <div className="axon-panel-head">
        <div>
          <MicroLabel>Live system</MicroLabel>
          <h2>Security state</h2>
        </div>
        <IconButton
          onClick={onRefresh}
          title="Refresh live state"
          aria-label="Refresh live state"
        >
          <RefreshCw size={15} className={loading ? "axon-spin" : ""} />
        </IconButton>
      </div>
      <div className="axon-health-list">
        {rows.map((row) => {
          const Icon = row.icon;
          return (
            <div key={row.label} className="axon-health-row">
              <Icon size={15} />
              <span>{row.label}</span>
              <strong className={`tone-${row.tone}`}>{row.value}</strong>
            </div>
          );
        })}
      </div>
      {error && <p className="axon-error-text">{error}</p>}
      <p className="axon-footnote">Backend: {CORE}</p>
    </Panel>
  );
}

function CapabilityLedger({ snapshot, capabilities }) {
  const tracked = snapshot?.autonomy?.capabilities || [];
  const threshold = snapshot?.autonomy?.supervision_threshold ?? 40;
  const source = tracked.length
    ? tracked
    : capabilities
        .slice(0, 8)
        .map((c) => ({ name: c.name, implemented: c.implemented }));

  return (
    <Panel>
      <div className="axon-panel-head">
        <div>
          <MicroLabel>Capability and autonomy</MicroLabel>
          <h2>Registry ledger</h2>
        </div>
        <Box size={16} />
      </div>
      <div className="axon-ledger-list">
        {source.length === 0 ? (
          <p className="axon-empty">No capability data has been returned yet.</p>
        ) : (
          source.map((cap) => {
            const raw = cap.effective_autonomy_pct ?? cap.autonomy_pct ?? null;
            const pct = raw == null ? null : Number(raw);
            const validPct = Number.isFinite(pct) ? pct : null;
            const below = validPct != null && validPct < threshold;
            return (
              <div key={cap.name} className="axon-ledger-row">
                <div>
                  <strong>{cap.name}</strong>
                  <small>
                    {cap.implemented === false
                      ? "not installed"
                      : below
                      ? "supervision threshold"
                      : "registered"}
                  </small>
                </div>
                <span className={below ? "tone-warn" : "tone-ok"}>
                  {validPct == null ? "--" : `${validPct}%`}
                </span>
                {validPct != null && (
                  <div className="axon-ledger-bar">
                    <i
                      style={{
                        width: `${Math.min(100, Math.max(0, validPct))}%`,
                        background: below ? "#fbbf24" : "#34d399",
                      }}
                    />
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </Panel>
  );
}

function EvolutionFeed({ snapshot, acquisition, missionResult }) {
  const events = snapshot?.evolution?.events || [];
  const missionActions = actionsFromMissionSteps(missionResult?.step_results || []);
  const feed = acquisition?.actions?.length
    ? acquisition.actions
    : missionActions.length
    ? missionActions
    : events.slice(0, 6).map((e) => ({
        label: e.event || e.type || "evolution event",
        detail: e.capability || e.message || e.status || "recorded",
        tone: "ok",
      }));

  return (
    <Panel>
      <div className="axon-panel-head">
        <div>
          <MicroLabel>Execution and evidence</MicroLabel>
          <h2>Live trace</h2>
        </div>
        <Terminal size={16} />
      </div>
      <div className="axon-feed">
        {feed.length === 0 ? (
          <p className="axon-empty">
            No execution events recorded in this session yet.
          </p>
        ) : (
          feed.map((item, i) => (
            <div key={`${item.label}-${i}`} className="axon-feed-item">
              <StatusDot tone={item.tone || "ok"} />
              <div>
                <strong>{item.label}</strong>
                <small>{item.detail}</small>
              </div>
            </div>
          ))
        )}
      </div>
    </Panel>
  );
}

function CoreGraph({
  nodes,
  edges,
  statuses,
  selectedId,
  connectFrom,
  canvasRef,
  center,
  onNodePointerDown,
  onNodeClick,
  onConnect,
  onDelete,
  isRunning,
  planning,
}) {
  return (
    <Panel className="axon-graph-panel">
      <div className="axon-graph-header">
        <div>
          <MicroLabel>AXON live graph</MicroLabel>
          <h1>Mission nervous system</h1>
        </div>
        <div className="axon-graph-badges">
          <span>{nodes.length} nodes</span>
          <span>{edges.length} links</span>
        </div>
      </div>
      <div ref={canvasRef} className="axon-canvas scroll-thin">
        <div className={cx("axon-core-orbit", isRunning && "axon-core-orbit--active")}>
          <span />
          <strong>AXON</strong>
          <small>{planning ? "planning" : isRunning ? "running" : "ready"}</small>
        </div>
        <svg className="axon-edge-layer" width="100%" height="100%">
          <defs>
            <marker
              id="axon-arrow"
              markerWidth="9"
              markerHeight="9"
              refX="8"
              refY="4.5"
              orient="auto"
            >
              <path d="M0,0 L9,4.5 L0,9 Z" fill="rgba(45,212,191,0.78)" />
            </marker>
          </defs>
          {edges.map((e) => {
            const a = nodes.find((n) => n.id === e.from);
            const b = nodes.find((n) => n.id === e.to);
            if (!a || !b) return null;
            const p1 = center(a);
            const p2 = center(b);
            return (
              <line
                key={`${e.from}->${e.to}`}
                x1={p1.x}
                y1={p1.y}
                x2={p2.x}
                y2={p2.y}
                markerEnd="url(#axon-arrow)"
              />
            );
          })}
        </svg>
        {nodes.length === 0 && (
          <div className="axon-empty-canvas">
            <Network size={28} />
            <strong>Describe a mission or add nodes manually.</strong>
            <span>The first real plan becomes an editable graph here.</span>
          </div>
        )}
        {(isRunning || planning) && (
          <div className="axon-run-banner">
            {planning
              ? "Planning through the governed mission API"
              : "Running through the real AXON engine"}
          </div>
        )}
        {nodes.map((node) => {
          const st = statuses.get(node.id);
          const tone = st?.tone || "idle";
          const selected = selectedId === node.id;
          const connecting = connectFrom === node.id;
          return (
            <div
              key={node.id}
              onPointerDown={(e) => onNodePointerDown(e, node)}
              onClick={() => onNodeClick(node.id)}
              className={cx(
                "axon-node",
                selected && "axon-node--selected",
                connecting && "axon-node--connecting"
              )}
              style={{
                left: node.x,
                top: node.y,
                width: NODE_W,
                minHeight: NODE_H,
                "--node-tone": TONE_COLOR[tone] || TONE_COLOR.idle,
              }}
            >
              <div className="axon-node-head">
                <StatusDot tone={tone} />
                <span>{node.id}</span>
                <em>{node.risk}</em>
              </div>
              <p>{node.description || "No description"}</p>
              <code>{node.tool || "AION acquisition path"}</code>
              {st && <small>{st.label}</small>}
              <div className="axon-node-actions">
                <button
                  type="button"
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={(e) => {
                    e.stopPropagation();
                    onConnect(node.id);
                  }}
                >
                  connect
                </button>
                <button
                  type="button"
                  aria-label={`Delete ${node.id}`}
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(node.id);
                  }}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function NodeEditor({
  selected,
  capabilities,
  argHint,
  nodeAnswer,
  updateNode,
  close,
}) {
  if (!selected) {
    return (
      <Panel>
        <MicroLabel>Node inspector</MicroLabel>
        <p className="axon-empty">
          Select a graph node to edit its capability, risk, arguments, and
          node-specific result.
        </p>
      </Panel>
    );
  }

  return (
    <Panel>
      <div className="axon-panel-head">
        <div>
          <MicroLabel>Node inspector</MicroLabel>
          <h2>Node {selected.id}</h2>
        </div>
        <IconButton title="Close inspector" aria-label="Close inspector" onClick={close}>
          <XCircle size={15} />
        </IconButton>
      </div>
      <div className="axon-form">
        <label>Description</label>
        <textarea
          value={selected.description}
          onChange={(e) => updateNode(selected.id, { description: e.target.value })}
          rows={3}
        />
        <label>Capability</label>
        <select
          value={selected.tool || ""}
          onChange={(e) => updateNode(selected.id, { tool: e.target.value || null })}
        >
          <option value="">Let AION acquire</option>
          {capabilities.map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
              {c.implemented ? "" : " (not installed)"}
            </option>
          ))}
        </select>
        <div className="axon-form-grid">
          <div>
            <label>Risk</label>
            <select
              value={selected.risk}
              onChange={(e) => updateNode(selected.id, { risk: e.target.value })}
            >
              <option value="LOW">LOW</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="HIGH">HIGH</option>
            </select>
          </div>
          <div>
            <label>Kind</label>
            <select
              value={selected.kind}
              onChange={(e) => updateNode(selected.id, { kind: e.target.value })}
            >
              <option value="READ_ANALYZE">READ_ANALYZE</option>
              <option value="EXTERNAL_EFFECT">EXTERNAL_EFFECT</option>
            </select>
          </div>
        </div>
        <label>Args</label>
        {argHint && <p className="axon-hint">{selected.tool} needs: {argHint}</p>}
        <textarea
          value={(selected.args || []).join("\n")}
          onChange={(e) => updateNode(selected.id, { args: e.target.value.split("\n") })}
          rows={4}
        />
      </div>
      <ResultCard title={`Node result: ${nodeAnswer?.tool || ""}`} answer={nodeAnswer} />
    </Panel>
  );
}

function ApprovalPanel({
  directApproval,
  acquisition,
  deciding,
  decideDirect,
  decideAcquisition,
}) {
  if (directApproval) {
    return (
      <Panel className="axon-gate axon-gate--warn">
        <MicroLabel>Governance gate</MicroLabel>
        <h2>Human approval required</h2>
        <p>AXON stopped at a real approval request before continuing this mission.</p>
        <div className="axon-button-row">
          <ActionButton tone="success" onClick={() => decideDirect(true)} disabled={deciding}>
            Approve
          </ActionButton>
          <ActionButton tone="danger" onClick={() => decideDirect(false)} disabled={deciding}>
            Reject
          </ActionButton>
        </div>
      </Panel>
    );
  }

  if (acquisition?.record?.status === "AWAITING_APPROVAL") {
    return (
      <Panel className="axon-gate axon-gate--active">
        <MicroLabel>Capability gate</MicroLabel>
        <h2>Install proposed capability</h2>
        <p>
          <strong>{acquisition.record.candidate?.name}</strong> is waiting for
          approval before install and resume.
        </p>
        <div className="axon-button-row">
          <ActionButton
            tone="success"
            onClick={() => decideAcquisition(true)}
            disabled={deciding}
          >
            Approve install
          </ActionButton>
          <ActionButton
            tone="danger"
            onClick={() => decideAcquisition(false)}
            disabled={deciding}
          >
            Reject
          </ActionButton>
        </div>
      </Panel>
    );
  }

  return null;
}

export default function AppV5() {
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [goal, setGoal] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [connectFrom, setConnectFrom] = useState(null);
  const [capabilities, setCapabilities] = useState([]);
  const [argHint, setArgHint] = useState(null);
  const [systemSnapshot, setSystemSnapshot] = useState(null);
  const [systemLoading, setSystemLoading] = useState(false);
  const [systemError, setSystemError] = useState(null);

  const [compileError, setCompileError] = useState(null);
  const [running, setRunning] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [missionResult, setMissionResult] = useState(null);
  const [answer, setAnswer] = useState(null);
  const [lastCompiled, setLastCompiled] = useState(null);

  const [directApproval, setDirectApproval] = useState(null);
  const [acquisition, setAcquisition] = useState(null);
  const [deciding, setDeciding] = useState(false);
  const [rejected, setRejected] = useState(false);

  const [unlocked, setUnlocked] = useState(hasOwnerToken());
  const [tokenInput, setTokenInput] = useState("");
  const [speakEnabled, setSpeakEnabled] = useState(false);

  const idCounter = useRef(1);
  const dragRef = useRef(null);
  const canvasRef = useRef(null);

  const speech = useSpeechInput({
    onText: (t) => setGoal(t),
    onError: (message) => setCompileError(message),
  });

  const refreshSystem = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setSystemLoading(true);
    setSystemError(null);
    try {
      const snapshot = await loadAll();
      setSystemSnapshot(snapshot);
      setCapabilities(snapshot?.capabilities?.capabilities || []);
    } catch (err) {
      setSystemError(String(err.message || err));
    } finally {
      if (!silent) setSystemLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshSystem();
  }, [refreshSystem]);

  const announce = (result, opts) => {
    const text = runOutcomeText(result, opts);
    if (speakEnabled) speak(text);
    return text;
  };

  const addNode = () => {
    const id = `n${idCounter.current++}`;
    const x = 36 + (nodes.length % 3) * 252;
    const y = 54 + Math.floor(nodes.length / 3) * 154;
    setNodes((prev) => [...prev, emptyNode(id, x, y)]);
    setSelectedId(id);
  };

  const updateNode = (id, patch) => {
    setNodes((prev) => prev.map((n) => (n.id === id ? { ...n, ...patch } : n)));
  };

  const deleteNode = (id) => {
    setNodes((prev) => prev.filter((n) => n.id !== id));
    setEdges((prev) => prev.filter((e) => e.from !== id && e.to !== id));
    if (selectedId === id) setSelectedId(null);
    if (connectFrom === id) setConnectFrom(null);
  };

  const handleNodeClick = (id) => {
    if (connectFrom && connectFrom !== id) {
      setEdges((prev) =>
        prev.some((e) => e.from === connectFrom && e.to === id)
          ? prev
          : [...prev, { from: connectFrom, to: id }]
      );
      setConnectFrom(null);
      return;
    }
    if (connectFrom === id) {
      setConnectFrom(null);
      return;
    }
    setSelectedId(id);
  };

  const removeEdge = (from, to) => {
    setEdges((prev) => prev.filter((e) => !(e.from === from && e.to === to)));
  };

  const onNodePointerDown = (e, node) => {
    if (e.button !== 0 || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    dragRef.current = {
      id: node.id,
      offsetX: e.clientX - rect.left - node.x,
      offsetY: e.clientY - rect.top - node.y,
    };
  };

  useEffect(() => {
    const onMove = (e) => {
      const drag = dragRef.current;
      if (!drag || !canvasRef.current) return;
      const rect = canvasRef.current.getBoundingClientRect();
      const x = Math.max(0, e.clientX - rect.left - drag.offsetX);
      const y = Math.max(0, e.clientY - rect.top - drag.offsetY);
      updateNode(drag.id, { x, y });
    };
    const onUp = () => {
      dragRef.current = null;
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, []);

  const resetRunState = () => {
    stopSpeaking();
    setMissionResult(null);
    setAnswer(null);
    setDirectApproval(null);
    setAcquisition(null);
    setRejected(false);
  };

  const startAcquisition = async (missionId) => {
    setAcquisition({ missionId, actions: [], record: null });
    try {
      const acquired = await api.acquireForMissionStream(missionId, {
        onStage: (record) => {
          const { label, detail, tone } = describeStage(record);
          setAcquisition((prev) =>
            prev && prev.missionId === missionId
              ? {
                  ...prev,
                  actions: [...prev.actions, { label, detail, tone }],
                  record,
                }
              : prev
          );
        },
      });
      setAcquisition((prev) =>
        prev && prev.missionId === missionId ? { ...prev, record: acquired } : prev
      );
      refreshSystem({ silent: true });
    } catch (err) {
      setCompileError(String(err.message || err));
    }
  };

  const compileAndRun = async () => {
    if (!unlocked) {
      setCompileError(
        "Unlock with the owner token. Running a mission is a real governed write."
      );
      return;
    }

    const { order, error: orderError } = topoOrder(nodes, edges);
    const { plan, error } = compileGraphToPlan(nodes, edges, goal);

    if (error || orderError) {
      setCompileError(error || orderError);
      return;
    }

    setCompileError(null);
    resetRunState();
    setRunning(true);

    const stepNumberById = new Map(order.map((id, i) => [id, i + 1]));
    setLastCompiled({ stepNumberById, plan });

    try {
      const result = await api.missionFromGraph(plan);
      setMissionResult(result);
      setAnswer(extractAnswer(result));
      announce(result);
      refreshSystem({ silent: true });

      if (result.status === "BLOCKED") {
        startAcquisition(result.mission_id);
      } else if (result.status === "AWAITING_APPROVAL") {
        setDirectApproval({
          missionId: result.mission_id,
          approvalRequestId: result.approval_request_id,
        });
      }
    } catch (err) {
      setCompileError(String(err.message || err));
    } finally {
      setRunning(false);
    }
  };

  const planIt = async () => {
    const text = goal.trim();
    if (!text || planning) return;

    if (!unlocked) {
      setCompileError(
        "Unlock with the owner token. Planning runs a real governed mission."
      );
      return;
    }

    setPlanning(true);
    setCompileError(null);
    resetRunState();

    try {
      const result = await api.plannedMission(text);
      const built = planToGraph({
        goal: result.goal || text,
        steps: result.plan || [],
      });
      const laidOut = built.nodes.map((n, i) => ({
        ...n,
        x: 36 + (i % 3) * 252,
        y: 54 + Math.floor(i / 3) * 154,
      }));
      setNodes(laidOut);
      setEdges(built.edges);
      idCounter.current = laidOut.length + 1;

      const stepNumberById = new Map(
        laidOut.map((n) => [n.id, Number(n.id.slice(1))])
      );
      setLastCompiled({
        stepNumberById,
        plan: { goal: result.goal || text, steps: result.plan || [] },
      });
      setMissionResult(result);
      setAnswer(extractAnswer(result));
      announce(result);
      refreshSystem({ silent: true });

      if (result.status === "BLOCKED") {
        startAcquisition(result.mission_id);
      } else if (result.status === "AWAITING_APPROVAL") {
        setDirectApproval({
          missionId: result.mission_id,
          approvalRequestId: result.approval_request_id,
        });
      }
    } catch (err) {
      setCompileError(String(err.message || err));
    } finally {
      setPlanning(false);
    }
  };

  const decideDirect = async (approved) => {
    if (!directApproval || deciding) return;
    setDeciding(true);
    setRejected(!approved);
    try {
      await api.decide(directApproval.approvalRequestId, approved);
      const resumed = await api.resumePlanned(directApproval.missionId);
      setMissionResult(resumed);
      setAnswer(extractAnswer(resumed));
      announce(resumed, { rejected: !approved });
      refreshSystem({ silent: true });

      if (approved && resumed.status === "AWAITING_APPROVAL") {
        setDirectApproval({
          missionId: directApproval.missionId,
          approvalRequestId: resumed.approval_request_id,
        });
      } else {
        setDirectApproval(null);
        if (approved && resumed.status === "BLOCKED") {
          startAcquisition(directApproval.missionId);
        }
      }
    } catch (err) {
      setCompileError(String(err.message || err));
    } finally {
      setDeciding(false);
    }
  };

  const decideAcquisition = async (approved) => {
    const rec = acquisition?.record;
    if (!rec?.approval_request_id || deciding) return;
    setDeciding(true);
    try {
      await api.decide(rec.approval_request_id, approved);

      if (approved) {
        const installed = await api.install(rec.candidate?.name);
        if (
          installed?.status !== "INSTALLED" &&
          installed?.status !== "ALREADY_INSTALLED"
        ) {
          setCompileError(
            `Install did not complete: ${
              installed?.reason || installed?.error || installed?.status || "unknown"
            }`
          );
        }

        const resumedId =
          installed?.mission_resumed?.mission_id ||
          (typeof installed?.mission_resumed === "string"
            ? installed.mission_resumed
            : null);
        if (resumedId) {
          const resumed = await api.mission(resumedId);
          setMissionResult(resumed);
          setAnswer(extractAnswer(resumed));
          announce(resumed);
          refreshSystem({ silent: true });
          if (resumed.status === "BLOCKED") {
            setAcquisition(null);
            startAcquisition(resumedId);
            setDeciding(false);
            return;
          }
        }
      } else if (speakEnabled) {
        speak("Capability rejected. The mission remains blocked.");
      }
      setAcquisition(null);
      refreshSystem({ silent: true });
    } catch (err) {
      setCompileError(String(err.message || err));
    } finally {
      setDeciding(false);
    }
  };

  const statuses = lastCompiled
    ? nodeStatuses({
        nodes,
        stepNumberById: lastCompiled.stepNumberById,
        missionResult,
      })
    : new Map();

  if (acquisition && lastCompiled && missionResult?.blocked_on) {
    const blockedStep = missionResult.blocked_on.step;
    const blockedNodeId = [...lastCompiled.stepNumberById.entries()].find(
      ([, n]) => n === blockedStep
    )?.[0];
    if (blockedNodeId) {
      const stage = acquisition.record ? describeStage(acquisition.record) : null;
      statuses.set(blockedNodeId, {
        tone: "acquiring",
        label: stage?.label || "Acquiring a missing capability",
        detail: stage?.detail || "",
      });
    }
  }

  const selected = nodes.find((n) => n.id === selectedId) || null;
  const nodeAnswer = selected ? extractStepAnswer(missionResult, selected.id) : null;

  useEffect(() => {
    if (!selected?.tool) {
      setArgHint(null);
      return;
    }

    let cancelled = false;
    api
      .passport(selected.tool)
      .then((body) => {
        if (cancelled) return;
        const candidate = body?.passport?.candidate;
        const code = candidate?.code;
        const entrypoint = candidate?.entrypoint;
        if (!code || !entrypoint) {
          setArgHint(null);
          return;
        }
        const match = code.match(
          new RegExp(`def\\s+${entrypoint}\\s*\\(([^)]*)\\)`)
        );
        setArgHint(match ? match[1].trim() || "(no arguments)" : null);
      })
      .catch(() => {
        if (!cancelled) setArgHint(null);
      });

    return () => {
      cancelled = true;
    };
  }, [selected?.tool]);

  const isRunning = running || planning;
  const center = (n) => ({ x: n.x + NODE_W / 2, y: n.y + NODE_H / 2 });
  const missionTone = toneForMissionStatus(missionResult?.status);

  return (
    <div className="axon-v5-shell">
      <header className="axon-topbar">
        <div className="axon-brand">
          <CircleDot size={18} />
          <div>
            <strong>AION AXON</strong>
            <span>Live autonomous mission control</span>
          </div>
        </div>
        <div className="axon-topbar-center">
          <span
            className={cx(
              "axon-connection",
              systemSnapshot?.online ? "tone-ok" : "tone-warn"
            )}
          >
            {systemSnapshot?.online ? "core online" : "core not verified"}
          </span>
          <span>
            {missionResult?.mission_id
              ? `mission ${missionResult.mission_id.slice(0, 8)}`
              : "no active mission"}
          </span>
        </div>
        <div className="axon-topbar-actions">
          {!unlocked ? (
            <div className="axon-token-box">
              <input
                type="password"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="owner token"
                autoComplete="off"
              />
              <ActionButton
                onClick={() => {
                  if (!tokenInput.trim()) return;
                  setOwnerToken(tokenInput);
                  setTokenInput("");
                  setUnlocked(true);
                }}
              >
                <Unlock size={14} />
                Unlock
              </ActionButton>
            </div>
          ) : (
            <span className="axon-owner">
              <Unlock size={13} /> owner unlocked
            </span>
          )}
          {speechSynthesisSupported() && (
            <IconButton
              onClick={() => setSpeakEnabled((v) => !v)}
              title={speakEnabled ? "Mute voice output" : "Enable voice output"}
              aria-label={speakEnabled ? "Mute voice output" : "Enable voice output"}
            >
              {speakEnabled ? <Volume2 size={15} /> : <VolumeX size={15} />}
            </IconButton>
          )}
        </div>
      </header>

      <main className="axon-layout">
        <aside className="axon-sidebar axon-sidebar--left">
          <HealthStack
            snapshot={systemSnapshot}
            loading={systemLoading}
            error={systemError}
            onRefresh={() => refreshSystem()}
          />
          <CapabilityLedger snapshot={systemSnapshot} capabilities={capabilities} />
        </aside>

        <section className="axon-main-stage">
          <Panel className="axon-command-panel">
            <div className="axon-command-copy">
              <MicroLabel>Mission command</MicroLabel>
              <h1>Plan, govern, execute, verify.</h1>
            </div>
            <div className="axon-command-input">
              {speech.supported && (
                <IconButton
                  onClick={speech.toggle}
                  title="Speak a mission"
                  aria-label="Speak a mission"
                  className={speech.listening ? "axon-mic-live" : ""}
                >
                  <Mic size={16} />
                </IconButton>
              )}
              <textarea
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="Describe the mission. AXON will turn it into the real governed plan."
                rows={2}
              />
              <div className="axon-command-actions">
                <ActionButton onClick={planIt} disabled={planning || !goal.trim()}>
                  <GitBranch size={14} />
                  {planning ? "Planning" : "Plan it"}
                </ActionButton>
                <ActionButton tone="neutral" onClick={addNode}>
                  <Plus size={14} />
                  Node
                </ActionButton>
                <ActionButton
                  tone="success"
                  onClick={compileAndRun}
                  disabled={running || !nodes.length}
                >
                  <Zap size={14} />
                  {running ? "Running" : "Compile & Run"}
                </ActionButton>
              </div>
            </div>
          </Panel>

          {connectFrom && (
            <div className="axon-info-strip">
              Connecting from {connectFrom}. Select a target node to create the
              dependency.
            </div>
          )}
          {compileError && (
            <div className="axon-error-strip">
              <AlertTriangle size={15} />
              {compileError}
            </div>
          )}

          <MissionTimeline
            missionResult={missionResult}
            running={running}
            planning={planning}
            directApproval={directApproval}
            acquisition={acquisition}
            answer={answer}
            lastCompiled={lastCompiled}
          />

          <CoreGraph
            nodes={nodes}
            edges={edges}
            statuses={statuses}
            selectedId={selectedId}
            connectFrom={connectFrom}
            canvasRef={canvasRef}
            center={center}
            onNodePointerDown={onNodePointerDown}
            onNodeClick={handleNodeClick}
            onConnect={setConnectFrom}
            onDelete={deleteNode}
            isRunning={isRunning}
            planning={planning}
          />

          {edges.length > 0 && (
            <div className="axon-edge-list">
              {edges.map((e) => (
                <span key={`${e.from}->${e.to}`}>
                  {e.from} -&gt; {e.to}
                  <button
                    onClick={() => removeEdge(e.from, e.to)}
                    aria-label={`Remove ${e.from} to ${e.to}`}
                  >
                    x
                  </button>
                </span>
              ))}
            </div>
          )}
        </section>

        <aside className="axon-sidebar axon-sidebar--right">
          <Panel className="axon-mission-card">
            <MicroLabel>Mission state</MicroLabel>
            <div className="axon-mission-status">
              {missionResult?.status === "COMPLETED" ? (
                <CheckCircle2 size={18} />
              ) : missionResult?.status ? (
                <ShieldAlert size={18} />
              ) : (
                <Clock size={18} />
              )}
              <div>
                <strong className={`tone-${missionTone}`}>
                  {missionResult?.status || "IDLE"}
                </strong>
                <span>
                  {missionResult
                    ? runOutcomeText(missionResult, { rejected })
                    : "No mission has run in this session."}
                </span>
              </div>
            </div>
            {missionResult && (
              <div className="axon-fields-grid">
                <Field
                  label="steps"
                  value={`${missionResult.steps_completed ?? 0}/${
                    missionResult.steps_total ?? "?"
                  }`}
                />
                <Field label="approval" value={directApproval ? "waiting" : "clear"} />
                <Field
                  label="capability"
                  value={
                    acquisition?.record?.status ||
                    (missionResult.blocked_on ? "blocked" : "ready")
                  }
                />
              </div>
            )}
          </Panel>

          <ApprovalPanel
            directApproval={directApproval}
            acquisition={acquisition}
            deciding={deciding}
            decideDirect={decideDirect}
            decideAcquisition={decideAcquisition}
          />
          <NodeEditor
            selected={selected}
            capabilities={capabilities}
            argHint={argHint}
            nodeAnswer={nodeAnswer}
            updateNode={updateNode}
            close={() => setSelectedId(null)}
          />
          <ResultCard title="Final result" answer={answer} />
          <EvolutionFeed
            snapshot={systemSnapshot}
            acquisition={acquisition}
            missionResult={missionResult}
          />
        </aside>
      </main>
    </div>
  );
}
