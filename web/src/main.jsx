import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import AppV2 from "./v2/AppV2.jsx";
import "./index.css";

/**
 * Two surfaces, one build.
 *
 * v1 (App) is the live production Holo-Deck and the filming fallback. It
 * stays the default at `/` so nothing about the existing site changes.
 *
 * v2 (AppV2) is the obsidian redesign, reachable at `/v2`. Firebase
 * rewrites every path to index.html, so this is a plain path check with
 * no router dependency.
 *
 * Gating on the path rather than replacing App outright is deliberate:
 * eight days from submission, the thing that already works has to remain
 * reachable while the new thing is still being judged on real hardware.
 */
const useV2 = window.location.pathname.replace(/\/+$/, "").endsWith("/v2");

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>{useV2 ? <AppV2 /> : <App />}</React.StrictMode>
);
