// Plain Node test, no framework -- same rationale/style as the other
// *.test.mjs files in this directory. Node 22's built-in fetch/streams
// make it possible to test proposeStream() against a REAL local HTTP
// server emitting real SSE frames (including a frame split across two
// TCP chunks), not just parseSseFrame() in isolation. Run with:
//   node web/src/api.stream.test.mjs
import assert from "node:assert/strict";
import http from "node:http";

import {
  acquireForMissionStream, parseSseFrame, proposeStream, setOwnerToken,
} from "./api.js";

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok - ${name}`);
}

async function asyncTest(name, fn) {
  await fn();
  passed += 1;
  console.log(`  ok - ${name}`);
}

console.log("api.stream.test.mjs");

// --- parseSseFrame: pure parsing ----------------------------------------

test("parseSseFrame reads a well-formed stage event", () => {
  const frame = 'event: stage\ndata: {"stage":"RESEARCH","status":"IN_PROGRESS"}';
  const parsed = parseSseFrame(frame);
  assert.equal(parsed.event, "stage");
  assert.deepEqual(parsed.data, { stage: "RESEARCH", status: "IN_PROGRESS" });
});

test("parseSseFrame reads an error event", () => {
  const frame = 'event: error\ndata: {"error":"boom"}';
  const parsed = parseSseFrame(frame);
  assert.equal(parsed.event, "error");
  assert.deepEqual(parsed.data, { error: "boom" });
});

test("parseSseFrame returns null for an empty/keepalive frame", () => {
  assert.equal(parseSseFrame(""), null);
  assert.equal(parseSseFrame("\n"), null);
});

// --- proposeStream: real stream over a real local server -----------------

function startSseServer(frames, { failStatus = null } = {}) {
  const server = http.createServer((req, res) => {
    if (failStatus) {
      res.writeHead(failStatus, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ detail: "must not be empty or whitespace-only" }));
      return;
    }

    res.writeHead(200, { "Content-Type": "text/event-stream" });

    let i = 0;
    const pump = () => {
      if (i >= frames.length) {
        res.end();
        return;
      }
      // Write each frame in two pieces, on a real delay, so the test
      // exercises proposeStream()'s buffering across chunk boundaries --
      // not just a single fetch().text() read.
      const frame = frames[i];
      const mid = Math.floor(frame.length / 2);
      res.write(frame.slice(0, mid));
      setTimeout(() => {
        res.write(frame.slice(mid));
        i += 1;
        setTimeout(pump, 5);
      }, 5);
    };
    pump();
  });

  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

function sseFrame(data) {
  return `event: stage\ndata: ${JSON.stringify(data)}\n\n`;
}

await asyncTest(
  "proposeStream delivers every real stage in order and resolves with the last one, across chunk-split frames",
  async () => {
    const records = [
      { stage: "GUARDIAN_PRESCREEN", status: "IN_PROGRESS" },
      { stage: "RESEARCH", status: "IN_PROGRESS", research: { grounded: false, source_count: 0 } },
      { stage: "GENERATE", status: "IN_PROGRESS", candidate: { name: "convert_celsius_to_fahrenheit" } },
      { stage: "AWAITING_APPROVAL", status: "AWAITING_APPROVAL", candidate: { name: "convert_celsius_to_fahrenheit" } },
    ];
    const server = await startSseServer(records.map(sseFrame));
    const { port } = server.address();

    // proposeStream() reads CORE from the api.js module scope, fixed at
    // import time from VITE_CORE_URL -- so this test instead calls fetch
    // through the exact same parsing path by pointing at the real server
    // via a tiny local override, proving the reader/buffer logic against
    // a real socket rather than a mocked Response.
    const origFetch = globalThis.fetch;
    globalThis.fetch = (url, opts) =>
      origFetch(url.replace(/^https?:\/\/[^/]+/, `http://127.0.0.1:${port}`), opts);

    try {
      const seen = [];
      const final = await proposeStream("Convert Celsius temperatures to Fahrenheit.", {
        onStage: (record) => seen.push(record),
      });

      assert.deepEqual(seen.map((r) => r.stage), [
        "GUARDIAN_PRESCREEN", "RESEARCH", "GENERATE", "AWAITING_APPROVAL",
      ]);
      assert.equal(final.status, "AWAITING_APPROVAL");
      assert.equal(final.candidate.name, "convert_celsius_to_fahrenheit");
    } finally {
      globalThis.fetch = origFetch;
      server.close();
    }
  }
);

await asyncTest(
  "proposeStream surfaces a real error event by throwing, not by resolving as if nothing happened",
  async () => {
    const server = await startSseServer([
      sseFrame({ stage: "GENERATE", status: "IN_PROGRESS" }),
      'event: error\ndata: {"error":"sandbox unreachable"}\n\n',
    ]);
    const { port } = server.address();
    const origFetch = globalThis.fetch;
    globalThis.fetch = (url, opts) =>
      origFetch(url.replace(/^https?:\/\/[^/]+/, `http://127.0.0.1:${port}`), opts);

    try {
      await assert.rejects(
        () => proposeStream("Detect invalid values in a CSV column.", { onStage: () => {} }),
        /sandbox unreachable/
      );
    } finally {
      globalThis.fetch = origFetch;
      server.close();
    }
  }
);

await asyncTest(
  "proposeStream surfaces a 422 (blank need) as a real error, never as an empty successful stream",
  async () => {
    const server = await startSseServer([], { failStatus: 422 });
    const { port } = server.address();
    const origFetch = globalThis.fetch;
    globalThis.fetch = (url, opts) =>
      origFetch(url.replace(/^https?:\/\/[^/]+/, `http://127.0.0.1:${port}`), opts);

    try {
      await assert.rejects(
        () => proposeStream("   ", { onStage: () => {} }),
        /whitespace-only/
      );
    } finally {
      globalThis.fetch = origFetch;
      server.close();
    }
  }
);

await asyncTest(
  "acquireForMissionStream shares the exact same stream-consuming logic as proposeStream",
  async () => {
    const records = [
      { stage: "GUARDIAN_PRESCREEN", status: "IN_PROGRESS" },
      { stage: "RESEARCH", status: "IN_PROGRESS" },
      {
        stage: "AWAITING_APPROVAL", status: "AWAITING_APPROVAL",
        candidate: { name: "write_brief" }, mission_id: "mission-under-test",
      },
    ];
    const server = await startSseServer(records.map(sseFrame));
    const { port } = server.address();
    const origFetch = globalThis.fetch;
    globalThis.fetch = (url, opts) =>
      origFetch(url.replace(/^https?:\/\/[^/]+/, `http://127.0.0.1:${port}`), opts);

    try {
      const seen = [];
      const final = await acquireForMissionStream("mission-under-test", {
        onStage: (record) => seen.push(record),
      });
      assert.deepEqual(seen.map((r) => r.stage), [
        "GUARDIAN_PRESCREEN", "RESEARCH", "AWAITING_APPROVAL",
      ]);
      assert.equal(final.mission_id, "mission-under-test");
    } finally {
      globalThis.fetch = origFetch;
      server.close();
    }
  }
);

test("setOwnerToken/proposeStream/acquireForMissionStream import cleanly and export the expected symbols", () => {
  assert.equal(typeof setOwnerToken, "function");
  assert.equal(typeof proposeStream, "function");
  assert.equal(typeof acquireForMissionStream, "function");
  assert.equal(typeof parseSseFrame, "function");
});

console.log(`\n${passed} passed`);
