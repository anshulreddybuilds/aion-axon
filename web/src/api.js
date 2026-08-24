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

  // Plain English in, governed plan out. This endpoint already does the
  // whole job -- plan, execute, block honestly on a gap -- it simply had
  // no front door until now.
  plannedMission: (text) =>
    request("/missions/planned", {
      method: "POST",
      body: JSON.stringify({ request: text }),
    }),

  mission: (id) => request(`/missions/${id}`),

  acquire: (missionId) =>
    request(`/missions/${missionId}/acquire`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  install: (capability) =>
    request(`/synapse/install/${capability}`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

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
