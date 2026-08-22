import { useEffect, useRef, useState } from "react";
import { api, hasOwnerToken, setOwnerToken } from "./api.js";

/**
 * The front door. Say what you want, in a sentence.
 *
 * `POST /missions/planned` already did the whole job - plan the request,
 * run it through the gate, block honestly on a capability gap, and hand
 * back the artifact. It simply had no interface, so the only way to reach
 * it was a four-line curl command with two headers and a JSON file, which
 * is four opportunities to make a typo before the agent has done anything
 * at all.
 *
 * Two properties this panel must not lose:
 *
 * 1. The owner token is typed here and held in memory only. See api.js.
 * 2. It shows what actually happened. A mission that BLOCKS on a gap, or
 *    FAILS because a step failed, says so in those words. Rendering every
 *    outcome as a friendly chat reply would hide exactly the behaviour
 *    this project exists to demonstrate.
 *
 * Voice uses the browser's own SpeechRecognition. No Google Cloud speech
 * service, no key, no cost, no new dependency - and typing always works
 * if the microphone does not, because a demo that depends on a mic is a
 * demo with a single point of failure.
 */

const STATUS_TONE = {
  COMPLETED: "text-ok",
  BLOCKED: "text-warn",
  AWAITING_APPROVAL: "text-warn",
  FAILED: "text-danger",
  REFUSED: "text-danger",
};

// Why the mic goes quiet, in words a listener can act on.
//
// The API reports these as bare slugs. "not-allowed" on screen tells the
// operator nothing about which of the two very different fixes to reach
// for -- the browser permission chip, or the OS privacy setting.
const SPEECH_ERRORS = {
  "not-allowed":
    "Microphone blocked. Click the 🔒 icon left of the address bar → " +
    "Microphone → Allow, then reload.",
  "service-not-allowed":
    "The browser refused speech recognition. Chrome sends audio to Google " +
    "to transcribe it; a privacy blocker or managed policy can veto that.",
  network:
    "Speech recognition needs the network and could not reach it. This is " +
    "the browser's transcription service, not aion-core.",
  "no-speech": "Nothing was heard. Click the mic and speak once it turns red.",
  aborted: "Listening was interrupted before anything was transcribed.",
  "audio-capture":
    "No microphone found. Check that one is connected and selected as the " +
    "input device.",
};

function Speech({ onText, onError, busy }) {
  const [listening, setListening] = useState(false);
  const [supported, setSupported] = useState(true);
  const recognition = useRef(null);

  // The callbacks live in refs so the effect below can depend on NOTHING.
  //
  // It used to depend on [onText], and the parent passes an inline arrow --
  // a new function identity on every single render. App.jsx polls the API
  // every 3 seconds and re-renders the tree, so the effect tore itself down
  // and its cleanup called r.abort() about three seconds after the mic was
  // switched on. Every time. A one-word request could sneak through; the
  // demo request is thirty words and never survived.
  //
  // It presented as "the mic isn't listening, I don't know why", which sent
  // the search to microphone permissions and browser settings -- none of
  // which were ever wrong. Recognition must outlive a render, so it is
  // built once and the callbacks are read at fire time.
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

    // Say WHY. Silently dropping the reason is what made this bug cost an
    // evening: a blocked mic and a dead mic looked exactly alike on screen.
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

  if (!supported) return null;

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

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      title={listening ? "Listening — click to stop" : "Speak your request"}
      className={`shrink-0 h-9 w-9 rounded-md border text-[13px] transition-colors ${
        listening
          ? "border-danger text-danger animate-pulse"
          : "border-edge text-muted hover:border-cyan hover:text-cyan"
      } disabled:opacity-40`}
    >
      {listening ? "◉" : "🎙"}
    </button>
  );
}

export default function Command({ onChanged }) {
  const [token, setToken] = useState("");
  const [unlocked, setUnlocked] = useState(hasOwnerToken());
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState([]);

  const add = (entry) => setLog((l) => [entry, ...l].slice(0, 6));

  const unlock = (e) => {
    e.preventDefault();
    if (!token.trim()) return;
    setOwnerToken(token);
    setToken("");           // never keep it in component state either
    setUnlocked(true);
  };

  const send = async (e) => {
    e?.preventDefault();

    const request = text.trim();
    if (!request || busy) return;

    setBusy(true);
    setText("");
    add({ kind: "you", text: request, at: Date.now() });

    try {
      const result = await api.plannedMission(request);
      add({ kind: "axon", result, at: Date.now() });
      onChanged?.();
    } catch (err) {
      add({ kind: "error", text: err.message, at: Date.now() });
    } finally {
      setBusy(false);
    }
  };

  if (!unlocked) {
    return (
      <section className="bg-panel border border-edge rounded-lg p-5">
        <p className="text-[9px] tracking-[0.22em] text-muted">COMMAND</p>
        <h2 className="text-[15px] mt-1">Unlock to give orders</h2>
        <p className="text-[10px] text-muted mt-2 leading-relaxed">
          Reads are public. Anything that changes state — running a mission,
          approving a capability, the kill switch — needs the owner token.
          It is held in memory for this tab only and is gone on refresh; it
          is never written to storage.
        </p>

        <form onSubmit={unlock} className="flex gap-2 mt-3">
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="owner token"
            autoComplete="off"
            className="flex-1 bg-void border border-edge rounded-md px-3 py-2 text-[12px] outline-none focus:border-cyan"
          />
          <button
            type="submit"
            className="px-4 rounded-md border border-cyan text-cyan text-[11px] tracking-[0.12em] hover:bg-cyan/10"
          >
            UNLOCK
          </button>
        </form>
      </section>
    );
  }

  return (
    <section className="bg-panel border border-edge rounded-lg p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[9px] tracking-[0.22em] text-muted">COMMAND</p>
          <h2 className="text-[15px] mt-1">Say what you want.</h2>
        </div>
        <span className="text-[9px] tracking-[0.14em] text-ok">UNLOCKED</span>
      </div>

      <form onSubmit={send} className="flex gap-2 mt-4">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={busy}
          placeholder="Pull the US birth totals from 2005 and brief me"
          className="flex-1 bg-void border border-edge rounded-md px-3 py-2 text-[12px] outline-none focus:border-cyan disabled:opacity-50"
        />
        <Speech
          onText={setText}
          onError={(message) =>
            add({ kind: "error", text: message, at: Date.now() })
          }
          busy={busy}
        />
        <button
          type="submit"
          disabled={busy || !text.trim()}
          className="px-4 rounded-md border border-cyan text-cyan text-[11px] tracking-[0.12em] hover:bg-cyan/10 disabled:opacity-30"
        >
          {busy ? "WORKING" : "SEND"}
        </button>
      </form>

      <p className="text-[8px] text-muted mt-2">
        Planning spends Gemini quota. The free tier allows 20 requests a day.
      </p>

      <div className="mt-4 space-y-3 max-h-[420px] overflow-y-auto scroll-thin">
        {log.map((entry) => (
          <Entry key={entry.at + entry.kind} entry={entry} />
        ))}
      </div>
    </section>
  );
}

function Entry({ entry }) {
  if (entry.kind === "you") {
    return (
      <div className="border-l-2 border-cyan/50 pl-3">
        <p className="text-[8px] tracking-[0.16em] text-muted">YOU</p>
        <p className="text-[12px] mt-0.5">{entry.text}</p>
      </div>
    );
  }

  if (entry.kind === "error") {
    return (
      <div className="border-l-2 border-danger pl-3">
        <p className="text-[8px] tracking-[0.16em] text-danger">FAILED</p>
        <p className="text-[11px] mt-0.5 text-danger">{entry.text}</p>
      </div>
    );
  }

  const r = entry.result || {};
  const status = r.status || "UNKNOWN";
  const tone = STATUS_TONE[status] || "text-muted";
  const steps = r.step_results || [];
  const blocked = r.blocked_on;

  // The artifact, if the mission produced one. Shown as the mission's
  // product rather than buried in the step list, because the product is
  // the point and the capability count is only supporting evidence.
  const brief = steps
    .map((s) => s?.result?.result?.brief || s?.result?.brief)
    .filter(Boolean)
    .pop();

  return (
    <div className="border-l-2 border-edge pl-3">
      <p className={`text-[8px] tracking-[0.16em] ${tone}`}>AXON — {status}</p>

      {r.goal && <p className="text-[11px] mt-1">{r.goal}</p>}

      {steps.length > 0 && (
        <ul className="mt-2 space-y-0.5">
          {steps.map((s) => (
            <li key={s.step} className="text-[10px] text-muted">
              <span className={STATUS_TONE[s.status] || "text-muted"}>
                {s.status === "EXECUTED" ? "✓" : "✕"}
              </span>{" "}
              {s.tool || "no capability"} — {s.description?.slice(0, 70)}
              {s.reason && (
                <span className="text-danger"> — {s.reason.slice(0, 90)}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {blocked && (
        <p className="text-[10px] text-warn mt-2">
          Blocked at step {blocked.step}: {blocked.reason}
          <br />
          <span className="text-muted">
            It needs a capability it does not have. Acquiring one is a
            separate, approved decision.
          </span>
        </p>
      )}

      {brief && (
        <pre className="mt-2 text-[10px] bg-void border border-edge rounded p-3 whitespace-pre-wrap max-h-56 overflow-y-auto scroll-thin">
          {brief}
        </pre>
      )}

      {r.error && (
        <p className="text-[10px] text-danger mt-1">{String(r.error).slice(0, 220)}</p>
      )}
    </div>
  );
}
