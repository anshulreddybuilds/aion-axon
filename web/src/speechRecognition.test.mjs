// Plain Node test, no framework -- same rationale/style as the other
// *.test.mjs files in this directory. Fakes a minimal SpeechRecognition
// implementation (Node has no real Web Speech API) to exercise the exact
// event-handling logic a real browser would trigger. Run with:
//   node web/src/speechRecognition.test.mjs
import assert from "node:assert/strict";

import {
  createRecognizer, messageForSpeechError, speechRecognitionSupported,
} from "./speechRecognition.js";

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok - ${name}`);
}

console.log("speechRecognition.test.mjs");

class FakeSpeechRecognition {
  constructor() {
    this.started = false;
    this.aborted = false;
  }
  start() {
    this.started = true;
  }
  stop() {
    this.started = false;
  }
  abort() {
    this.aborted = true;
    this.started = false;
  }
}

function fakeResultEvent(transcript) {
  return { results: [[{ transcript }]] };
}

// --- Support detection ---------------------------------------------------

test("speechRecognitionSupported is false with no implementation on window", () => {
  assert.equal(speechRecognitionSupported({}), false);
});

test("speechRecognitionSupported is true with SpeechRecognition present", () => {
  assert.equal(
    speechRecognitionSupported({ SpeechRecognition: FakeSpeechRecognition }),
    true
  );
});

test("speechRecognitionSupported is true with only the webkit-prefixed name", () => {
  assert.equal(
    speechRecognitionSupported({ webkitSpeechRecognition: FakeSpeechRecognition }),
    true
  );
});

test("createRecognizer returns null when the browser has no implementation", () => {
  assert.equal(createRecognizer({}, {}), null);
});

// --- The transcript becomes the exact onText payload ----------------------

test("a real speech result delivers the EXACT transcript, unmodified", () => {
  let received = null;
  const r = createRecognizer(
    { onText: (t) => (received = t) },
    { SpeechRecognition: FakeSpeechRecognition }
  );
  r.onresult(fakeResultEvent("Convert 100 degrees Celsius to Fahrenheit."));
  assert.equal(received, "Convert 100 degrees Celsius to Fahrenheit.");
});

test("two different transcripts deliver two different onText calls -- no fixed example", () => {
  const seen = [];
  const r = createRecognizer(
    { onText: (t) => seen.push(t) },
    { SpeechRecognition: FakeSpeechRecognition }
  );
  r.onresult(fakeResultEvent("Calculate 17 percent of 8450."));
  r.onresult(fakeResultEvent("Find the current population of Tokyo."));
  assert.deepEqual(seen, [
    "Calculate 17 percent of 8450.",
    "Find the current population of Tokyo.",
  ]);
  assert.notEqual(seen[0], seen[1]);
});

test("an empty transcript still delivers an empty string, not a crash or a fabricated value", () => {
  let received = "not called";
  const r = createRecognizer(
    { onText: (t) => (received = t) },
    { SpeechRecognition: FakeSpeechRecognition }
  );
  r.onresult({ results: [[{ transcript: "" }]] });
  assert.equal(received, "");
});

// --- Errors are surfaced honestly, never swallowed -------------------------

test("messageForSpeechError maps a known code to an actionable message", () => {
  const msg = messageForSpeechError("not-allowed");
  assert.ok(msg.toLowerCase().includes("microphone"));
});

test("messageForSpeechError never throws on an unknown code, and says so", () => {
  const msg = messageForSpeechError("some-new-browser-error-code");
  assert.ok(msg.includes("some-new-browser-error-code"));
});

test("a real onerror event surfaces the mapped message via onError, not silently", () => {
  let message = null;
  let code = null;
  const r = createRecognizer(
    { onError: (m, c) => { message = m; code = c; } },
    { SpeechRecognition: FakeSpeechRecognition }
  );
  r.onerror({ error: "audio-capture" });
  assert.ok(message.toLowerCase().includes("no microphone"));
  assert.equal(code, "audio-capture");
});

test("onend fires onEnd (used to reset the listening indicator)", () => {
  let ended = false;
  const r = createRecognizer(
    { onEnd: () => (ended = true) },
    { SpeechRecognition: FakeSpeechRecognition }
  );
  r.onend();
  assert.equal(ended, true);
});

console.log(`\n${passed} passed`);
