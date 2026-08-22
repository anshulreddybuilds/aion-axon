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
  import.meta.env.VITE_CORE_URL ||
  "https://aion-core-638298765129.asia-south1.run.app";

async function request(path, options = {}) {
  const response = await fetch(`${CORE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`${options.method || "GET"} ${path} → ${response.status}`);
  }

  return response.json();
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

  // Cloud Run returns HTTP 411 on a POST with no body, so every POST
  // sends one even when the endpoint ignores it.
  setKillSwitch: (active) =>
    request("/killswitch", {
      method: "POST",
      body: JSON.stringify({ active, reason: "Holo-Deck" }),
    }),
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
