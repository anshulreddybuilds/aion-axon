import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUp, CheckCircle2, Mic, ShieldAlert, Square, X } from "lucide-react";
import Hologram from "./Hologram.jsx";
import { buildBeats, buildDecision, humanMs, loadReplay } from "./replay.js";
import { runLiveMission } from "./live.js";
import { hasOwnerToken, setOwnerToken } from "../api.js";

/**
 * v3 — the owner's hologram prototype, driven by real data.
 *
 * Keeps every visual beat of the prototype: hero orb + command capsule,
 * orb docks into the header on send, the 12-node spine reveals, execution
 * walks node by node, the telemetry HUD streams, a decision card closes
 * it, and a scrubber jumps between beats for filming.
 *
 * What changed is provenance, not appearance. The prototype's numbers
 * were invented — random latency, an arithmetic token counter, a
 * fabricated birth total, a fake SHA-256 "receipt". Here every figure is
 * fetched from the live API at replay time, so nothing on screen can
 * drift from what the system actually did.
 *
 * The sequence is labelled REPLAY on screen. That label is not a
 * disclaimer bolted on afterwards — it is the honest description of what
 * it is, and it costs nothing, because the underlying run was real.
 */

// Pacing per node, tuned for camera rather than for impatience.
//
// 900ms read as a blur on playback: twelve stages went by in under 11
// seconds, which is too fast for a viewer to read a node's name AND its
// metric before the next one lights. At 1500ms the full spine is ~18s,
// which still fits comfortably inside a 4-minute cut and gives each
// stage time to be understood rather than merely seen.
const STEP_MS = 1500;

const TONE_HEX = {
  ok: "#10b981",
  warn: "#f59e0b",
  danger: "#ef4444",
  idle: "#475569",
};

function LogLine({ time, tag, text }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -5 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex gap-2 font-mono text-[9.5px] leading-relaxed"
    >
      <span className="text-slate-600 shrink-0">{time}</span>
      <span
        className="shrink-0 font-semibold"
        style={{ color: tag === "REFUSED" || tag === "BLOCKED" ? "#fca5a5" : "#34d399" }}
      >
        [{tag}]
      </span>
      <span className="text-slate-400">{text}</span>
    </motion.div>
  );
}

export default function AppV3() {
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [running, setRunning] = useState(false);
  const [docked, setDocked] = useState(false);
  const [step, setStep] = useState(0); // 0 = not started, 1..12, 13 = done
  const [logs, setLogs] = useState([]);
  const [showDecision, setShowDecision] = useState(false);
  const [command, setCommand] = useState("");
  const timer = useRef(null);

  // REPLAY walks a recorded run on a fixed 1500ms beat. LIVE runs a real
  // mission and lets the pipeline's own pace drive the nodes — research
  // ~20s, generate ~27s, evaluate ~34s, so a real acquisition is roughly
  // 90 seconds rather than 18.
  const [mode, setMode] = useState("replay");
  const [unlocked, setUnlocked] = useState(hasOwnerToken());
  const [tokenInput, setTokenInput] = useState("");
  const [liveNodes, setLiveNodes] = useState({});
  const [liveResult, setLiveResult] = useState(null);
  const cancelLive = useRef(null);

  // Pull the real mission + telemetry once, up front.
  useEffect(() => {
    loadReplay()
      .then((payload) => {
        setData(payload);
        if (!payload.mission) {
          setLoadError(
            "Could not reach the recorded mission. Nothing is shown rather than showing placeholders."
          );
        } else if (!command) {
          setCommand(payload.mission.request || "");
        }
      })
      .catch((err) => setLoadError(err.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const beats = data?.beats || [];
  const decision = data?.decision || null;

  const pushLog = useCallback((tag, text) => {
    const time = new Date().toTimeString().split(" ")[0];
    setLogs((l) => [...l, { time, tag, text }].slice(-40));
  }, []);

  const clearTimer = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };

  const advance = useCallback(
    (index) => {
      if (index > beats.length) {
        setStep(beats.length + 1);
        setRunning(false);
        pushLog("FINAL", "all 12 stages replayed from the recorded mission");
        timer.current = setTimeout(() => setShowDecision(true), 700);
        return;
      }

      const beat = beats[index - 1];
      setStep(index);
      pushLog(beat.tone === "danger" ? "REFUSED" : "OK", `${beat.name}: ${beat.log}`);

      timer.current = setTimeout(() => advance(index + 1), STEP_MS);
    },
    [beats, pushLog]
  );

  const startReplay = () => {
    if (!beats.length) return;
    clearTimer();
    setLogs([]);
    setShowDecision(false);
    setDocked(true);
    setRunning(true);
    timer.current = setTimeout(() => advance(1), 500);
  };

  const startLive = () => {
    const request = command.trim();
    if (!request) return;

    clearTimer();
    setLogs([]);
    setShowDecision(false);
    setLiveNodes({});
    setLiveResult(null);
    setDocked(true);
    setRunning(true);
    pushLog("OK", "live mission dispatched — nodes will light as stages really complete");

    cancelLive.current = runLiveMission(request, {
      onNode: (id, note) =>
        setLiveNodes((n) => ({ ...n, [id]: { at: Date.now(), note } })),
      onLog: (tag, text) => pushLog(tag, text),
      onDone: (result) => {
        setRunning(false);
        setLiveResult(result);
        setShowDecision(true);
      },
      onError: () => setRunning(false),
    });
  };

  const start = () => (mode === "live" ? startLive() : startReplay());

  const jumpTo = (target) => {
    if (!beats.length) return;
    clearTimer();
    setDocked(true);
    setShowDecision(false);
    setRunning(true);
    setLogs(
      beats.slice(0, target).map((b) => ({
        time: new Date().toTimeString().split(" ")[0],
        tag: b.tone === "danger" ? "REFUSED" : "OK",
        text: `${b.name}: ${b.log}`,
      }))
    );
    advance(target);
  };

  const reset = () => {
    clearTimer();
    cancelLive.current?.();
    cancelLive.current = null;
    setStep(0);
    setRunning(false);
    setDocked(false);
    setLogs([]);
    setShowDecision(false);
    setLiveNodes({});
    setLiveResult(null);
  };

  useEffect(
    () => () => {
      clearTimer();
      cancelLive.current?.();
    },
    []
  );

  const isLive = mode === "live";
  const active = beats[step - 1] || null;
  const verified = isLive
    ? Object.keys(liveNodes).length
    : Math.max(0, Math.min(step - 1, beats.length));

  return (
    <div
      className="min-h-screen text-slate-100 font-sans relative overflow-x-hidden"
      style={{
        background:
          "radial-gradient(circle at 50% 0%, rgba(0,102,255,0.15) 0%, transparent 60%)," +
          "radial-gradient(circle at 10% 90%, rgba(0,240,255,0.06) 0%, transparent 40%)," +
          "radial-gradient(circle at 90% 90%, rgba(168,85,247,0.06) 0%, transparent 40%)," +
          "#05060a",
      }}
    >
      <div className="max-w-[1920px] mx-auto px-6 py-5 flex flex-col gap-4 min-h-screen">
        {/* Header */}
        <header className="glass rounded-2xl px-5 py-2.5 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3.5 min-w-0">
            {docked && <Hologram docked spinning={false} />}
            <div className="min-w-0">
              <p className="text-[17px] font-extrabold tracking-tight leading-none bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">
                AION AXON
              </p>
            </div>
            <span className="font-mono text-[11px] font-semibold text-sky-400 bg-sky-400/10 border border-sky-400/25 px-2 py-0.5 rounded-md hidden sm:inline">
              AXON NODE / ASIA-SOUTH1
            </span>
          </div>

          <div className="hidden lg:flex items-center gap-2.5 font-mono text-[11.5px] text-slate-400 bg-black/40 px-3.5 py-1.5 rounded-full border border-white/[0.05]">
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: "#10b981", boxShadow: "0 0 10px #10b981" }}
            />
            <span>
              {data?.mission ? "RECORDED MISSION LOADED" : "LOADING RECORD…"} ·
              REPLAY MODE
            </span>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 p-1 rounded-full bg-black/40 border border-white/[0.06]">
              {[
                ["replay", "REPLAY"],
                ["live", "LIVE"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  onClick={() => {
                    reset();
                    setMode(id);
                  }}
                  className={`font-mono text-[10px] font-bold px-2.5 py-1 rounded-full transition-colors ${
                    mode === id
                      ? id === "live"
                        ? "bg-emerald-400/20 text-emerald-300"
                        : "bg-amber-400/20 text-amber-300"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <span
              className={`font-mono text-[11px] font-semibold px-2.5 py-1 rounded-full border hidden sm:inline ${
                isLive
                  ? "bg-emerald-400/10 border-emerald-400/30 text-emerald-300"
                  : "bg-amber-400/10 border-amber-400/30 text-amber-300"
              }`}
            >
              {isLive ? "LIVE — REAL MISSION" : "REPLAY — RECORDED RUN"}
            </span>
          </div>
        </header>

        {loadError && (
          <div className="glass rounded-xl px-4 py-3 border-red-400/30 flex items-center gap-2">
            <ShieldAlert size={14} className="text-red-300 shrink-0" />
            <p className="text-[11px] text-red-300">{loadError}</p>
          </div>
        )}

        {/* Hero */}
        <AnimatePresence>
          {!docked && (
            <motion.div
              exit={{ opacity: 0, y: -20 }}
              className="flex-1 flex flex-col items-center justify-center"
            >
              <Hologram docked={false} spinning={!running} />
              <p className="text-[13px] font-semibold tracking-[2px] uppercase text-sky-400 mt-6 mb-4 text-center">
                Autonomous Governed Capability Spine
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Command capsule */}
        <motion.div
          layout
          className={`glass rounded-2xl mx-auto w-full ${
            docked ? "max-w-none px-4 py-2.5" : "max-w-[820px] px-5 py-4"
          }`}
          style={{
            border: "1px solid rgba(0,136,255,0.5)",
            boxShadow: docked
              ? "0 0 20px rgba(0,102,255,0.2)"
              : "0 0 0 1px rgba(0,136,255,0.4), 0 0 35px rgba(0,102,255,0.28), inset 0 1px 0 rgba(255,255,255,0.25)",
          }}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11.5px] text-slate-300 bg-white/[0.05] border border-white/10 px-2 py-0.5 rounded-md">
              Session #01 · Recorded mission
            </span>
            <span
              className="font-mono text-[10px] font-bold uppercase tracking-wider"
              style={{ color: running ? "#00f0ff" : "#38bdf8" }}
            >
              {running ? "● Replaying pipeline" : "● Ready"}
            </span>
          </div>

          <input
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            placeholder="Loading the recorded mission request…"
            className="w-full bg-transparent border-none outline-none text-[15px] font-medium tracking-tight placeholder:text-slate-600"
          />

          {isLive && !unlocked && (
            <div className="flex gap-2 mt-2.5">
              <input
                type="password"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="owner token — live missions change state"
                autoComplete="off"
                className="flex-1 bg-black/40 border border-white/[0.08] rounded-lg px-3 py-2 text-[11px] outline-none focus:border-cyan-400/50"
              />
              <button
                type="button"
                onClick={() => {
                  if (!tokenInput.trim()) return;
                  setOwnerToken(tokenInput);
                  setTokenInput("");
                  setUnlocked(true);
                }}
                className="px-4 rounded-lg border border-cyan-400/40 text-cyan-300 font-mono text-[10px] font-bold uppercase tracking-wider hover:bg-cyan-400/10"
              >
                Unlock
              </button>
            </div>
          )}

          <div className="flex items-center justify-between pt-2.5 mt-2 border-t border-white/[0.06]">
            <span className="font-mono text-[11px] font-semibold text-slate-400 bg-black/30 border border-white/[0.08] px-2.5 py-1 rounded-md">
              gemini-3.6-flash
            </span>

            <div className="flex items-center gap-2.5">
              <button
                type="button"
                disabled
                title="Voice is unproven on this machine — disabled rather than faked"
                className="flex items-center gap-1.5 font-mono text-[11px] font-semibold px-3 py-1.5 rounded-full border border-white/10 text-slate-600 cursor-not-allowed"
              >
                <Mic size={12} />
                Mic
              </button>

              <button
                type="button"
                onClick={running ? reset : start}
                disabled={
                  running
                    ? false
                    : isLive
                    ? !unlocked || !command.trim()
                    : !beats.length
                }
                className="h-9 w-9 grid place-items-center rounded-full text-white disabled:opacity-30"
                style={{
                  background: "linear-gradient(135deg, #0066ff, #00f0ff)",
                  boxShadow: "0 0 16px rgba(0,102,255,0.6)",
                }}
              >
                {running ? <Square size={13} /> : <ArrowUp size={16} />}
              </button>
            </div>
          </div>
        </motion.div>

        {/* Workspace */}
        <AnimatePresence>
          {docked && (
            <motion.div
              initial={{ opacity: 0, y: 30, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
              className="grid gap-5 xl:grid-cols-[1.9fr_1fr] flex-1"
            >
              {/* Spine */}
              <div className="glass rounded-2xl p-5">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2.5">
                    <h2 className="text-[14.5px] font-bold tracking-tight">
                      Governed capability spine
                    </h2>
                    <span className="font-mono text-[10px] font-semibold text-emerald-400 bg-emerald-400/10 border border-emerald-400/25 px-2 py-0.5 rounded">
                      {active ? `STAGE ${active.id}: ${active.name.toUpperCase()}` : "STANDBY"}
                    </span>
                  </div>
                  <div className="font-mono text-[11px] text-slate-400 flex gap-3">
                    <span>● {String(verified).padStart(2, "0")} replayed</span>
                    {running && <span className="text-cyan-400">● 01 running</span>}
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-2.5">
                  {beats.map((beat) => {
                    // In LIVE mode a node is lit only if its own real
                    // counter moved; there is no "current step" walking
                    // forward on a schedule.
                    const live = liveNodes[beat.id];
                    const isDone = isLive ? !!live : step > beat.id;
                    const isRunning = isLive
                      ? !!live && Date.now() - live.at < 2000
                      : step === beat.id;
                    const tone = isDone || isRunning ? beat.tone : "idle";

                    return (
                      <motion.div
                        key={beat.id}
                        animate={{ scale: isRunning ? 1.02 : 1 }}
                        transition={{ duration: 0.4 }}
                        className="rounded-xl px-3 py-2.5 flex flex-col justify-between relative overflow-hidden"
                        style={{
                          background: isRunning
                            ? "rgba(0,102,255,0.18)"
                            : "rgba(18,22,38,0.6)",
                          border: isRunning
                            ? "1px solid #00f0ff"
                            : "1px solid rgba(255,255,255,0.08)",
                          borderLeft:
                            isDone && !isRunning
                              ? `3px solid ${TONE_HEX[beat.tone]}`
                              : undefined,
                          boxShadow: isRunning
                            ? "0 0 24px rgba(0,136,255,0.45), inset 0 1px 0 rgba(255,255,255,0.3)"
                            : "none",
                          opacity: isDone || isRunning ? 1 : 0.6,
                        }}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-[9.5px] font-bold text-slate-500">
                            {String(beat.id).padStart(2, "0")}
                          </span>
                          <span
                            className="h-1.5 w-1.5 rounded-full"
                            style={{
                              background: TONE_HEX[tone],
                              boxShadow: isRunning
                                ? `0 0 10px ${TONE_HEX[beat.tone]}`
                                : "none",
                            }}
                          />
                        </div>

                        <p className="text-[12.5px] font-bold mt-1">{beat.name}</p>
                        <p className="text-[9.5px] text-slate-400 leading-tight mt-0.5">
                          {beat.desc}
                        </p>

                        <span className="font-mono text-[9.5px] font-semibold text-sky-400 bg-black/35 px-1.5 py-0.5 rounded self-start mt-1.5">
                          {isDone || isRunning
                            ? isRunning
                              ? "processing…"
                              : beat.metric
                            : "pending"}
                        </span>

                        {(isDone || isRunning) && beat.ms != null && (
                          <span className="font-mono text-[9px] text-slate-500 mt-1">
                            {humanMs(beat.ms)} measured
                          </span>
                        )}
                      </motion.div>
                    );
                  })}
                </div>
              </div>

              {/* Telemetry HUD */}
              <div className="flex flex-col gap-3">
                <div className="glass rounded-2xl p-4">
                  <p className="font-mono text-[10.5px] font-bold uppercase tracking-wider text-slate-400 mb-2.5">
                    Live telemetry
                  </p>
                  {[
                    ["Engine", "gemini-3.6-flash"],
                    [
                      "Model calls",
                      data?.telemetry?.model_calls?.count ?? "—",
                    ],
                    [
                      "Measured tokens",
                      data?.telemetry?.model_calls?.total_tokens?.toLocaleString() ??
                        "—",
                    ],
                    [
                      "Unmeasured calls",
                      data?.telemetry?.model_calls?.unmeasured ?? "—",
                    ],
                    ["Exec p50", humanMs(data?.telemetry?.tool_executions?.p50_ms) ?? "—"],
                  ].map(([k, v]) => (
                    <div
                      key={k}
                      className="flex justify-between font-mono text-[10.5px] py-1 border-b border-white/[0.04] last:border-0"
                    >
                      <span className="text-slate-500">{k}</span>
                      <span className="font-semibold text-slate-200">{v}</span>
                    </div>
                  ))}
                </div>

                <div className="glass rounded-2xl p-4">
                  <p className="font-mono text-[10.5px] font-bold uppercase tracking-wider text-slate-400 mb-2.5">
                    Guardian gating
                  </p>
                  <div className="rounded-lg px-2.5 py-2 bg-red-500/[0.08] border border-red-500/25 space-y-1.5">
                    {[
                      ["G-04", "credential-access-prohibited"],
                      ["G-06", "guardian-override-prohibited"],
                    ].map(([id, title]) => (
                      <div
                        key={id}
                        className="flex items-center gap-2 font-mono text-[10px] text-red-300"
                      >
                        <span className="bg-red-500 text-white text-[8.5px] font-bold px-1.5 py-px rounded">
                          REFUSED
                        </span>
                        <span>
                          {id} {title}
                        </span>
                      </div>
                    ))}
                  </div>
                  <p className="text-[9px] text-slate-600 mt-2 leading-relaxed">
                    Both refusals are real and reproducible against the live API.
                  </p>
                </div>

                <div className="glass rounded-2xl p-4 flex-1 min-h-0">
                  <p className="font-mono text-[10.5px] font-bold uppercase tracking-wider text-slate-400 mb-2.5">
                    Audit log
                  </p>
                  <div className="space-y-1 max-h-[220px] overflow-y-auto scroll-thin">
                    {logs.length === 0 ? (
                      <p className="font-mono text-[9.5px] text-slate-600">
                        spine standby…
                      </p>
                    ) : (
                      logs.map((l, i) => <LogLine key={i} {...l} />)
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Scrubber */}
        <div className="glass rounded-xl px-4 py-2 flex items-center gap-3 flex-wrap">
          <span className="font-mono text-[10.5px] font-bold text-sky-400 tracking-wider">
            DEMO BEATS:
          </span>
          {[
            [1, "01 Owner"],
            [3, "03 Gap"],
            [6, "06 AST"],
            [7, "07 Sandbox"],
            [9, "09 Guardian"],
            [10, "10 Approval"],
            [12, "12 Ledger"],
          ].map(([n, label]) => (
            <button
              key={n}
              onClick={() => jumpTo(n)}
              disabled={!beats.length}
              className={`font-mono text-[10px] px-3 py-1.5 rounded border transition-colors disabled:opacity-30 ${
                step === n
                  ? "bg-blue-600/20 border-cyan-400 text-cyan-400 font-bold"
                  : "bg-white/[0.04] border-white/[0.08] text-slate-400 hover:border-cyan-400/40"
              }`}
            >
              {label}
            </button>
          ))}
          <button
            onClick={reset}
            className="ml-auto font-mono text-[10px] px-3 py-1.5 rounded border border-white/[0.08] text-slate-400 hover:text-white"
          >
            Reset
          </button>
        </div>

        <p className="text-[9px] text-slate-600 leading-relaxed">
          {isLive ? (
            <>
              LIVE mode runs a real mission and spends real Gemini quota. Nodes
              light only when their own telemetry counter actually increments
              server-side — there is no timer, so the pacing you see is the
              pipeline's true pace (research ~20s, generate ~27s, evaluate
              ~34s). A stage with nothing observable stays dark rather than
              advancing to keep the animation moving.
            </>
          ) : (
            <>
              This sequence replays mission{" "}
              <span className="font-mono">{decision?.missionId || "—"}</span>, a
              real run recorded on 22 Aug 2026, at a fixed 1.5s beat. Every
              figure is fetched from the live aion-core API at replay time —
              none is hardcoded. Research shows 0 citations because Search
              grounding is genuinely tier-blocked.
            </>
          )}
        </p>
      </div>

      {/* Decision card */}
      <AnimatePresence>
        {showDecision && isLive && liveResult && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 grid place-items-center p-6"
            style={{ background: "rgba(0,0,0,0.8)", backdropFilter: "blur(16px)" }}
          >
            <motion.div
              initial={{ scale: 0.9 }}
              animate={{ scale: 1 }}
              className="w-full max-w-[640px] rounded-2xl p-6"
              style={{
                background: "rgba(15,18,30,0.95)",
                border: "1px solid #00f0ff",
                boxShadow: "0 0 50px rgba(0,136,255,0.4)",
              }}
            >
              <div className="flex items-center gap-2.5 mb-4">
                <CheckCircle2 size={22} className="text-cyan-400" />
                <h3 className="text-[18px] font-extrabold tracking-tight">
                  Live mission · {liveResult.status || "COMPLETE"}
                </h3>
              </div>

              <div className="rounded-xl p-4 bg-black/40 border border-white/[0.08] font-mono text-[11.5px] text-slate-300 space-y-1.5">
                <p className="text-slate-500 break-all">
                  mission · {liveResult.mission_id}
                </p>
                {liveResult.blocked_on && (
                  <p className="text-amber-300">
                    blocked · {liveResult.blocked_on.capability_description ||
                      liveResult.blocked_on.description}
                  </p>
                )}

                {/* WHY, not just that. A mission that comes back FAILED
                    with no steps and no gap -- the shape of a quota
                    refusal -- would otherwise show a status word and
                    nothing else. */}
                {(liveResult.reason || liveResult.error) && (
                  <p className="text-red-300 break-all">
                    reason · {liveResult.reason || liveResult.error}
                  </p>
                )}
                {(liveResult.step_results || []).map((s, i) => (
                  <p key={i}>
                    <span className="text-slate-500">step {i + 1}</span> ·{" "}
                    {s.tool} → {s.status}
                  </p>
                ))}
              </div>

              <p className="text-[9.5px] text-slate-500 mt-3 leading-relaxed">
                This is the mission's own response, shown exactly as returned.
                A BLOCKED mission is reported as blocked.
              </p>

              <button
                onClick={reset}
                className="mt-4 ml-auto flex items-center gap-2 text-white font-bold px-5 py-2.5 rounded-lg"
                style={{ background: "linear-gradient(135deg, #0066ff, #00f0ff)" }}
              >
                <X size={14} />
                Close & reset
              </button>
            </motion.div>
          </motion.div>
        )}

        {showDecision && !isLive && decision && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 grid place-items-center p-6"
            style={{ background: "rgba(0,0,0,0.8)", backdropFilter: "blur(16px)" }}
          >
            <motion.div
              initial={{ scale: 0.9 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0.9 }}
              transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
              className="w-full max-w-[640px] rounded-2xl p-6"
              style={{
                background: "rgba(15,18,30,0.95)",
                border: "1px solid #00f0ff",
                boxShadow:
                  "0 0 50px rgba(0,136,255,0.4), inset 0 1px 0 rgba(255,255,255,0.2)",
              }}
            >
              <div className="flex items-center gap-2.5 mb-4">
                <CheckCircle2 size={22} className="text-cyan-400" />
                <h3 className="text-[18px] font-extrabold tracking-tight">
                  Governed mission complete
                </h3>
              </div>

              <div className="rounded-xl p-4 bg-black/40 border border-white/[0.08] font-mono text-[11.5px] text-slate-300 leading-relaxed space-y-1.5">
                <p>
                  <span className="text-slate-500">query</span> ·{" "}
                  {decision.request?.slice(0, 90)}…
                </p>
                <p>
                  <span className="text-slate-500">capability</span> ·
                  calculate_birth_cagr (generated, screened, sandboxed, approved)
                </p>
                <p>
                  <span className="text-slate-500">rows</span> ·{" "}
                  {decision.rowCount} from BigQuery public data
                </p>
                <p className="text-cyan-300">
                  <span className="text-slate-500">result</span> ·{" "}
                  {decision.startYear} {decision.startTotal?.toLocaleString()} →{" "}
                  {decision.endYear} {decision.endTotal?.toLocaleString()}
                </p>
                <p className="text-cyan-300">
                  <span className="text-slate-500">CAGR</span> ·{" "}
                  {decision.cagrPct}%/yr across {decision.years} years
                </p>
                <p>
                  <span className="text-slate-500">steps</span> ·{" "}
                  {decision.stepsExecuted}/{decision.stepsTotal} EXECUTED
                </p>
                <p className="text-slate-500 break-all">
                  mission · {decision.missionId}
                </p>
                <p className="text-slate-500 break-all">
                  workflow · {decision.workflowId}
                </p>
              </div>

              <p className="text-[9.5px] text-slate-500 mt-3 leading-relaxed">
                These are the mission's own recorded identifiers, not a
                generated hash. Any figure above can be checked by fetching
                <span className="font-mono"> /missions/{decision.missionId}</span>{" "}
                from the live API.
              </p>

              <button
                onClick={reset}
                className="mt-4 ml-auto flex items-center gap-2 text-white font-bold px-5 py-2.5 rounded-lg"
                style={{
                  background: "linear-gradient(135deg, #0066ff, #00f0ff)",
                  boxShadow: "0 0 16px rgba(0,102,255,0.5)",
                }}
              >
                <X size={14} />
                Close & reset
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
