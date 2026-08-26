/**
 * Shared, framework-agnostic core for browser-native speech recognition.
 *
 * Ported from web/src/Command.jsx's <Speech> component, where two real
 * bugs were found and fixed live against the deployed app: recognition
 * not surviving a re-render (the parent's onText/onError callbacks must
 * be read via refs at fire time, not captured as an effect dependency --
 * a polling parent re-renders the tree every few seconds, and depending
 * on [onText] tore recognition down seconds after every start(), letting
 * only a one-word request sneak through before cleanup aborted it), and
 * dropping the real error code instead of surfacing it (a blocked mic
 * and a dead mic looked identical on screen). Neither bug is re-derived
 * here -- this file is the one place the core logic lives now, reused
 * by any component that wants a mic button (see useSpeechInput.js for
 * the React-hook wrapper AppV4.jsx uses).
 *
 * Browser-native SpeechRecognition only: no Google Cloud speech service,
 * no API key, no per-call cost, no new dependency. Typing always still
 * works if the microphone or the browser's transcription service does
 * not -- a mission entry point that depends on a mic is a single point
 * of failure this project deliberately does not accept.
 */

// Why the mic goes quiet, in words a listener can act on.
//
// The Web Speech API reports these as bare slugs. "not-allowed" on
// screen tells the operator nothing about which of two very different
// fixes to reach for -- the browser permission chip, or the OS privacy
// setting.
export const SPEECH_ERRORS = {
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

export function messageForSpeechError(code) {
  return SPEECH_ERRORS[code] || `Speech input failed (${code || "unknown"}).`;
}

export function speechRecognitionSupported(win = globalThis) {
  return Boolean(win && (win.SpeechRecognition || win.webkitSpeechRecognition));
}

/**
 * Build one configured SpeechRecognition instance and wire it to
 * `handlers` (an object read live, not closed over at build time, so a
 * caller can mutate handlers.onText/handlers.onError across renders
 * without rebuilding the recognizer). Returns null when the browser has
 * no implementation at all -- callers must treat that as "hide the mic
 * button", never as "fall back to something that isn't real".
 */
export function createRecognizer(handlers, win = globalThis) {
  const Impl =
    (win && (win.SpeechRecognition || win.webkitSpeechRecognition)) || null;

  if (!Impl) return null;

  const r = new Impl();
  r.lang = "en-US";
  r.interimResults = false;
  r.maxAlternatives = 1;

  r.onresult = (event) => {
    const transcript = event?.results?.[0]?.[0]?.transcript ?? "";
    handlers.onText?.(transcript);
  };

  r.onerror = (event) => {
    const code = event?.error || "unknown";
    handlers.onError?.(messageForSpeechError(code), code);
  };

  r.onend = () => handlers.onEnd?.();

  return r;
}
