import { useEffect, useRef, useState } from "react";
import { Mic, Plus, Trash2, Unlock, Volume2, VolumeX, Zap } from "lucide-react";
import { api, hasOwnerToken, setOwnerToken } from "../api.js";
import { compileGraphToPlan, planToGraph, topoOrder } from "../graphCompiler.js";
import { nodeStatuses, runOutcomeText, toneForMissionStatus } from "../graphExecutionState.js";
import { describeStage } from "../livePipeline.js";
import { speak, speechSynthesisSupported, stopSpeaking } from "../speechOutput.js";
import { extractAnswer, prettyValue } from "../v4/artifact.js";
import { useSpeechInput } from "../useSpeechInput.js";

/**
 * v5 — the graphical mission builder.
 *
 * GRAPH -> MISSION COMPILER -> EXISTING MISSION ENGINE. graphCompiler.js's
 * compileGraphToPlan() is the compiler; POST /missions/from-graph and
 * MissionService.start_from_plan() (backend, this same milestone) are the
 * engine entry point. There is no second execution engine here: a graph
 * built on this canvas produces the exact MissionPlan the Gemini planner
 * produces from free text, and from that point on -- Guardian, sandbox,
 * approval, resume -- it is one pipeline.
 *
 * "Plan it" (text or voice) is the convergence path: it runs the SAME
 * plannedMission() every other surface uses, then reconstructs the
 * resulting plan onto this canvas via graphCompiler.js's planToGraph() --
 * so a mission described in words and a mission drawn as nodes end up as
 * the same editable object, not two unrelated features bolted together.
 *
 * Node status is never invented. nodeStatuses() (graphExecutionState.js)
 * only reports what the last real mission result actually said about
 * each step; a node with nothing to report reads "not yet run".
 */

const NODE_W = 208;
const NODE_H = 112;

const TONE_COLOR = {
  ok: "#4ade80",
  danger: "#f87171",
  warn: "#fbbf24",
  idle: "#475569",
  acquiring: "#22d3ee",
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

export default function AppV5() {
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [goal, setGoal] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [connectFrom, setConnectFrom] = useState(null);
  const [capabilities, setCapabilities] = useState([]);

  const [compileError, setCompileError] = useState(null);
  const [running, setRunning] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [missionResult, setMissionResult] = useState(null);
  const [answer, setAnswer] = useState(null);
  const [lastCompiled, setLastCompiled] = useState(null); // { stepNumberById, plan }

  const [directApproval, setDirectApproval] = useState(null); // { missionId, approvalRequestId }
  const [acquisition, setAcquisition] = useState(null); // { missionId, actions, record }
  const [deciding, setDeciding] = useState(false);
  // BUG-011: resume-planned cannot distinguish "rejected" from "not yet
  // decided" in its own status word (both come back as
  // APPROVAL_REQUIRED -- see runOutcomeText()'s doc comment). The ONLY
  // place that distinction genuinely exists is api.decide()'s own
  // response, so it is captured here at the moment of the click, not
  // guessed from the status word afterwards.
  const [rejected, setRejected] = useState(false);

  const [unlocked, setUnlocked] = useState(hasOwnerToken());
  const [tokenInput, setTokenInput] = useState("");

  // Voice output mirrors AppV4's pattern exactly: off by default (no
  // audio a viewer did not ask for), speaks only the SAME terminal-
  // outcome sentence already on screen (runOutcomeText()), never a
  // separate scripted line.
  const [speakEnabled, setSpeakEnabled] = useState(false);

  const idCounter = useRef(1);
  const dragRef = useRef(null); // { id, offsetX, offsetY }
  const canvasRef = useRef(null);

  const speech = useSpeechInput({
    onText: (t) => setGoal(t),
    // A mic error (permission denied, no mic, network) is reported via
    // the SAME error banner a compile/run failure uses -- one honest
    // place on screen for "something went wrong", not a second silent
    // failure mode nothing shows.
    onError: (message) => setCompileError(message),
  });

  const announce = (result, opts) => {
    const text = runOutcomeText(result, opts);
    if (speakEnabled) speak(text);
    return text;
  };

  useEffect(() => {
    api
      .capabilities()
      .then((c) => setCapabilities(c?.capabilities || []))
      .catch(() => {});
  }, []);

  // ── node CRUD ────────────────────────────────────────────────────────

  const addNode = () => {
    const id = `n${idCounter.current++}`;
    const x = 40 + (nodes.length % 3) * 240;
    const y = 40 + Math.floor(nodes.length / 3) * 150;
    setNodes((prev) => [...prev, emptyNode(id, x, y)]);
    setSelectedId(id);
  };

  const updateNode = (id, patch) =>
    setNodes((prev) => prev.map((n) => (n.id === id ? { ...n, ...patch } : n)));

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

  const removeEdge = (from, to) =>
    setEdges((prev) => prev.filter((e) => !(e.from === from && e.to === to)));

  // ── dragging ─────────────────────────────────────────────────────────

  const onNodePointerDown = (e, node) => {
    if (e.button !== 0) return;
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

  // ── compile + run ────────────────────────────────────────────────────

  const resetRunState = () => {
    stopSpeaking(); // never let a stale result keep talking over a new run
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
              ? { ...prev, actions: [...prev.actions, { label, detail, tone }], record }
              : prev
          );
        },
      });
      setAcquisition((prev) =>
        prev && prev.missionId === missionId ? { ...prev, record: acquired } : prev
      );
    } catch (err) {
      setCompileError(String(err.message || err));
    }
  };

  const compileAndRun = async () => {
    if (!unlocked) {
      setCompileError("Unlock with the owner token below -- running a mission is a real, governed write.");
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

  // "Plan it": the text/voice convergence path. Runs the SAME real
  // plannedMission() every other surface uses, then reconstructs the
  // resulting plan onto the canvas so it can be seen and re-run as a
  // graph. This genuinely executes (there is no plan-only endpoint --
  // governance gates the same way regardless), so a step that needs
  // approval or a capability that does not exist still stops for a real
  // human decision below, exactly as a hand-built graph would.
  const planIt = async () => {
    const text = goal.trim();
    if (!text || planning) return;

    if (!unlocked) {
      setCompileError("Unlock with the owner token below -- running a mission is a real, governed write.");
      return;
    }

    setPlanning(true);
    setCompileError(null);
    resetRunState();

    try {
      const result = await api.plannedMission(text);
      const built = planToGraph({ goal: result.goal || text, steps: result.plan || [] });
      const laidOut = built.nodes.map((n, i) => ({
        ...n,
        x: 40 + (i % 3) * 240,
        y: 40 + Math.floor(i / 3) * 150,
      }));
      setNodes(laidOut);
      setEdges(built.edges);
      idCounter.current = laidOut.length + 1;

      const stepNumberById = new Map(laidOut.map((n) => [n.id, Number(n.id.slice(1))]));
      setLastCompiled({ stepNumberById, plan: { goal: result.goal || text, steps: result.plan || [] } });

      setMissionResult(result);
      setAnswer(extractAnswer(result));
      announce(result);

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

  // ── approvals ────────────────────────────────────────────────────────

  const decideDirect = async (approved) => {
    if (!directApproval || deciding) return;
    setDeciding(true);
    setRejected(!approved);
    try {
      // decide() itself is the ONE place a real REJECTED signal exists --
      // resume-planned's own re-derived status word cannot tell "rejected"
      // apart from "not yet decided" (see runOutcomeText()'s doc comment,
      // BUG-011). Captured here, not re-guessed from what comes back below.
      await api.decide(directApproval.approvalRequestId, approved);
      const resumed = await api.resumePlanned(directApproval.missionId);
      setMissionResult(resumed);
      setAnswer(extractAnswer(resumed));
      announce(resumed, { rejected: !approved });

      if (approved && resumed.status === "AWAITING_APPROVAL") {
        // Only a genuinely new approval gate further down the plan
        // re-arms this panel -- a rejection must never loop back into
        // "waiting for a decision" as if nothing happened.
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

        if (installed?.status !== "INSTALLED" && installed?.status !== "ALREADY_INSTALLED") {
          // BUG-008/BUG-010's own lesson, reapplied here: a real FAILED
          // install response carries its message under "error", and
          // ALREADY_INSTALLED is a safe idempotent outcome, never an
          // error -- so only a genuine non-install status is reported as
          // a problem, and with its real message, not a bare status word.
          setCompileError(
            `Install did not complete: ${installed?.reason || installed?.error || installed?.status || "unknown"}`
          );
        }

        const resumedId =
          installed?.mission_resumed?.mission_id ||
          (typeof installed?.mission_resumed === "string" ? installed.mission_resumed : null);
        if (resumedId) {
          const resumed = await api.mission(resumedId);
          setMissionResult(resumed);
          setAnswer(extractAnswer(resumed));
          announce(resumed);
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
    } catch (err) {
      setCompileError(String(err.message || err));
    } finally {
      setDeciding(false);
    }
  };

  // ── derived ──────────────────────────────────────────────────────────

  const statuses = lastCompiled
    ? nodeStatuses({ nodes, stepNumberById: lastCompiled.stepNumberById, missionResult })
    : new Map();

  // The ONE genuinely real-time per-node override: while acquisition is
  // actively streaming (GET /missions/{id}/acquire/stream), the exact
  // node that BLOCKED gets the real current stage's own label instead of
  // the static "BLOCKED" text -- this is live because the underlying
  // data genuinely is (see graphExecutionState.js's doc comment on the
  // real-time boundary). Every other node's state still comes only from
  // the last real mission result; nothing else is fabricated as "in
  // progress".
  if (acquisition && lastCompiled && missionResult?.blocked_on) {
    const blockedStep = missionResult.blocked_on.step;
    const blockedNodeId = [...lastCompiled.stepNumberById.entries()].find(
      ([, n]) => n === blockedStep
    )?.[0];
    if (blockedNodeId) {
      const stage = acquisition.record ? describeStage(acquisition.record) : null;
      statuses.set(blockedNodeId, {
        tone: "acquiring",
        label: stage?.label || "Acquiring a missing capability…",
        detail: stage?.detail || "",
      });
    }
  }

  const selected = nodes.find((n) => n.id === selectedId) || null;
  const isRunning = running || planning;

  const center = (n) => ({ x: n.x + NODE_W / 2, y: n.y + NODE_H / 2 });

  return (
    <div className="min-h-screen bg-[#06090f] text-slate-100 font-sans">
      {/* topbar */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-white/[0.07] glass">
        <span className="font-semibold tracking-tight text-[13px]">
          AION Axon — Graphical Mission Builder
        </span>
        <span className="text-[10px] text-slate-500 font-mono">
          graph → mission compiler → the real governed engine
        </span>

        <div className="ml-auto flex items-center gap-2">
          {!unlocked ? (
            <div className="flex items-center gap-1.5">
              <input
                type="password"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="owner token"
                autoComplete="off"
                className="bg-black/40 border border-white/10 rounded-md text-[11px] px-2 py-1 outline-none placeholder:text-slate-600"
              />
              <button
                onClick={() => {
                  if (!tokenInput.trim()) return;
                  setOwnerToken(tokenInput);
                  setTokenInput("");
                  setUnlocked(true);
                }}
                className="flex items-center gap-1 px-2 py-1 rounded-md border border-cyan-400/40 text-cyan-300 text-[10px] font-bold uppercase"
              >
                <Unlock size={11} /> Unlock
              </button>
            </div>
          ) : (
            <span className="text-[10px] text-emerald-400 font-mono">owner unlocked</span>
          )}

          {/* Speaks only the real terminal outcome text already on
              screen (runOutcomeText()) -- never a scripted line. Hidden,
              not disabled, when the browser has no SpeechSynthesis; off
              by default, same reasoning as AppV4. */}
          {speechSynthesisSupported() && (
            <button
              onClick={() => setSpeakEnabled((v) => !v)}
              title={speakEnabled ? "Voice output on — click to mute" : "Voice output off — click to enable"}
              aria-label={speakEnabled ? "Mute voice output" : "Enable voice output"}
              className={`h-7 w-7 grid place-items-center rounded-full transition-colors ${
                speakEnabled ? "text-cyan-300" : "text-slate-500 hover:bg-white/[0.06]"
              }`}
            >
              {speakEnabled ? <Volume2 size={13} /> : <VolumeX size={13} />}
            </button>
          )}
        </div>
      </div>

      <div className="grid xl:grid-cols-[1fr_360px] gap-4 p-4">
        {/* ── canvas ─────────────────────────────────────────────── */}
        <div className="flex flex-col gap-2 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={addNode}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full framer-pill text-[11px] hover:bg-white/[0.06]"
            >
              <Plus size={13} /> Add node
            </button>

            {connectFrom && (
              <span className="text-[11px] text-cyan-300 font-mono">
                click a target node to connect from "{connectFrom}" (click it again to cancel)
              </span>
            )}

            <div className="flex-1" />

            {speech.supported && (
              <button
                onClick={speech.toggle}
                title="Speak a mission description"
                className={`h-7 w-7 grid place-items-center rounded-full transition-colors ${
                  speech.listening ? "text-red-400 mic-live bg-red-400/10" : "framer-pill text-slate-400"
                }`}
              >
                <Mic size={13} />
              </button>
            )}
            <input
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="Describe the mission (typed or spoken) — 'Plan it' builds this graph for you"
              className="bg-black/40 border border-white/10 rounded-md text-[11.5px] px-2.5 py-1.5 outline-none placeholder:text-slate-600 w-[360px] max-w-full"
            />
            <button
              onClick={planIt}
              disabled={planning || !goal.trim()}
              className="px-3 py-1.5 rounded-full text-[11px] font-semibold text-white disabled:opacity-40"
              style={{ background: "linear-gradient(135deg,#0066ff,#00f0ff)" }}
            >
              {planning ? "Planning…" : "Plan it"}
            </button>
          </div>

          <div
            ref={canvasRef}
            className="relative framer-canvas-frame min-h-[460px] overflow-auto scroll-thin"
            style={{ background: "#090a0f" }}
          >
            <svg className="absolute inset-0 pointer-events-none" width="100%" height="100%">
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
                    stroke="rgba(0,136,255,0.55)"
                    strokeWidth="1.5"
                    markerEnd="url(#arrow)"
                  />
                );
              })}
              <defs>
                <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                  <path d="M0,0 L8,4 L0,8 Z" fill="rgba(0,136,255,0.7)" />
                </marker>
              </defs>
            </svg>

            {nodes.length === 0 && (
              <div className="absolute inset-0 grid place-items-center text-[11px] text-slate-600 italic">
                Add a node, or describe the mission above and click "Plan it".
              </div>
            )}

            {/* The ONE honest global "work is happening" signal for the
                main plan's execution. There is no per-step streaming
                endpoint for a normal mission run (see
                graphExecutionState.js's real-time boundary comment), so
                this is deliberately a single banner, not per-node
                fabricated EXECUTING states. */}
            {isRunning && (
              <div
                className="absolute top-0 left-0 right-0 z-10 px-3 py-1.5 text-[10px] font-mono text-cyan-200 orb-breathe"
                style={{ background: "rgba(0,102,255,0.14)", borderBottom: "1px solid rgba(0,136,255,0.35)" }}
              >
                {planning ? "Planning the mission…" : "Running the mission through the real governed engine…"}
              </div>
            )}

            {nodes.map((n) => {
              const st = statuses.get(n.id);
              const dot = TONE_COLOR[st?.tone] || TONE_COLOR.idle;
              return (
                <div
                  key={n.id}
                  onPointerDown={(e) => onNodePointerDown(e, n)}
                  onClick={() => handleNodeClick(n.id)}
                  className="absolute rounded-xl p-2.5 cursor-grab active:cursor-grabbing select-none"
                  style={{
                    left: n.x,
                    top: n.y,
                    width: NODE_W,
                    minHeight: NODE_H,
                    background: "rgba(13,16,28,0.9)",
                    border:
                      selectedId === n.id
                        ? "1.5px solid #0088ff"
                        : connectFrom === n.id
                        ? "1.5px solid #00f0ff"
                        : "1px solid rgba(255,255,255,0.09)",
                    boxShadow: selectedId === n.id ? "0 0 16px rgba(0,102,255,0.35)" : "none",
                  }}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full shrink-0" style={{ background: dot }} />
                    <span className="font-mono text-[10px] text-slate-500">{n.id}</span>
                    <span className="ml-auto text-[9px] px-1.5 py-0.5 rounded framer-pill text-slate-400">
                      {n.risk}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-200 mt-1 leading-tight break-words">
                    {n.description || "(no description)"}
                  </p>
                  <p className="font-mono text-[10px] text-cyan-300/80 mt-1 truncate">
                    {n.tool || "— let AION acquire —"}
                  </p>
                  {st && (
                    <p className="text-[9px] mt-1 leading-tight break-words" style={{ color: dot }}>
                      {st.label}
                    </p>
                  )}
                  <div className="flex items-center gap-2 mt-1.5">
                    <button
                      onPointerDown={(e) => e.stopPropagation()}
                      onClick={(e) => {
                        e.stopPropagation();
                        setConnectFrom(n.id);
                      }}
                      className="text-[9px] text-slate-500 hover:text-cyan-300"
                    >
                      connect →
                    </button>
                    <button
                      onPointerDown={(e) => e.stopPropagation()}
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteNode(n.id);
                      }}
                      className="text-[9px] text-slate-500 hover:text-red-400 ml-auto"
                    >
                      <Trash2 size={10} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {edges.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {edges.map((e) => (
                <span
                  key={`${e.from}->${e.to}`}
                  className="framer-pill text-[10px] font-mono px-2 py-1 flex items-center gap-1.5 text-slate-400"
                >
                  {e.from} → {e.to}
                  <button onClick={() => removeEdge(e.from, e.to)} className="text-slate-600 hover:text-red-400">
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}

          {compileError && (
            <p className="text-[11px] text-red-300 bg-red-400/10 border border-red-400/30 rounded-md px-3 py-2">
              {compileError}
            </p>
          )}

          <button
            onClick={compileAndRun}
            disabled={running || !nodes.length}
            className="self-start flex items-center gap-1.5 px-4 py-2 rounded-full text-[12px] font-bold text-white disabled:opacity-40"
            style={{ background: "linear-gradient(135deg,#0066ff,#00f0ff)", boxShadow: "0 0 18px rgba(0,102,255,0.5)" }}
          >
            <Zap size={13} /> {running ? "Compiling & running…" : "Compile & Run"}
          </button>
        </div>

        {/* ── side panel: node editor / run state ───────────────── */}
        <div className="framer-panel p-3.5 flex flex-col gap-3 min-h-0">
          {selected ? (
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-slate-300">
                  Node {selected.id}
                </span>
                <button onClick={() => setSelectedId(null)} className="text-[10px] text-slate-500">
                  close
                </button>
              </div>

              <label className="block text-[9.5px] uppercase tracking-wider text-slate-500">
                Description
              </label>
              <textarea
                value={selected.description}
                onChange={(e) => updateNode(selected.id, { description: e.target.value })}
                rows={2}
                className="w-full bg-black/40 border border-white/10 rounded-md text-[11.5px] px-2 py-1.5 outline-none resize-none"
              />

              <label className="block text-[9.5px] uppercase tracking-wider text-slate-500">
                Capability
              </label>
              <select
                value={selected.tool || ""}
                onChange={(e) => updateNode(selected.id, { tool: e.target.value || null })}
                className="w-full bg-black/40 border border-white/10 rounded-md text-[11px] px-2 py-1.5 outline-none font-mono"
              >
                <option value="">— let AION acquire —</option>
                {capabilities.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name} {c.implemented ? "" : "(not yet built)"}
                  </option>
                ))}
              </select>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[9.5px] uppercase tracking-wider text-slate-500">Risk</label>
                  <select
                    value={selected.risk}
                    onChange={(e) => updateNode(selected.id, { risk: e.target.value })}
                    className="w-full bg-black/40 border border-white/10 rounded-md text-[11px] px-2 py-1.5 outline-none"
                  >
                    <option value="LOW">LOW</option>
                    <option value="MEDIUM">MEDIUM</option>
                    <option value="HIGH">HIGH</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[9.5px] uppercase tracking-wider text-slate-500">Kind</label>
                  <select
                    value={selected.kind}
                    onChange={(e) => updateNode(selected.id, { kind: e.target.value })}
                    className="w-full bg-black/40 border border-white/10 rounded-md text-[11px] px-2 py-1.5 outline-none"
                  >
                    <option value="READ_ANALYZE">READ_ANALYZE</option>
                    <option value="EXTERNAL_EFFECT">EXTERNAL_EFFECT</option>
                  </select>
                </div>
              </div>

              <label className="block text-[9.5px] uppercase tracking-wider text-slate-500">
                Args (one per line — use @{"{node id}"} or @{"{node id}"}.field to reference a
                connected node's real output)
              </label>
              <textarea
                value={(selected.args || []).join("\n")}
                onChange={(e) => updateNode(selected.id, { args: e.target.value.split("\n") })}
                rows={3}
                className="w-full bg-black/40 border border-white/10 rounded-md font-mono text-[10.5px] px-2 py-1.5 outline-none resize-none"
              />
            </div>
          ) : (
            <p className="text-[11px] text-slate-500 italic">
              Click a node to edit it, or drag it to reposition. "connect →" then click another
              node to declare a dependency.
            </p>
          )}

          {/* run result */}
          {missionResult && (
            <div className="border-t border-white/[0.07] pt-3 space-y-2">
              <p className="text-[10px] uppercase tracking-wider font-bold text-slate-400">
                Mission {missionResult.mission_id?.slice(0, 8)} —{" "}
                <span style={{ color: TONE_COLOR[toneForMissionStatus(missionResult.status)] }}>
                  {missionResult.status}
                </span>
              </p>
              {/* BUG-011: the real reason, not just the bare status word --
                  see runOutcomeText()'s doc comment for the full contract
                  this reads (step_results[last].reason/error, the
                  summary's own reason/error, and the decide()-captured
                  rejection signal, in that order). */}
              <p className="text-[10.5px] text-slate-400 leading-relaxed">
                {runOutcomeText(missionResult, { rejected })}
              </p>

              {answer && (
                <div className="rounded-lg p-2.5" style={{ background: "rgba(16,185,129,0.08)", border: "1px solid rgba(16,185,129,0.4)" }}>
                  {answer.fields.map(([k, v]) => (
                    <div key={k} className="flex items-baseline gap-2">
                      <span className="font-mono text-[9.5px] text-slate-500 min-w-[80px]">{k}</span>
                      <span className="font-mono text-[12px] text-emerald-200 font-semibold">{prettyValue(v)}</span>
                    </div>
                  ))}
                </div>
              )}

              {directApproval && (
                <div className="rounded-lg p-2.5" style={{ background: "rgba(0,102,255,0.1)", border: "1.5px solid rgba(0,136,255,0.7)" }}>
                  <p className="text-[10px] uppercase tracking-wider font-bold text-[#00f0ff] mb-1.5">
                    ⏸ A step needs your approval
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => decideDirect(true)}
                      disabled={deciding}
                      className="px-2.5 py-1 rounded-lg border border-emerald-400/50 text-emerald-300 text-[10px] font-bold uppercase disabled:opacity-40"
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => decideDirect(false)}
                      disabled={deciding}
                      className="px-2.5 py-1 rounded-lg border border-red-400/50 text-red-300 text-[10px] font-bold uppercase disabled:opacity-40"
                    >
                      Reject
                    </button>
                  </div>
                </div>
              )}

              {acquisition && (
                <div className="rounded-lg p-2.5 space-y-1.5" style={{ background: "rgba(0,102,255,0.08)", border: "1px solid rgba(0,136,255,0.4)" }}>
                  <p className="text-[10px] uppercase tracking-wider font-bold text-slate-400">
                    Acquiring a missing capability…
                  </p>
                  <div className="space-y-1 max-h-[160px] overflow-y-auto scroll-thin">
                    {acquisition.actions.map((a, i) => (
                      <div key={i} className="text-[10px] text-slate-400">
                        <span style={{ color: TONE_COLOR[a.tone] || "#94a3b8" }}>●</span> {a.label}
                        <div className="text-[9px] text-slate-600 pl-3">{a.detail}</div>
                      </div>
                    ))}
                  </div>

                  {acquisition.record?.status === "AWAITING_APPROVAL" && (
                    <div className="pt-1.5 border-t border-white/[0.07]">
                      <p className="text-[10px] text-slate-300 mb-1.5">
                        Proposed <span className="font-mono">{acquisition.record.candidate?.name}</span> — approve to
                        install and resume this mission.
                      </p>
                      <div className="flex gap-2">
                        <button
                          onClick={() => decideAcquisition(true)}
                          disabled={deciding}
                          className="px-2.5 py-1 rounded-lg border border-emerald-400/50 text-emerald-300 text-[10px] font-bold uppercase disabled:opacity-40"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => decideAcquisition(false)}
                          disabled={deciding}
                          className="px-2.5 py-1 rounded-lg border border-red-400/50 text-red-300 text-[10px] font-bold uppercase disabled:opacity-40"
                        >
                          Reject
                        </button>
                      </div>
                    </div>
                  )}

                  {acquisition.record?.status && acquisition.record.status !== "AWAITING_APPROVAL" && (
                    <p className="text-[10px] text-amber-300">
                      {acquisition.record.status} — {acquisition.record.reason || ""}
                    </p>
                  )}
                </div>
              )}

              <p className="text-[9px] text-slate-500">
                steps {missionResult.steps_completed ?? 0}/{missionResult.steps_total ?? "?"}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
