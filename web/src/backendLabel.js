/**
 * What backend this browser is ACTUALLY talking to.
 *
 * The top strip's two labels used to be static design text: "AXON NODE /
 * ASIA-SOUTH1" and "LIVE — CLOUD RUN", rendered no matter what CORE
 * pointed at. Against a local `uvicorn app.api:app` both were simply
 * false -- the strip claimed a Cloud Run deployment in a region it had
 * never contacted, three panels away from the sidebar's own promise that
 * "Every number on this surface is read from the live API. Nothing is
 * mocked."
 *
 * The backend reports neither a region nor a revision (there is no such
 * field on GET /), so the honest thing to show is the one deployment
 * fact this client genuinely knows: the origin it is calling.
 *
 * Lives in a plain .js module, like graphCompiler.js and
 * graphExecutionState.js, so it is unit-testable under bare Node without
 * a JSX runtime -- see backendLabel.test.mjs.
 */
import { CORE } from "./api.js";

export function backendLabel(coreUrl = CORE) {
  try {
    const { hostname, port } = new URL(coreUrl);
    const isLocal =
      hostname === "localhost" ||
      hostname === "127.0.0.1" ||
      hostname === "[::1]";

    if (isLocal) {
      return { node: `AXON NODE / LOCAL:${port || "80"}`, live: "LIVE — LOCAL" };
    }

    // Cloud Run hostnames carry their region:
    // aion-core-<hash>.<region>.run.app
    const region = hostname.match(/\.([a-z]+-[a-z]+\d)\.run\.app$/i)?.[1];

    return {
      node: `AXON NODE / ${(region || hostname).toUpperCase()}`,
      live: hostname.endsWith(".run.app") ? "LIVE — CLOUD RUN" : "LIVE",
    };
  } catch {
    // A malformed CORE is worth saying out loud rather than papering over
    // with a confident-looking default.
    return { node: "AXON NODE / UNKNOWN", live: "LIVE" };
  }
}
