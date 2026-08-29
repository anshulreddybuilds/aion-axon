/**
 * Client for the aion-core API.
 *
 * The Holo-Deck reads the governed API rather than Firestore directly.
 * Live Firestore listeners would need a Firebase web config in the browser
 * AND public read rules on the audit log, approvals and capability
 * registry. For a project whose whole claim is governed access, shipping a
 * world-readable audit log to make a dashboard prettier would undercut the
 * thing being demonstrated.
 *
 * So the browser holds no credentials at all, which is the same property
 * the sandbox has, for the same reason.
 */

export const CORE =
  // `import.meta.env` only exists under Vite. Guarded, not assumed, so
  // this file can also be imported directly by plain-Node tests
  // (api.stream.test.mjs) without needing a Vite runtime just to test a
  // pure function that lives in the same module.
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_CORE_URL) ||
  "https://aion-core-638298765129.asia-south1.run.app";

/**
 * The owner token lives in a module variable and NOWHERE ELSE.
 *
 * Not localStorage, not sessionStorage, not a cookie, not the URL. This
 * token approves capability installs and trips the kill switch, so it
 * should not survive a refresh, a closed tab, or a borrowed laptop. The
 * cost is retyping it each session; the alternative is a credential
 * sitting on disk in a browser profile, which is a strictly worse trade
 * for the thing it protects.
 *
 * It is still a bearer token rather than real auth — that limitation is
 * stated in the README and is not fixed by where it is kept.
 */
let ownerToken = "";

export function setOwnerToken(value) {
  ownerToken = (value || "").trim();
}

export function hasOwnerToken() {
  return Boolean(ownerToken);
}

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json" };

  if (ownerToken) headers["X-Axon-Token"] = ownerToken;

  const response = await fetch(`${CORE}${path}`, { headers, ...options });

  if (!response.ok) {
    // 401 has one cause and one fix; saying so beats a bare status code.
    if (response.status === 401) {
      throw new Error(
        "401 — this action needs the owner token. Paste it above."
      );
    }

    // Includes CORE, not just the path: a 404/405 here is often not a
    // real backend defect but this browser talking to the wrong backend
    // entirely (CORE defaults to production -- see this module's own
    // docstring -- unless web/.env.example has been copied to .env.local
    // to point VITE_CORE_URL at a local backend). Without the origin in
    // the message, that class of confusion is indistinguishable from a
    // real API bug.
    throw new Error(`${options.method || "GET"} ${CORE}${path} → ${response.status}`);
  }

  return response.json();
}

/**
 * Parse one Server-Sent Event frame (everything between two "\n\n"
 * separators) into { event, data }. Pure and framework-free so it can be
 * unit tested without a real fetch/stream — see api.stream.test.mjs.
 *
 * Returns null for an empty/keepalive frame rather than throwing, since
 * a stray blank frame is not malformed input, just nothing to report.
 */
export function parseSseFrame(frame) {
  let event = null;
  let data = null;

  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) {
      event = line.slice("event: ".length);
    } else if (line.startsWith("data: ")) {
      const raw = line.slice("data: ".length);
      try {
        data = JSON.parse(raw);
      } catch {
        data = null;
      }
    }
  }

  if (event === null && data === null) return null;
  return { event, data };
}

/**
 * Consume any of this API's text/event-stream routes. Deliberately NOT
 * the browser's native EventSource: EventSource cannot send a custom
 * header, and every one of these routes is gated on X-Axon-Token the
 * same as every other write — putting the owner token in the URL
 * instead (the only way EventSource could authenticate) would leak it
 * into server logs and browser history, exactly what setOwnerToken()'s
 * module-variable-only design exists to avoid. fetch() + a manual
 * stream reader keeps the token where every other call already keeps
 * it: a header, never a URL.
 *
 * `onStage(record)` fires once per real stage the backend pipeline just
 * completed — record is the exact AcquisitionRecord.to_dict() shape the
 * matching non-streaming POST route already returns, just delivered
 * incrementally. Resolves with the LAST record delivered (the terminal
 * outcome).
 */
async function consumeStageStream(url, { onStage, signal } = {}) {
  const headers = {};
  if (ownerToken) headers["X-Axon-Token"] = ownerToken;

  const response = await fetch(url, { headers, signal });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error(
        "401 — this action needs the owner token. Paste it above."
      );
    }
    // A rejected request (422 blank need, 429 rate limit) never opens
    // as a stream at all — its body is a normal JSON error, not SSE.
    let detail = `GET ${url} → ${response.status}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* body wasn't JSON; the generic detail above stands */
    }
    throw new Error(detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let last = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      const parsed = parseSseFrame(frame);
      if (!parsed) continue;

      if (parsed.event === "error") {
        throw new Error(parsed.data?.error || "The live pipeline stream failed.");
      }

      last = parsed.data;
      onStage?.(parsed.data);
    }
  }

  return last;
}

/** GET /synapse/propose/stream — see consumeStageStream() above. */
export function proposeStream(
  need,
  { missionId, allowRetry = false, onStage, signal } = {}
) {
  const params = new URLSearchParams({ need });
  if (missionId) params.set("mission_id", missionId);
  if (allowRetry) params.set("allow_retry", "true");

  return consumeStageStream(
    `${CORE}/synapse/propose/stream?${params.toString()}`,
    { onStage, signal }
  );
}

/**
 * GET /missions/{id}/acquire/stream — the same acquisition as
 * api.acquire(), streamed. For a mission that BLOCKED on a real
 * capability gap: shows SYNAPSE researching/generating/screening/
 * testing/evaluating/approving the missing capability live, instead of
 * only the terminal AWAITING_APPROVAL result. Once approved and
 * installed (api.install()), the ORIGINAL mission resumes automatically
 * — this only covers the acquisition half.
 */
export function acquireForMissionStream(missionId, { onStage, signal } = {}) {
  return consumeStageStream(
    `${CORE}/missions/${missionId}/acquire/stream`,
    { onStage, signal }
  );
}

export const api = {
  root: () => request("/"),
  capabilities: () => request("/capabilities"),
  autonomy: () => request("/autonomy"),
  evolution: () => request("/evolution"),
  monitors: () => request("/monitors"),
  pending: () => request("/approvals/pending"),
  sandboxProof: () => request("/sandbox/proof"),
  passport: (name) => request(`/capabilities/${name}/passport`),
  review: (id) => request(`/approvals/${id}/review`),
  telemetry: () => request("/telemetry"),

  decide: (id, approved) =>
    request(`/approvals/${id}/decide`, {
      method: "POST",
      body: JSON.stringify({ approved, decided_by: "anshul" }),
    }),

  // Plain English in, governed plan out. This endpoint already does the
  // whole job -- plan, execute, block honestly on a gap -- it simply had
  // no front door until now.
  plannedMission: (text) =>
    request("/missions/planned", {
      method: "POST",
      body: JSON.stringify({ request: text }),
    }),

  mission: (id) => request(`/missions/${id}`),

  // The graphical mission builder's entry point. `plan` is a
  // MissionPlan built by graphCompiler.js's compileGraphToPlan() --
  // the exact same schema plannedMission() gets from the Gemini
  // planner, just authored on a canvas instead of free text. See
  // POST /missions/from-graph (app/api.py) and MissionService
  // .start_from_plan() (app/missions/service.py): there is no second
  // execution engine, only a second way to produce the same plan.
  missionFromGraph: (plan) =>
    request("/missions/from-graph", {
      method: "POST",
      body: JSON.stringify(plan),
    }),

  acquire: (missionId) =>
    request(`/missions/${missionId}/acquire`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  // Continue a graph (or planner) mission past a direct MEDIUM/HIGH-risk
  // approval gate -- decide() only records the human's decision;
  // resume-planned re-reads it and runs the rest of the plan. Distinct
  // from install()'s auto-resume, which only fires for a BLOCKED
  // capability-gap acquisition, not a plain approval-required step.
  resumePlanned: (missionId) =>
    request(`/missions/${missionId}/resume-planned`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  // Continue a mission that BLOCKED on a missing capability, optionally
  // naming the capability that was just installed for that gap.
  resumeBlocked: (missionId, capabilityName) =>
    request(`/missions/${missionId}/resume-blocked`, {
      method: "POST",
      body: JSON.stringify({ capability_name: capabilityName || null }),
    }),

  install: (capability) =>
    request(`/synapse/install/${capability}`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  // Runs the REAL acquisition loop synchronously and returns the
  // terminal AcquisitionRecord (research → generate → screen → sandbox
  // → evaluate → guardian → approval). This IS the governed pipeline,
  // not a summary of it — the call blocks on real Gemini/sandbox work,
  // typically 10-30s. allow_retry permits one real regenerate-on-failure
  // attempt; see app/synapse/engine.py's retry loop.
  proposeCapability: (need, { missionId, allowRetry = false } = {}) =>
    request("/synapse/propose", {
      method: "POST",
      body: JSON.stringify({
        need,
        mission_id: missionId || null,
        allow_retry: allowRetry,
      }),
    }),

  // The SAME pipeline as proposeCapability, streamed: one real event per
  // stage as GET /synapse/propose/stream's generator (app/synapse/engine.py's
  // propose_stream()) actually completes it. See proposeStream() below —
  // not part of the `request()`-based table above because it isn't a
  // single JSON response, it's a stream.
  proposeStream,
  acquireForMissionStream,

  // Cloud Run returns HTTP 411 on a POST with no body, so every POST
  // sends one even when the endpoint ignores it.
  setKillSwitch: (active) =>
    request("/killswitch", {
      method: "POST",
      body: JSON.stringify({ active, reason: "Holo-Deck" }),
    }),

  // Beastmode governance proof surface — every call here is a real GET/POST
  // against app/beastmode/*.py. Nothing in this block is mocked; a failed
  // call is surfaced as NOT AVAILABLE, never silently swapped for a fake
  // result. See docs/AXON_BEASTMODE_AUDIT.md for what each module verifies.
  redTeam: () => request("/beastmode/red-team"),
  ledgerVerify: () => request("/beastmode/ledger/verify"),
  ledgerSeal: () => request("/beastmode/ledger/seal", { method: "POST" }),
  contract: (capability) => request(`/beastmode/contract/${capability}`),
  lineage: (capability) => request(`/beastmode/lineage/${capability}`),
  quarantine: () => request("/beastmode/quarantine"),
  explainApproval: (requestId) =>
    request(`/beastmode/approval/${requestId}/explain`),

  // Read-only lexical-overlap memory over the real capability registry +
  // audit trail. Never generates, screens, sandboxes, approves or
  // installs anything -- see app/beastmode/memory.py's module docstring.
  memoryQuery: (need) =>
    request("/beastmode/memory/query", {
      method: "POST",
      body: JSON.stringify({ need }),
    }),
  memoryHistory: (capability) => request(`/beastmode/memory/${capability}`),

  // The memory-informed plan for a need -- REUSE_EXISTING_CAPABILITY /
  // ACQUIRE_NEW (with strategy) / ESCALATE. Read-only, same invariant as
  // memoryQuery: see app/synapse/planner.py's module docstring.
  plan: (need) =>
    request("/beastmode/plan", {
      method: "POST",
      body: JSON.stringify({ need }),
    }),

  securityReport: () => request("/beastmode/security/report"),

  missionReadiness: () => request("/beastmode/mission/readiness"),

  // The formal capability-lifecycle transition table -- public, pure
  // constants, no secrets. See app/beastmode/state_machine.py.
  stateMachine: () => request("/beastmode/state-machine"),
};

/** Fetch everything the dashboard shows, tolerating partial failure.
 *
 *  One dead endpoint must not blank the whole screen — during a demo a
 *  blank panel reads as "the system is down" when only one call failed.
 */
export async function loadAll() {
  const [
    root, capabilities, autonomy, evolution, monitors, pending, sandbox,
    telemetry,
  ] = await Promise.allSettled([
      api.root(),
      api.capabilities(),
      api.autonomy(),
      api.evolution(),
      api.monitors(),
      api.pending(),
      api.sandboxProof(),
      // The Synapse Theater reads this to decide which agents have
      // actually done work. Settled with the rest, so a telemetry outage
      // costs one quiet panel rather than the whole dashboard.
      api.telemetry(),
    ]);

  const value = (settled, fallback) =>
    settled.status === "fulfilled" ? settled.value : fallback;

  return {
    root: value(root, null),
    capabilities: value(capabilities, { capabilities: [] }),
    autonomy: value(autonomy, { capabilities: [] }),
    evolution: value(evolution, { events: [] }),
    monitors: value(monitors, { monitors: [] }),
    pending: value(pending, { pending: [] }),
    sandbox: value(sandbox, null),
    telemetry: value(telemetry, null),
    online: root.status === "fulfilled",
  };
}
