import { useEffect, useState } from "react";
import {
  api,
  AccountingSummary,
  KpiDepartmentScoreboard,
  NarrativeSummary,
  SimulationStatus,
  TvChatFeed,
  TvTicketFeed,
} from "./api";

// ---------------------------------------------------------------------------
// Phase 37: /tv route — no-nav-chrome spectator view. Still gated behind the
// same HTTP Basic Auth as every other route (the SPA catch-all in
// dashboard/main.py auths every path, this one included) but renders with no
// tabs/nav — pure auto-cycling panels, per spec.
//
// Panels, ~18s each: chat feed, ticket feed, financial snapshot, KPI
// highlights, sim-time/speed. A "weekly digest" panel was considered (per the
// plan's own feature list) but Phase 25 (the weekly-digest generator) is
// confirmed NOT built anywhere in this codebase (see PHASES.md's Phase 25
// section + kpi-engine has no digest-selection code) — so it's skipped
// entirely rather than inventing fake content, per the plan's own explicit
// instruction to confirm before building it.
// ---------------------------------------------------------------------------
const CYCLE_MS = 18000;
const PANELS = ["chat", "tickets", "financial", "kpi", "sim"] as const;
type Panel = (typeof PANELS)[number];

export default function TvWall() {
  const [panelIdx, setPanelIdx] = useState(0);
  const [chat, setChat] = useState<TvChatFeed | null>(null);
  const [tickets, setTickets] = useState<TvTicketFeed | null>(null);
  const [accounting, setAccounting] = useState<AccountingSummary | null>(null);
  const [kpi, setKpi] = useState<KpiDepartmentScoreboard | null>(null);
  const [sim, setSim] = useState<SimulationStatus | null>(null);
  const [narrative, setNarrative] = useState<NarrativeSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const load = () => {
      api.tvChatFeed().then(setChat).catch((e) => setErr(String(e)));
      api.tvTicketFeed().then(setTickets).catch((e) => setErr(String(e)));
      api.accountingSummary().then(setAccounting).catch((e) => setErr(String(e)));
      api.kpiDepartmentScoreboard().then(setKpi).catch((e) => setErr(String(e)));
      api.simulationStatus().then(setSim).catch((e) => setErr(String(e)));
      api.narrativeSummary().then(setNarrative).catch((e) => setErr(String(e)));
    };
    load();
    const dataId = setInterval(load, 15000);
    return () => clearInterval(dataId);
  }, []);

  useEffect(() => {
    const id = setInterval(() => setPanelIdx((i) => (i + 1) % PANELS.length), CYCLE_MS);
    return () => clearInterval(id);
  }, []);

  const panel: Panel = PANELS[panelIdx];

  return (
    <div className="tv-wall">
      <div className="tv-dots">
        {PANELS.map((p, i) => (
          <span key={p} className={i === panelIdx ? "tv-dot tv-dot-active" : "tv-dot"} />
        ))}
      </div>
      {err && <div className="tv-error">{err}</div>}

      {panel === "chat" && (
        <div className="tv-panel">
          <h1>Live Chat Feed</h1>
          <div className="tv-list">
            {chat?.posts.map((p) => (
              <div key={p.id} className="tv-row">
                <span className="tv-row-meta">#{p.channel} · {p.username}</span>
                <span className="tv-row-body">{p.message}</span>
              </div>
            ))}
            {!chat?.posts.length && <p className="hint">No recent chat activity.</p>}
          </div>
        </div>
      )}

      {panel === "tickets" && (
        <div className="tv-panel">
          <h1>Live Ticket Feed</h1>
          <div className="tv-list">
            {tickets?.tickets.map((t) => (
              <div key={t.id} className="tv-row">
                <span className="tv-row-meta">#{t.number}</span>
                <span className="tv-row-body">{t.title}</span>
              </div>
            ))}
            {!tickets?.tickets.length && <p className="hint">No recent tickets.</p>}
          </div>
        </div>
      )}

      {panel === "financial" && (
        <div className="tv-panel">
          <h1>Financial Snapshot</h1>
          <div className="tv-stat-row">
            <div className="tv-stat">
              <div className="tv-stat-label">Cash balance</div>
              <div className="tv-stat-value">
                {accounting?.cash.cash_balance !== null && accounting?.cash.cash_balance !== undefined
                  ? `$${accounting.cash.cash_balance.toFixed(2)}`
                  : "—"}
              </div>
            </div>
            <div className="tv-stat">
              <div className="tv-stat-label">Pending approvals</div>
              <div className="tv-stat-value">{accounting?.pending_approvals.length ?? "—"}</div>
            </div>
            <div className="tv-stat">
              <div className="tv-stat-label">Retry queue depth</div>
              <div className="tv-stat-value">{narrative?.pending_actions.retry_queue_depth ?? "—"}</div>
            </div>
          </div>
        </div>
      )}

      {panel === "kpi" && (
        <div className="tv-panel">
          <h1>KPI Highlights (Top Movers)</h1>
          <div className="tv-list">
            {kpi?.rows
              .slice()
              .sort((a, b) => b.total - a.total)
              .slice(0, 10)
              .map((r, i) => (
                <div key={i} className="tv-row">
                  <span className="tv-row-meta">{r.department}</span>
                  <span className="tv-row-body">
                    {r.metric}: {r.total.toFixed(2)}
                  </span>
                </div>
              ))}
            {!kpi?.rows.length && <p className="hint">No KPI data in the current lookback window.</p>}
          </div>
        </div>
      )}

      {panel === "sim" && (
        <div className="tv-panel">
          <h1>Simulation Status</h1>
          <div className="tv-stat-row">
            <div className="tv-stat">
              <div className="tv-stat-label">Sim time</div>
              <div className="tv-stat-value">
                {sim?.sim_clock ? new Date(sim.sim_clock.sim_time).toLocaleString() : "—"}
              </div>
            </div>
            <div className="tv-stat">
              <div className="tv-stat-label">Speed</div>
              <div className="tv-stat-value">{sim?.sim_clock ? `${sim.sim_clock.speed_multiplier}x` : "—"}</div>
            </div>
            <div className="tv-stat">
              <div className="tv-stat-label">Tick loop</div>
              <div className="tv-stat-value">{sim?.tick ? (sim.tick.paused ? "Paused" : "Running") : "—"}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
