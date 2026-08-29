import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ArrowUp, ChevronDown, Cpu, Mic, Square } from "lucide-react";
import { api, hasOwnerToken, setOwnerToken } from "../api.js";
import { Card, MicroLabel, Pill, SessionBar } from "./Shell2.jsx";

/**
 * The central command capsule.
 *
 * Carries over, unchanged, the two properties the v1 Command panel earned
 * the hard way:
 *
 *   1. The owner token lives in a module variable in api.js and NOWHERE
 *      else — not localStorage, not sessionStorage, not a cookie, not the
 *      URL. It dies with the tab. That is the right trade for a token that
 *      can approve installs and trip the kill switch.
 *   2. Speech recognition is built ONCE and its callbacks are read from
 *      refs. It used to depend on a callback prop identity, and since the
 *      dashboard re-renders on every poll, the effect tore itself down and
 *      aborted the mic mid-sentence. Errors are surfaced with the reason,
 *      never swallowed.
 */

// Both stages run gemini-3.5-flash today. The evaluator used to run a
// Gemma model (gemma-3-27b-it, then gemma-4-26b-a4b-it), but both 404'd
// in production on 2026-08-29 -- see app/synapse/evaluator.py's own
// history comment -- so it now falls back to the same model as the
// generator. Keeping `id` in sync with generator.py's and evaluator.py's
// real MODEL env-var defaults is the whole point of this list existing;
// a stale id here just lies to the person picking an engine. `key` is
// separate from `id` on purpose -- now that both stages share one real
// model, `id` alone can't tell the two rows apart for React keys or for
// tracking which one is selected.
const MODELS = [
  { key: "generator", id: "gemini-3.5-flash", role: "planner · generator · research" },
  { key: "evaluator", id: "gemini-3.5-flash", role: "evaluator — second opinion" },
];

const SPEECH_ERRORS = {
  "not-allowed":
    "Microphone blocked. Click the icon left of the address bar → Microphone → Allow, then reload.",
  "service-not-allowed":
    "The browser refused speech recognition. Chrome sends audio to Google to transcribe it; a privacy blocker or managed policy can veto that.",
  network:
    "Speech recognition needs the network and could not reach it. This is the browser's transcription service, not aion-core.",
  "no-speech": "Nothing was heard. Click the mic and speak once it turns red.",
  aborted: "Listening was interrupted before anything was transcribed.",
  "audio-capture":
    "No microphone found. Check that one is connected and selected as the input device.",
};

function useSpeech({ onText, onError }) {
  const [listening, setListening] = useState(false);
  const [supported, setSupported] = useState(true);
  const recognition = useRef(null);

  const onTextRef = useRef(onText);
  const onErrorRef = useRef(onError);
  onTextRef.current = onText;
  onErrorRef.current = onError;

  useEffect(() => {
    const Impl =
      window.SpeechRecognition || window.webkitSpeechRecognition || null;

    if (!Impl) {
      setSupported(false);
      return;
    }

    const r = new Impl();
    r.lang = "en-US";
    r.interimResults = false;
    r.maxAlternatives = 1;

    r.onresult = (event) =>
      onTextRef.current?.(event.results[0][0].transcript);

    r.onerror = (event) => {
      setListening(false);
      const code = event?.error || "unknown";
      onErrorRef.current?.(
        SPEECH_ERRORS[code] || `Speech input failed (${code}).`
      );
    };

    r.onend = () => setListening(false);
    recognition.current = r;

    return () => {
      try {
        r.abort();
      } catch {
        /* already stopped */
      }
    };
  }, []);

  const toggle = () => {
    if (listening) {
      recognition.current?.stop();
      setListening(false);
      return;
    }
    try {
      recognition.current?.start();
      setListening(true);
    } catch {
      setListening(false);
    }
  };

  return { listening, supported, toggle };
}

export default function CommandCapsule({ onChanged, onLog, unlocked, onUnlock }) {
  const [token, setToken] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [focused, setFocused] = useState(false);
  const [modelKey, setModelKey] = useState(MODELS[0].key);
  const [modelOpen, setModelOpen] = useState(false);

  const { listening, supported, toggle } = useSpeech({
    onText: setText,
    onError: (message) => onLog?.({ kind: "error", text: message }),
  });

  const unlock = (e) => {
    e.preventDefault();
    if (!token.trim()) return;
    setOwnerToken(token);
    setToken("");
    onUnlock?.();
  };

  const send = async (e) => {
    e?.preventDefault();
    const request = text.trim();
    if (!request || busy) return;

    setBusy(true);
    setText("");
    onLog?.({ kind: "you", text: request });

    try {
      const result = await api.plannedMission(request);
      onLog?.({ kind: "axon", result });
      onChanged?.();
    } catch (err) {
      onLog?.({ kind: "error", text: err.message });
    } finally {
      setBusy(false);
    }
  };

  if (!unlocked) {
    return (
      <Card className="p-5">
        <MicroLabel>Command</MicroLabel>
        <h2 className="text-[15px] font-semibold tracking-tight mt-1.5">
          Unlock to give orders
        </h2>
        <p className="text-[11px] text-zinc-500 mt-2 leading-relaxed max-w-xl">
          Reads are public. Anything that changes state — running a mission,
          approving a capability, the kill switch — needs the owner token. It
          is held in memory for this tab only and is gone on refresh; it is
          never written to storage.
        </p>
        <form onSubmit={unlock} className="flex gap-2 mt-4">
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="owner token"
            autoComplete="off"
            className="flex-1 bg-obsidian/60 border border-white/[0.08] rounded-xl px-3.5 py-2.5 text-[12px] outline-none focus:border-cobalt/50 transition-colors"
          />
          <button
            type="submit"
            className="px-5 rounded-xl border border-cobalt/40 text-electric text-[10px] tracking-wider uppercase font-semibold hover:bg-cobalt/10 transition-colors"
          >
            Unlock
          </button>
        </form>
      </Card>
    );
  }

  const active = focused || listening;

  return (
    <div>
      <SessionBar sessionLabel="Session #01" />

      <motion.div
        animate={{ scale: active ? 1.004 : 1 }}
        transition={{ duration: 0.2 }}
        className={`glass glass-spec rounded-2xl p-4 transition-shadow duration-300 ${
          active ? "neon" : ""
        }`}
      >
        <form onSubmit={send}>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) send(e);
            }}
            disabled={busy}
            rows={3}
            placeholder="Ask for something it cannot do yet…"
            className="w-full bg-transparent resize-none outline-none text-[14px] leading-relaxed tracking-tight placeholder:text-zinc-600 disabled:opacity-50"
          />

          <div className="flex items-center gap-2 mt-3">
            <div className="relative">
              <button
                type="button"
                onClick={() => setModelOpen((v) => !v)}
                className="glass rounded-full pl-2.5 pr-2 py-1.5 flex items-center gap-1.5 text-[10px] tracking-wider uppercase font-semibold text-zinc-300 hover:border-cobalt/40 transition-colors"
              >
                <Cpu size={11} className="text-electric" />
                {MODELS.find((m) => m.key === modelKey)?.id ?? MODELS[0].id}
                <ChevronDown size={11} className="text-zinc-500" />
              </button>

              {modelOpen && (
                <div className="absolute bottom-full mb-2 left-0 glass rounded-xl p-1.5 w-[280px] z-20">
                  {MODELS.map((m) => (
                    <button
                      key={m.key}
                      type="button"
                      onClick={() => {
                        setModelKey(m.key);
                        setModelOpen(false);
                      }}
                      className={`w-full text-left rounded-lg px-2.5 py-2 hover:bg-white/[0.04] transition-colors ${
                        modelKey === m.key ? "bg-cobalt/10" : ""
                      }`}
                    >
                      <p className="text-[11px] font-medium tracking-tight">
                        {m.id}
                      </p>
                      <p className="text-[9px] text-zinc-500 mt-0.5">{m.role}</p>
                    </button>
                  ))}
                  <p className="text-[9px] text-zinc-600 px-2.5 py-1.5 leading-relaxed border-t border-white/[0.06] mt-1">
                    Both are already wired server-side. Selecting here does not
                    reroute the pipeline — it names which engine runs which
                    stage.
                  </p>
                </div>
              )}
            </div>

            <div className="ml-auto flex items-center gap-2">
              {supported && (
                <button
                  type="button"
                  onClick={toggle}
                  disabled={busy}
                  title={listening ? "Listening — click to stop" : "Speak your request"}
                  className={`h-9 w-9 grid place-items-center rounded-full border transition-colors disabled:opacity-40 ${
                    listening
                      ? "mic-live border-red-400/60 text-red-300"
                      : "border-white/[0.08] text-zinc-400 hover:text-electric hover:border-cobalt/40"
                  }`}
                >
                  {listening ? <Square size={12} /> : <Mic size={14} />}
                </button>
              )}

              <button
                type="submit"
                disabled={busy || !text.trim()}
                className={`h-9 w-9 grid place-items-center rounded-full border transition-all disabled:opacity-25 ${
                  text.trim() && !busy
                    ? "neon border-cobalt/50 text-electric"
                    : "border-white/[0.08] text-zinc-500"
                }`}
              >
                <ArrowUp size={15} />
              </button>
            </div>
          </div>
        </form>
      </motion.div>

      <div className="flex items-center gap-2 mt-2.5">
        <Pill tone="warn">Planning spends real Gemini quota</Pill>
        {listening && <Pill tone="danger">Listening</Pill>}
      </div>
    </div>
  );
}
