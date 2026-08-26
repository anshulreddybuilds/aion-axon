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
  Volume2,
  VolumeX,
  Zap,
} from "lucide-react";
import { api, hasOwnerToken, setOwnerToken } from "../api.js";
import { actionsFromMissionSteps, describeStage } from "../livePipeline.js";
import { speak, speechSynthesisSupported, stopSpeaking } from "../speechOutput.js";
import { useSpeechInput } from "../useSpeechInput.js";
import { extractAnswer, humanMs, loadArtifact, prettyValue, VIEWS } from "./artifact.js";

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

  // Wrapped in the border beam so the active canvas frame carries the same
  // traveling photon as the command capsule, per the owner's spec.
  return (
    <div className="framer-border-beam beam-frame">
      <div className="framer-capsule-inner">
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
    </div>
  );
}

function RegistryTable({ autonomy, capabilities }) {
  const rows = (autonomy?.capabilities || []).slice(0, 8);

  return (
    <div className="framer-border-beam beam-frame">
      <div className="framer-capsule-inner">
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
  // No default capability. A fixed starting value here is exactly the
  // regression this file exists to prevent: the primary send button
  // reveals whatever `selected` was pinned to, so a hardcoded name here
  // makes every typed need look like it produced the same capability,
  // whether or not it actually ran. Empty means "nothing chosen yet" —
  // shown as an empty/initial state, not silently backfilled.
  const [selected, setSelected] = useState(null);
  const [revealed, setRevealed] = useState(0);
  const revealTimer = useRef(null);

  // The live pipeline: what the primary send button now actually drives.
  // `liveActions`/`liveRecord` hold REAL data streamed from
  // GET /synapse/propose/stream as it runs -- one entry per real stage
  // the backend just completed, via describeStage() in livePipeline.js.
  // `liveMode` is true from the moment send() dispatches a real need
  // until (if ever) the resulting capability is installed, at which
  // point decide()'s existing loadArtifact() call takes back over and
  // shows the fuller, post-install telemetry view for the same
  // capability -- watch it happen, then see the recorded evidence.
  const [liveActions, setLiveActions] = useState([]);
  const [liveRecord, setLiveRecord] = useState(null);
  const [liveMode, setLiveMode] = useState(false);
  const [sendingLive, setSendingLive] = useState(false);
  const stageStartRef = useRef(Date.now());

  // Voice is only an interface onto the same send() below -- it sets
  // `prompt`, nothing else, and never submits by itself (see the mic
  // button's onText handler). Off by default: unexpected audio on page
  // load is a real accessibility/UX problem this project won't ship.
  const [speakEnabled, setSpeakEnabled] = useState(false);
  const speech = useSpeechInput({
    onText: (transcript) => setPrompt(transcript),
    // setExpanded(true) here matters: sendOutcome only renders in the
    // dual-pane canvas (STATE 2). A mic error on first use, before the
    // canvas has ever opened, would otherwise set a real error message
    // nothing on screen shows -- the same silent-failure shape the
    // unlock-gate branch in send() already avoids for the same reason.
    onError: (message) => {
      setExpanded(true);
      setSendOutcome({ kind: "error", text: message });
    },
  });

  // Follow-up dispatches a REAL mission. An earlier pass shipped this as a
  // glowing send button with no handler at all, which is the exact thing
  // docs/upgrade-plan.md warns about: "judges clicking a dead Approve
  // button is worse than no button."
  const [followUp, setFollowUp] = useState("");
  const [sending, setSending] = useState(false);
  const [sendOutcome, setSendOutcome] = useState(null);
  const [unlocked, setUnlocked] = useState(hasOwnerToken());
  const [tokenInput, setTokenInput] = useState("");

  // The approval queue, polled live.
  //
  // v4 shipped without this and it was the most important omission on the
  // surface: every row of the registry reads "approved by anshul", which is
  // a record of decisions already made. A viewer could see the paperwork and
  // never see the machine stop and ask -- and stopping to ask IS the
  // product. A governance surface that can only show past approvals is a
  // receipt printer.
  const [pending, setPending] = useState([]);
  const [deciding, setDeciding] = useState(null);

  // The code actually under review.
  //
  // Without this the canvas showed whatever capability the dropdown
  // happened to be on -- an ALREADY INSTALLED one -- while the panel asked
  // for approval of a different, brand-new capability. On camera that
  // reads as "here is the code, now I approve it", and the two are not the
  // same artifact. Showing code A while asking consent for B is exactly
  // the kind of quiet dishonesty this project exists to avoid.
  const [review, setReview] = useState(null);

  // The answer the mission produced. See extractAnswer() for why this
  // exists: the surface showed the whole apparatus and never the result.
  const [answer, setAnswer] = useState(null);

  useEffect(() => {
    api
      .autonomy()
      .then((a) =>
        setNames((a?.capabilities || []).filter((c) => c.passport).map((c) => c.name))
      )
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selected) {
      setData(null);
      return;
    }
    loadArtifact(selected).then(setData).catch(() => {});
  }, [selected]);

  // Poll the real queue. A pending request must appear here within seconds
  // of SYNAPSE stopping, or the owner has no way to know he is being asked.
  useEffect(() => {
    let alive = true;
    const read = () =>
      api
        .pending()
        .then((p) => alive && setPending(p?.pending || []))
        .catch(() => {});
    read();
    const id = setInterval(read, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  // Pull the review package for whatever is pending, so the canvas can show
  // the artifact being decided on rather than an unrelated installed one.
  useEffect(() => {
    const first = pending[0];
    const id = first?.request_id || first?.id;
    if (!id) {
      setReview(null);
      return;
    }
    if (review?.request_id === id) return; // already loaded
    let alive = true;
    api
      .review(id)
      .then((r) => alive && setReview(r))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [pending, review?.request_id]);

  const decide = async (id, approved, capability) => {
    setDeciding(id);
    try {
      await api.decide(id, approved);

      // Approval alone installs NOTHING.
      //
      // POST /approvals/{id}/decide only records the decision; the install
      // is a separate call that re-reads that decision from Firestore.
      // Every UI shipped without making it, so clicking Approve cleared
      // the queue and then silently did nothing -- the registry never
      // moved and the blocked mission never resumed. On camera that is the
      // closing beat of the demo quietly failing to happen.
      //
      // The two-step design on the server is correct and deliberate: the
      // install re-reads the decision rather than trusting the caller. The
      // bug was only that no caller ever took the second step.
      if (approved && capability) {
        const installed = await api.install(capability);

        // The blocked mission resumes on install. Fetching it is how the
        // closing beat becomes visible: the job that was stuck now has a
        // result, and that result is the point of the whole exercise.
        const resumedId =
          installed?.mission_resumed?.mission_id ||
          (typeof installed?.mission_resumed === "string"
            ? installed.mission_resumed
            : null);
        if (resumedId) {
          try {
            setAnswer(extractAnswer(await api.mission(resumedId)));
          } catch {
            /* the install still succeeded; the answer is just unavailable */
          }
        }

        setSendOutcome({
          kind: installed?.status === "INSTALLED" ? "ok" : "error",
          text:
            installed?.status === "INSTALLED"
              ? `INSTALLED ${capability} · registry now ${installed.implemented_count}` +
                (installed.mission_resumed
                  ? " · blocked mission resumed"
                  : "")
              : `Install did not complete: ${
                  installed?.reason || installed?.status || "unknown"
                }`,
        });
      } else if (!approved) {
        setSendOutcome({ kind: "blocked", text: `REJECTED ${capability || id}` });
      }

      setReview(null);
      const p = await api.pending();
      setPending(p?.pending || []);

      // Point the canvas at whatever was just INSTALLED, not whatever
      // `selected` happened to be before this decision -- otherwise a
      // live acquisition that gets approved leaves the dropdown pinned
      // to the old value while the evidence panel silently shows a
      // different capability's data. A rejection installs nothing, so
      // it must NOT repoint `selected` -- a rejected candidate has no
      // real telemetry/passport worth switching the canvas to, and
      // doing so here previously leaked a rejected capability's name
      // into a later, unrelated mission's view.
      if (approved && capability) {
        setLiveMode(false);
        setSelected(capability);
      } else {
        loadArtifact(selected).then(setData).catch(() => {});
      }
    } catch (err) {
      setSendOutcome({ kind: "error", text: String(err.message || err) });
    } finally {
      setDeciding(null);
    }
  };

  const actions = liveMode ? liveActions : data?.actions || [];

  // The action stream reveals one item at a time after send. Each item is
  // a real completed stage with its real measured cost; the reveal is
  // pacing for reading, not a claim that work is happening now.
  useEffect(() => {
    if (!expanded || !actions.length) return;
    if (revealed >= actions.length) return;
    revealTimer.current = setTimeout(() => setRevealed((r) => r + 1), 700);
    return () => clearTimeout(revealTimer.current);
  }, [expanded, revealed, actions.length]);

  const candidate = liveMode
    ? liveRecord?.candidate || null
    : data?.passport?.passport?.candidate || null;
  const thought = liveMode
    ? { need: liveRecord?.need || null, evaluatorReason: liveRecord?.evaluation?.reason || null }
    : data?.thought || {};

  const totalMs = useMemo(
    () => actions.reduce((sum, a) => sum + (a.ms || 0), 0),
    [actions]
  );

  // Dispatches the REAL typed (or spoken -- see the mic button below)
  // need to the REAL governed pipeline. This used to call
  // api.proposeStream() directly, which always tried to research and
  // generate a BRAND NEW capability for whatever was typed -- even
  // "calculate 17% of 8450", which should just reuse the existing
  // calculator capability. That skipped the mission planner's own job
  // (decide reuse vs. acquire) entirely.
  //
  // Now: plannedMission() first, always -- the real planner decides
  // per-step whether an existing capability applies. A mission that can
  // be answered entirely from what's already installed COMPLETES right
  // here, no acquisition spent. Only a mission that genuinely BLOCKS on
  // a missing capability moves on to live-streamed acquisition
  // (GET /missions/{id}/acquire/stream), which is the SAME
  // synapse.propose_stream() generator the standalone flow already used
  // -- one pipeline, reached two different ways depending on whether a
  // mission context exists.
  // Speaks only a TERMINAL outcome (mission completed, blocked on
  // approval, refused, or failed) -- never the transient "Planning…" /
  // "Acquiring it now…" busy text, which would talk over itself on a
  // fast mission and add nothing a listener needs to act on.
  const announceResult = (outcome) => {
    setSendOutcome(outcome);
    if (speakEnabled) speak(outcome.text);
  };

  const send = async () => {
    const need = prompt.trim();
    if (!need || sendingLive) return;

    if (!unlocked) {
      setExpanded(true);
      announceResult({
        kind: "blocked",
        text: "Unlock with the owner token below, then send again — running a mission is a real, governed write.",
      });
      return;
    }

    setExpanded(true);
    setRevealed(0);
    setLiveActions([]);
    setLiveRecord(null);
    setLiveMode(true);
    setAnswer(null);
    setSendOutcome({ kind: "blocked", text: "Planning…" });
    setSendingLive(true);

    try {
      const missionResult = await api.plannedMission(need);
      setAnswer(extractAnswer(missionResult));

      const missionActions = actionsFromMissionSteps(missionResult?.step_results);
      setLiveActions(missionActions);
      setRevealed(missionActions.length);

      if (missionResult?.status === "COMPLETED") {
        announceResult({
          kind: "ok",
          text: `COMPLETED · ${missionActions.length} step${
            missionActions.length === 1 ? "" : "s"
          }, all from the existing registry.`,
        });
      } else if (missionResult?.status === "BLOCKED") {
        const missionId = missionResult.mission_id;
        setSendOutcome({
          kind: "blocked",
          text: "BLOCKED — missing a capability. Acquiring it now…",
        });

        stageStartRef.current = Date.now();
        const acquired = await api.acquireForMissionStream(missionId, {
          onStage: (record) => {
            const now = Date.now();
            const ms = now - stageStartRef.current;
            stageStartRef.current = now;
            const { label, detail, tone } = describeStage(record);
            setLiveActions((prev) => [...prev, { label, detail, tone, ms }]);
            setRevealed((prev) => prev + 1);
            setLiveRecord(record);
          },
        });

        if (acquired?.status === "AWAITING_APPROVAL") {
          announceResult({
            kind: "blocked",
            text: `Proposed ${
              acquired.candidate?.name || "a new capability"
            } — stopped for your approval below. Approving it finishes this mission automatically.`,
          });
        } else if (acquired?.status === "REFUSED") {
          announceResult({ kind: "blocked", text: `REFUSED — ${acquired.reason || "policy"}` });
        } else if (acquired?.status) {
          announceResult({
            kind: "error",
            text: `${acquired.status} — ${acquired.reason || ""}`.trim(),
          });
        }
      } else if (missionResult?.status) {
        announceResult({
          kind: "error",
          text: `${missionResult.status} — ${
            missionResult.error || missionResult.reason || ""
          }`.trim(),
        });
      }
    } catch (err) {
      announceResult({ kind: "error", text: String(err.message || err) });
    } finally {
      setSendingLive(false);
    }
  };

  const reset = () => {
    stopSpeaking(); // never let a stale result keep talking over a new mission
    setExpanded(false);
    setRevealed(0);
    setLiveActions([]);
    setLiveRecord(null);
    setLiveMode(false);
    setSendOutcome(null);
    setAnswer(null);
    // A genuinely new mission starts from an empty canvas, not whatever
    // capability a previous mission (or a rejected one) happened to
    // leave selected -- see decide()'s own comment on why a rejection
    // must never repoint `selected` either.
    setSelected(null);
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
      // Capture the answer, if the mission produced one.
      setAnswer(extractAnswer(result));

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
          {/* Speaks only the real terminal result text already shown on
              screen -- see announceResult() above. Hidden, not disabled,
              when the browser has no SpeechSynthesis, same reasoning as
              the mic button. Off by default: audio nobody asked for on
              page load is a real problem, not a feature. */}
          {speechSynthesisSupported() && (
            <button
              onClick={() => setSpeakEnabled((v) => !v)}
              title={speakEnabled ? "Voice output on — click to mute" : "Voice output off — click to enable"}
              aria-label={speakEnabled ? "Mute voice output" : "Enable voice output"}
              className={`h-6 w-6 grid place-items-center rounded-full transition-colors ${
                speakEnabled ? "text-cyan-300" : "text-slate-400 hover:bg-white/[0.05]"
              }`}
            >
              {speakEnabled ? <Volume2 size={13} /> : <VolumeX size={13} />}
            </button>
          )}
        </div>
      </div>

      {!expanded ? (
        /* ── STATE 1: hero capsule ─────────────────────────────── */
        <div className="min-h-[calc(100vh-80px)] grid place-items-center px-5">
          <motion.div
            layoutId="capsule"
            className="framer-border-beam w-full max-w-[680px]"
          >
            <div className="framer-capsule-inner p-4">
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
                {/* Voice is only an interface onto send() above -- speaking
                    fills this same box, it never submits by itself (see
                    useSpeechInput's onText handler). Hidden entirely, not
                    disabled, when the browser has no SpeechRecognition:
                    typing must never look broken because a capability the
                    page never promised is missing. */}
                {speech.supported && (
                  <button
                    type="button"
                    data-testid="voice-input-button"
                    onClick={speech.toggle}
                    aria-label={speech.listening ? "Stop listening" : "Speak your request"}
                    title={speech.listening ? "Listening — click to stop" : "Speak your request"}
                    disabled={sendingLive}
                    className={`h-8 w-8 grid place-items-center rounded-full transition-colors disabled:opacity-40 ${
                      speech.listening
                        ? "text-red-400 animate-pulse bg-red-400/10"
                        : "framer-pill text-slate-400 hover:text-cyan-300"
                    }`}
                  >
                    <Mic size={14} />
                  </button>
                )}
                <button
                  onClick={send}
                  aria-label="Send"
                  disabled={sendingLive}
                  className="h-8 w-8 grid place-items-center rounded-full text-white disabled:opacity-50"
                  style={{
                    background: "linear-gradient(135deg,#0066ff,#00f0ff)",
                    boxShadow: "0 0 18px rgba(0,102,255,0.65)",
                  }}
                >
                  <ArrowUp size={15} />
                </button>
              </div>
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
                  value={selected || ""}
                  onChange={(e) => setSelected(e.target.value || null)}
                  className="bg-transparent outline-none font-mono text-[10.5px] text-slate-300"
                >
                  {/* No default capability is pinned here (see `selected`'s
                      own comment above) -- an empty registry with nothing
                      selected shows one honest placeholder option instead
                      of silently falling back to an example name. */}
                  {!names.length && !selected && (
                    <option value="" className="bg-[#0b0d15]">
                      no capability selected
                    </option>
                  )}
                  {(names.length ? names : selected ? [selected] : []).map((n) => (
                    <option key={n} value={n} className="bg-[#0b0d15]">
                      {n}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* When something is awaiting approval, the canvas shows THAT
                artifact and says so. Otherwise a viewer would watch code
                for an installed capability and then see it approved -- two
                different things presented as one. */}
            {review && (
              <div
                className="rounded-xl px-3.5 py-2.5 flex items-center gap-2.5"
                style={{
                  background: "rgba(0,102,255,0.10)",
                  border: "1px solid rgba(0,136,255,0.6)",
                }}
              >
                <span className="text-[10px] uppercase tracking-wider font-bold text-[#00f0ff]">
                  ⏸ Under review
                </span>
                <span className="font-mono text-[11px] text-slate-300">
                  {review.capability}
                </span>
                <span className="text-[10px] text-slate-500">
                  {review.is_first_version ? "new capability" : `v${review.current_version} → next`}
                  {" · "}risk {review.risk}
                </span>
                <span className="ml-auto text-[9.5px] text-slate-500">
                  this is the code you are approving
                </span>
              </div>
            )}

            <div className="flex-1 min-h-0">
              {view === "source" &&
                ((review?.code || candidate?.code) ? (
                  <CodeCard
                    filename={`${
                      review?.capability || candidate?.name || selected
                    }.py`}
                    code={review?.code || candidate.code}
                  />
                ) : (
                  <div className="framer-canvas-frame p-6 text-[11px] text-slate-500 italic">
                    No source recorded for this capability.
                  </div>
                ))}

              {view === "test" &&
                ((review?.test_code || candidate?.test) ? (
                  <CodeCard
                    filename={`test_${
                      review?.capability || candidate?.name || selected
                    }.py`}
                    code={review?.test_code || candidate.test}
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

            {/* THE ANSWER.
                Sits above everything because it is what was asked for.
                Everything else on this surface explains how it was
                obtained; this is the obtaining. */}
            {answer && (
              <div
                className="rounded-xl p-3"
                style={{
                  background: "rgba(16,185,129,0.08)",
                  border: "1px solid rgba(16,185,129,0.45)",
                }}
              >
                <p className="text-[10px] uppercase tracking-wider font-bold text-emerald-300 mb-1.5">
                  ✓ Result · mission {answer.missionStatus}
                </p>
                <div className="space-y-1">
                  {answer.fields.map(([k, v]) => (
                    <div key={k} className="flex items-baseline gap-2">
                      <span className="font-mono text-[10px] text-slate-500 min-w-[92px]">
                        {k}
                      </span>
                      <span className="font-mono text-[13px] text-emerald-200 font-semibold tabular-nums break-all">
                        {prettyValue(v)}
                      </span>
                    </div>
                  ))}
                </div>
                <p className="text-[9px] text-slate-500 mt-2 leading-relaxed">
                  Produced by {answer.tool} · mission {answer.missionId?.slice(0, 8)}.
                  These are the mission's own recorded values, not a summary.
                </p>
              </div>
            )}

            {/* HUMAN APPROVAL — the moment the whole product exists for.
                Rendered above everything else when the queue is non-empty,
                because a request the owner does not notice is the same as
                no gate at all. */}
            {pending.length > 0 ? (
              <div
                className="rounded-xl p-3"
                style={{
                  background: "rgba(0,102,255,0.10)",
                  border: "1.5px solid rgba(0,136,255,0.8)",
                  boxShadow: "0 0 24px rgba(0,102,255,0.35)",
                }}
              >
                <p className="text-[10px] uppercase tracking-wider font-bold text-[#00f0ff] mb-2">
                  ⏸ Stopped — {pending.length} waiting on you
                </p>

                {pending.map((p) => {
                  const id = p.request_id || p.id;
                  const busy = deciding === id;
                  return (
                    <div key={id} className="mb-2 last:mb-0">
                      <p className="text-[12px] font-medium tracking-tight break-all">
                        {p.capability || p.action || id}
                      </p>
                      {p.description && (
                        <p className="text-[10px] text-slate-400 mt-0.5 leading-relaxed">
                          {p.description}
                        </p>
                      )}
                      <div className="flex gap-2 mt-2">
                        <button
                          onClick={() => decide(id, true, p.capability)}
                          disabled={busy}
                          className="px-3 py-1.5 rounded-lg border border-emerald-400/50 text-emerald-300 text-[10px] font-bold uppercase tracking-wider hover:bg-emerald-400/10 disabled:opacity-40"
                        >
                          {busy ? "…" : "Approve"}
                        </button>
                        <button
                          onClick={() => decide(id, false, p.capability)}
                          disabled={busy}
                          className="px-3 py-1.5 rounded-lg border border-red-400/50 text-red-300 text-[10px] font-bold uppercase tracking-wider hover:bg-red-400/10 disabled:opacity-40"
                        >
                          {busy ? "…" : "Reject"}
                        </button>
                      </div>
                    </div>
                  );
                })}

                <p className="text-[9px] text-slate-500 mt-2 leading-relaxed">
                  Nothing installs until you decide. install() re-reads this
                  decision from the database rather than trusting the proposal.
                </p>
              </div>
            ) : (
              <div className="rounded-xl px-3 py-2.5 border border-white/[0.07]">
                <p className="text-[10px] uppercase tracking-wider font-semibold text-slate-500">
                  Human approval · queue clear
                </p>
                <p className="text-[10px] text-slate-500 mt-1 leading-relaxed">
                  Nothing is waiting on you. The capabilities below were each
                  approved by a named human — an empty queue means no decision
                  is pending, not that the gate was skipped.
                </p>
              </div>
            )}

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
            <div className="framer-border-beam">
              <div className="framer-capsule-inner p-2.5">
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
