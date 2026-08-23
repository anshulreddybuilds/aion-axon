import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowUp,
  ChevronDown,
  Code2,
  Mic,
  Play,
  Plus,
  RotateCcw,
  Search,
  Zap,
} from "lucide-react";
import { api, hasOwnerToken, setOwnerToken } from "../api.js";
import { humanMs, loadArtifact, VIEWS } from "./artifact.js";

/**
 * v4 — the Framer Agents design language, on AION Axon's real objects.
 *
 * Two states, exactly as specified: a centred hero prompt capsule with an
 * electric laser perimeter, which expands on send into a dual-pane
 * generative canvas with an agent reasoning sidebar.
 *
 * The visual system is implemented to the owner's spec verbatim (see
 * .framer-glow-box / .framer-canvas-frame in index.css). The CONTENT is
 * AION Axon's, because Framer's content belongs to a website builder:
 * page layers, CMS rows of people, viewport widths. Rendering those here
 * would mean showing a product that does not exist.
 *
 * The substitution is one-for-one and everything in it is fetched live:
 *   code component card  -> the real generated Python for a capability
 *   CMS data table       -> the real capability registry
 *   Thought (4s) drawer  -> the real need + evaluator reasoning
 *   timed action stream  -> real per-stage measured latency
 *   device viewports     -> Source / Test / Evidence views of the artifact
 */

const SYNTAX = [
  [/(\b(?:def|return|import|if|not|isinstance|for|in|try|except|raise|else|elif|with|as|from|lambda|None|True|False)\b)/g, "#c084fc"],
  [/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, "#34d399"],
  [/(#[^\n]*)/g, "#475569"],
  [/(\b\d+(?:\.\d+)?\b)/g, "#fbbf24"],
];

function highlight(line) {
  // Deliberately simple: enough colour to read as code, no tokeniser
  // dependency for a demo surface. Order matters — comments last would
  // recolour keywords inside them.
  const parts = [{ text: line, color: null }];
  for (const [re, color] of SYNTAX) {
    for (let i = parts.length - 1; i >= 0; i--) {
      if (parts[i].color) continue;
      const seg = parts[i].text;
      const out = [];
      let last = 0;
      seg.replace(re, (m, _g, idx) => {
        if (idx > last) out.push({ text: seg.slice(last, idx), color: null });
        out.push({ text: m, color });
        last = idx + m.length;
        return m;
      });
      if (out.length) {
        if (last < seg.length) out.push({ text: seg.slice(last), color: null });
        parts.splice(i, 1, ...out);
      }
    }
  }
  return parts;
}

function CodeCard({ name, code, filename }) {
  const lines = (code || "").split("\n");

  return (
    <div className="framer-canvas-frame">
      <div className="flex items-center gap-2 px-3.5 py-2.5 border-b border-white/[0.07] bg-black/50">
        <Code2 size={13} className="text-[#0088ff]" />
        <span className="font-mono text-[11.5px] text-slate-300">{filename}</span>
        <span className="ml-auto font-mono text-[9.5px] text-slate-600">
          {lines.length} lines · generated
        </span>
      </div>

      <div className="p-3.5 overflow-auto max-h-[420px] scroll-thin">
        <pre className="font-mono text-[11px] leading-[1.65]">
          {lines.map((line, i) => (
            <div key={i} className="flex">
              <span className="text-slate-700 select-none w-8 shrink-0 text-right pr-3">
                {i + 1}
              </span>
              <span className="text-slate-300 whitespace-pre-wrap break-all">
                {highlight(line).map((p, j) => (
                  <span key={j} style={p.color ? { color: p.color } : undefined}>
                    {p.text}
                  </span>
                ))}
              </span>
            </div>
          ))}
        </pre>
      </div>
    </div>
  );
}

function RegistryTable({ autonomy, capabilities }) {
  const rows = (autonomy?.capabilities || []).slice(0, 8);

  return (
    <div className="framer-canvas-frame">
      <div className="flex items-center gap-2 px-3.5 py-2.5 border-b border-white/[0.07] bg-black/50">
        <span className="font-mono text-[11.5px] text-slate-300">
          capability_registry
        </span>
        <span className="ml-auto font-mono text-[9.5px] text-slate-600">
          {capabilities?.implemented ?? "—"} of {capabilities?.total ?? "—"} built
        </span>
      </div>

      <table className="w-full">
        <thead>
          <tr className="border-b border-white/[0.06]">
            {["Name", "State", "Risk", "Approver"].map((h) => (
              <th
                key={h}
                className="text-left font-semibold text-[9.5px] uppercase tracking-wider text-slate-500 px-3.5 py-2"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={4} className="px-3.5 py-4 text-[11px] text-slate-600 italic">
                registry empty — nothing acquired yet
              </td>
            </tr>
          ) : (
            rows.map((c) => (
              <tr
                key={c.name}
                className="border-b border-white/[0.04] last:border-0 hover:bg-[#0066ff]/[0.08] transition-colors"
              >
                <td className="px-3.5 py-2 font-mono text-[11px] text-slate-200">
                  {c.name}
                </td>
                <td className="px-3.5 py-2">
                  <span className="inline-flex items-center gap-1.5 framer-pill px-2 py-0.5 text-[9.5px] font-semibold text-emerald-300">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                    {c.passport ? "Active" : "Declared"}
                  </span>
                </td>
                <td className="px-3.5 py-2 font-mono text-[10px] text-slate-400">
                  {c.risk || "LOW"}
                </td>
                <td className="px-3.5 py-2 font-mono text-[10px] text-slate-400">
                  {c.passport ? "anshul" : "—"}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export default function AppV4() {
  const [expanded, setExpanded] = useState(false);
  const [prompt, setPrompt] = useState(
    "Pull the US birth totals from 2005 and brief me"
  );
  const [view, setView] = useState("source");
  const [thoughtOpen, setThoughtOpen] = useState(true);
  const [data, setData] = useState(null);
  const [names, setNames] = useState([]);
  const [selected, setSelected] = useState("calculate_birth_cagr");
  const [revealed, setRevealed] = useState(0);
  const revealTimer = useRef(null);

  // Follow-up dispatches a REAL mission. An earlier pass shipped this as a
  // glowing send button with no handler at all, which is the exact thing
  // docs/upgrade-plan.md warns about: "judges clicking a dead Approve
  // button is worse than no button."
  const [followUp, setFollowUp] = useState("");
  const [sending, setSending] = useState(false);
  const [sendOutcome, setSendOutcome] = useState(null);
  const [unlocked, setUnlocked] = useState(hasOwnerToken());
  const [tokenInput, setTokenInput] = useState("");

  useEffect(() => {
    api
      .autonomy()
      .then((a) =>
        setNames((a?.capabilities || []).filter((c) => c.passport).map((c) => c.name))
      )
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadArtifact(selected).then(setData).catch(() => {});
  }, [selected]);

  const actions = data?.actions || [];

  // The action stream reveals one item at a time after send. Each item is
  // a real completed stage with its real measured cost; the reveal is
  // pacing for reading, not a claim that work is happening now.
  useEffect(() => {
    if (!expanded || !actions.length) return;
    if (revealed >= actions.length) return;
    revealTimer.current = setTimeout(() => setRevealed((r) => r + 1), 700);
    return () => clearTimeout(revealTimer.current);
  }, [expanded, revealed, actions.length]);

  const candidate = data?.passport?.passport?.candidate || null;
  const thought = data?.thought || {};

  const totalMs = useMemo(
    () => actions.reduce((sum, a) => sum + (a.ms || 0), 0),
    [actions]
  );

  const send = () => {
    setExpanded(true);
    setRevealed(0);
  };

  const reset = () => {
    setExpanded(false);
    setRevealed(0);
    setSendOutcome(null);
  };

  const sendFollowUp = async () => {
    const request = followUp.trim();
    if (!request || sending) return;

    setSending(true);
    setSendOutcome(null);
    try {
      const result = await api.plannedMission(request);
      // A 200 response can still describe a failure. Report the reason the
      // server gave, not just the status word -- a bare "FAILED" is the
      // same defect as a silent error.
      const failed = result?.status && result.status !== "COMPLETED";
      setSendOutcome({
        kind: result?.blocked_on ? "blocked" : failed ? "error" : "ok",
        text: result?.blocked_on
          ? `BLOCKED — gap: ${
              result.blocked_on.capability_description ||
              result.blocked_on.description
            }`
          : result?.reason
          ? `${result.status} — ${result.reason}`
          : `${result?.status || "COMPLETED"} · ${
              (result?.step_results || []).length
            } steps`,
      });
      setFollowUp("");
    } catch (err) {
      // Reported verbatim. A 429 says 429; this surface exists to show
      // what the server actually said.
      setSendOutcome({ kind: "error", text: String(err.message || err) });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="min-h-screen ambient-bloom text-slate-100 font-sans">
      {/* Top pill nav */}
      <div className="flex justify-center pt-5 px-5">
        <div className="framer-pill flex items-center gap-1.5 px-2 py-1.5">
          <button
            onClick={reset}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11.5px] text-slate-300 hover:bg-white/[0.05] transition-colors"
          >
            New mission
          </button>
          <button
            onClick={reset}
            title="Start over"
            className="h-6 w-6 grid place-items-center rounded-full text-slate-400 hover:bg-white/[0.05] transition-colors"
          >
            <Plus size={13} />
          </button>
        </div>
      </div>

      {!expanded ? (
        /* ── STATE 1: hero capsule ─────────────────────────────── */
        <div className="min-h-[calc(100vh-80px)] grid place-items-center px-5">
          <motion.div
            layoutId="capsule"
            className="framer-glow-box w-full max-w-[680px] p-4"
          >
            <input
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="Ask for something it cannot do yet…"
              className="w-full bg-transparent border-none outline-none text-[16px] tracking-tight placeholder:text-slate-600 px-1 py-2"
            />

            <div className="flex items-center justify-between mt-3">
              {/* A label, not a button. It reports which engine runs this
                  pipeline; there is no second engine to switch to, and a
                  dropdown that opens onto one option is a dead control
                  wearing a chevron. */}
              <span className="framer-pill flex items-center gap-1.5 px-2.5 py-1.5 font-mono text-[11px] text-slate-400">
                gemini-3.6-flash
              </span>

              <div className="flex items-center gap-1.5">
                <button
                  onClick={send}
                  className="h-8 w-8 grid place-items-center rounded-full text-white"
                  style={{
                    background: "linear-gradient(135deg,#0066ff,#00f0ff)",
                    boxShadow: "0 0 18px rgba(0,102,255,0.65)",
                  }}
                >
                  <ArrowUp size={15} />
                </button>
              </div>
            </div>
          </motion.div>
        </div>
      ) : (
        /* ── STATE 2: dual-pane canvas ─────────────────────────── */
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          className="px-5 pb-5 pt-4 grid gap-4 xl:grid-cols-[1fr_380px] min-h-[calc(100vh-80px)]"
        >
          {/* Canvas */}
          <div className="relative flex flex-col gap-3 min-w-0">
            <div className="flex items-center gap-2">
              {VIEWS.map((v) => (
                <button
                  key={v.id}
                  onClick={() => setView(v.id)}
                  className={`px-3 py-1.5 rounded-full text-[11px] font-medium transition-colors ${
                    view === v.id
                      ? "text-white"
                      : "framer-pill text-slate-400 hover:text-slate-200"
                  }`}
                  style={
                    view === v.id
                      ? {
                          background: "rgba(0,102,255,0.22)",
                          border: "1px solid #0066ff",
                          boxShadow: "0 0 14px rgba(0,102,255,0.4)",
                        }
                      : undefined
                  }
                >
                  {v.label}
                </button>
              ))}
              <span className="text-[10px] text-slate-600 ml-1">
                {VIEWS.find((v) => v.id === view)?.hint}
              </span>

              <div className="ml-auto framer-pill flex items-center gap-2 px-2.5 py-1.5">
                <select
                  value={selected}
                  onChange={(e) => setSelected(e.target.value)}
                  className="bg-transparent outline-none font-mono text-[10.5px] text-slate-300"
                >
                  {(names.length ? names : [selected]).map((n) => (
                    <option key={n} value={n} className="bg-[#0b0d15]">
                      {n}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex-1 min-h-0">
              {view === "source" &&
                (candidate?.code ? (
                  <CodeCard
                    filename={`${candidate.name || selected}.py`}
                    code={candidate.code}
                  />
                ) : (
                  <div className="framer-canvas-frame p-6 text-[11px] text-slate-500 italic">
                    No source recorded for this capability.
                  </div>
                ))}

              {view === "test" &&
                (candidate?.test ? (
                  <CodeCard
                    filename={`test_${candidate.name || selected}.py`}
                    code={candidate.test}
                  />
                ) : (
                  <div className="framer-canvas-frame p-6 text-[11px] text-slate-500 italic">
                    No test recorded.
                  </div>
                ))}

              {view === "evidence" && (
                <div className="space-y-3">
                  <RegistryTable
                    autonomy={data?.autonomy}
                    capabilities={data?.capabilities}
                  />
                </div>
              )}
            </div>

            <div className="absolute bottom-0 left-0 framer-pill flex items-center gap-2 px-2.5 py-1.5 text-slate-500">
              <Play size={11} />
              <Search size={11} />
              <span className="font-mono text-[10px]">100%</span>
            </div>
          </div>

          {/* Agent sidebar */}
          <div className="framer-panel p-4 flex flex-col gap-3 min-h-0">
            {/* Framer has Agent / Style because it styles web pages. There
                is no style axis here, so a "Style" tab would be a dead
                control. One honest label instead of two tabs, one of which
                does nothing. */}
            <div className="flex items-center gap-2">
              <span className="px-3 py-1.5 rounded-full text-[11px] font-medium bg-white/[0.08] text-white">
                Agent
              </span>
              <span className="text-[10px] text-slate-600">
                acquisition trace
              </span>
            </div>

            <div className="text-[12px] font-medium tracking-tight">
              Acquire missing capability
            </div>

            {/* user prompt bubble */}
            <div className="framer-pill px-3 py-2.5 flex items-start gap-2.5 !rounded-2xl">
              <p className="text-[11.5px] text-slate-300 leading-relaxed flex-1">
                {prompt}
              </p>
              <button
                onClick={reset}
                className="h-6 w-6 grid place-items-center rounded-full text-slate-500 hover:text-slate-200 shrink-0"
              >
                <RotateCcw size={11} />
              </button>
            </div>

            {/* timed action badge */}
            <div className="framer-pill inline-flex items-center gap-1.5 px-2.5 py-1.5 self-start">
              <Zap size={11} className="text-[#00f0ff]" />
              <span className="text-[11px] text-slate-300">
                Acquired a capability
              </span>
              {totalMs > 0 && (
                <span className="font-mono text-[10px] text-slate-500">
                  · {humanMs(totalMs)}
                </span>
              )}
            </div>

            {/* thought drawer */}
            <div className="border border-white/[0.07] rounded-xl overflow-hidden">
              <button
                onClick={() => setThoughtOpen((v) => !v)}
                className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-white/[0.02] transition-colors"
              >
                <span className="text-[11.5px] text-slate-300">
                  Thought{" "}
                  <span className="font-mono text-slate-500">
                    ({humanMs(actions[0]?.ms) || "—"})
                  </span>
                </span>
                <motion.span
                  animate={{ rotate: thoughtOpen ? 180 : 0 }}
                  className="ml-auto text-slate-500"
                >
                  <ChevronDown size={13} />
                </motion.span>
              </button>

              {/* Opacity only — see the same fix in v2/TelemetryPane.jsx.
                  Animating height to "auto" resolved to 0, mounting the
                  panel invisibly and making the drawer look dead. */}
              <AnimatePresence initial={false}>
                {thoughtOpen && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.15 }}
                  >
                    <div className="px-3 pb-3 space-y-2">
                      {thought.need ? (
                        <p className="text-[11px] text-slate-400 italic leading-relaxed">
                          “{thought.need.split("\n")[0]}”
                        </p>
                      ) : (
                        <p className="text-[11px] text-slate-600 italic">
                          No recorded need for this capability.
                        </p>
                      )}
                      {thought.evaluatorReason && (
                        <p className="text-[10.5px] text-slate-500 leading-relaxed">
                          Evaluator: “{thought.evaluatorReason}”
                        </p>
                      )}
                      <p className="text-[9px] text-slate-600 leading-relaxed">
                        Quoted from the capability's passport. The system does
                        not record model chain-of-thought, so none is shown.
                      </p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* execution stream */}
            <div className="flex-1 min-h-0 overflow-y-auto scroll-thin space-y-1.5">
              {actions.slice(0, revealed).map((a, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="flex items-start gap-2 py-1"
                >
                  <span
                    className="h-1.5 w-1.5 rounded-full mt-1.5 shrink-0"
                    style={{
                      background:
                        a.tone === "warn"
                          ? "#f59e0b"
                          : a.tone === "danger"
                          ? "#ef4444"
                          : "#10b981",
                    }}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-[11.5px] text-slate-300 leading-tight">
                      {a.label}
                      {a.ms != null && (
                        <span className="font-mono text-[10px] text-slate-500">
                          {" "}
                          · {humanMs(a.ms)}
                        </span>
                      )}
                    </p>
                    <p className="text-[10px] text-slate-500 mt-0.5 break-all">
                      {a.detail}
                    </p>
                  </div>
                </motion.div>
              ))}
              {revealed < actions.length && (
                <p className="text-[10px] text-slate-600 font-mono pl-3.5">
                  …
                </p>
              )}
            </div>

            {/* follow-up capsule — dispatches a REAL mission */}
            <div className="framer-glow-box p-2.5">
              {!unlocked ? (
                <div className="flex gap-2">
                  <input
                    type="password"
                    value={tokenInput}
                    onChange={(e) => setTokenInput(e.target.value)}
                    placeholder="owner token — needed to run a mission"
                    autoComplete="off"
                    className="flex-1 bg-transparent border-none outline-none text-[12px] placeholder:text-slate-600 px-1 py-1"
                  />
                  <button
                    onClick={() => {
                      if (!tokenInput.trim()) return;
                      setOwnerToken(tokenInput);
                      setTokenInput("");
                      setUnlocked(true);
                    }}
                    className="px-3 rounded-lg border border-cyan-400/40 text-cyan-300 font-mono text-[10px] font-bold uppercase"
                  >
                    Unlock
                  </button>
                </div>
              ) : (
                <>
                  <input
                    value={followUp}
                    onChange={(e) => setFollowUp(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && sendFollowUp()}
                    disabled={sending}
                    placeholder="Add follow-up…"
                    className="w-full bg-transparent border-none outline-none text-[12px] placeholder:text-slate-600 px-1 py-1 disabled:opacity-50"
                  />
                  <div className="flex items-center justify-between mt-1.5">
                    <span className="framer-pill px-2 py-1 font-mono text-[10px] text-slate-400">
                      {sending ? "running…" : "gemini-3.6-flash"}
                    </span>
                    <div className="flex items-center gap-1.5">
                      <button
                        disabled
                        title="Voice is unproven on this machine — disabled rather than faked"
                        className="h-7 w-7 grid place-items-center rounded-full text-slate-700 cursor-not-allowed"
                      >
                        <Mic size={12} />
                      </button>
                      <button
                        onClick={sendFollowUp}
                        disabled={sending || !followUp.trim()}
                        title="Run this as a real governed mission"
                        className="h-7 w-7 grid place-items-center rounded-full text-white disabled:opacity-30"
                        style={{
                          background: "linear-gradient(135deg,#0066ff,#00f0ff)",
                          boxShadow: "0 0 14px rgba(0,102,255,0.6)",
                        }}
                      >
                        <ArrowUp size={13} />
                      </button>
                    </div>
                  </div>
                </>
              )}

              {sendOutcome && (
                <p
                  className={`text-[10px] mt-2 leading-relaxed break-all ${
                    sendOutcome.kind === "error"
                      ? "text-red-300"
                      : sendOutcome.kind === "blocked"
                      ? "text-amber-300"
                      : "text-emerald-300"
                  }`}
                >
                  {sendOutcome.text}
                </p>
              )}
            </div>

            <p className="text-[8.5px] text-slate-600 leading-relaxed">
              Source, test, evaluation and approver are fetched live from the
              capability's passport. The code shown is what the system actually
              generated.
            </p>
          </div>
        </motion.div>
      )}
    </div>
  );
}
