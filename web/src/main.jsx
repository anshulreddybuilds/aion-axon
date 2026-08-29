import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import AppV2 from "./v2/AppV2.jsx";
import AppV3 from "./v3/AppV3.jsx";
import AppV4 from "./v4/AppV4.jsx";
import AppV5 from "./v5/AppV5.jsx";
import "./index.css";

/**
 * Five surfaces, one build.
 *
 * v5 (AppV5), the graphical mission builder, is now the default at `/` --
 * the owner's explicit call on 29 Aug after reviewing all of them: it is
 * "the right UI we worked and build[t]", not the v1 Holo-Deck that used
 * to load here.
 *
 * v1 (App), the original production Holo-Deck (Pipeline / Autonomy
 * ledger / Evidence / Mission Theater / Judge Mode), is NOT removed --
 * it is still fully live at `/v1`, since nothing else in the product
 * routes to those panels except through it.
 *
 * v2/v3/v4 keep their existing paths unchanged. Firebase rewrites every
 * path to index.html, so this is a plain path check with no router
 * dependency.
 */
const path = window.location.pathname.replace(/\/+$/, "");

function Surface() {
  if (path.endsWith("/v4")) return <AppV4 />;
  if (path.endsWith("/v3")) return <AppV3 />;
  if (path.endsWith("/v2")) return <AppV2 />;
  if (path.endsWith("/v1")) return <App />;
  return <AppV5 />;
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Surface />
  </React.StrictMode>
);
