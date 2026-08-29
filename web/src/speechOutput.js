/**
 * Speaks the REAL mission outcome text -- never a scripted line, never
 * invented from a status word alone. The caller passes the exact same
 * string already shown on screen (sendOutcome.text in AppV4.jsx), so
 * what's spoken and what's displayed can never drift apart.
 *
 * Browser-native SpeechSynthesis only, same reasoning as
 * speechRecognition.js: no cloud TTS service, no API key, no per-call
 * cost. Degrades silently where unsupported -- a missing voice is a
 * missing convenience, never a missing result (the on-screen trace is
 * always the source of truth).
 */
export function speechSynthesisSupported(win = globalThis) {
  return Boolean(win && win.speechSynthesis && win.SpeechSynthesisUtterance);
}

export function speak(text, win = globalThis) {
  if (!text || !speechSynthesisSupported(win)) return false;

  try {
    win.speechSynthesis.cancel(); // never queue behind a stale prior result
    const utterance = new win.SpeechSynthesisUtterance(text);
    win.speechSynthesis.speak(utterance);
    return true;
  } catch {
    return false;
  }
}

export function stopSpeaking(win = globalThis) {
  if (!speechSynthesisSupported(win)) return;
  try {
    win.speechSynthesis.cancel();
  } catch {
    /* nothing to cancel */
  }
}
