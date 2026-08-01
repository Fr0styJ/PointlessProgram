import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import TvWall from "./TvWall";
import "./styles.css";

// Phase 37: /tv is a separate spectator view with NO nav chrome — not part of
// the authenticated dashboard's normal tab flow. No router library is
// justified for one extra top-level route at this project's scale (per
// PLAN_PHASES_33_38_DASHBOARD.md §1's "no framework sprawl" reasoning) — a
// plain pathname check is enough. Auth is still enforced identically: the BFF's
// static-file catch-all (dashboard/main.py) requires HTTP Basic Auth for
// EVERY path, /tv included, so this split is purely a rendering choice, not
// an access-control one.
const isTv = window.location.pathname.replace(/\/+$/, "") === "/tv";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{isTv ? <TvWall /> : <App />}</React.StrictMode>
);
