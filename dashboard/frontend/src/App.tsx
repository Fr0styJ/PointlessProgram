import { useEffect, useState } from "react";
import { api, LlmSpend, LlmStatus, NarrativeSummary, SimulationStatus } from "./api";

// Phase 33 dashboard shell. Nav is a plain array of {key,label} entries so
// Phases 34-37 can extend it by adding entries — no router library needed at
// this scale (single Principal user, small tab count).
const NAV_ITEMS = [
  { key: "simulation", label: "Simulation" },
  { key: "llm", label: "LLM Status" },
  { key: "narrative", label: "Narrative" },
  { key: "settings", label: "Settings" },
  // Future phases plug in here: HR, Payroll, Accounting, External World,
  // KPI/Performance, Company Direction, Chaos, Data Management, Branding, TV...
] as const;

type TabKey = (typeof NAV_ITEMS)[number]["key"];

export default function App() {
  const [tab, setTab] = useState<TabKey>("simulation");

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">FakeCo Control Dashboard</div>
        <nav className="tabs">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              className={item.key === tab ? "tab tab-active" : "tab"}
              onClick={() => setTab(item.key)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>
      <main className="content">
        {tab === "simulation" && <SimulationTab />}
        {tab === "llm" && <LlmStatusTab />}
        {tab === "narrative" && <NarrativeTab />}
        {tab === "settings" && <SettingsTab />}
      </main>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return <div className="error-banner">Service unavailable: {message}</div>;
}

const SPEED_PRESETS = [0.1, 0.25, 0.5, 1, 2, 5, 10];

function SimulationTab() {
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () => {
    api
      .simulationStatus()
      .then(setStatus)
      .catch((e) => setErr(String(e)));
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, []);

  const togglePause = async () => {
    if (!status?.tick) return;
    setBusy(true);
    try {
      if (status.tick.paused) {
        await api.tickResume();
      } else {
        await api.tickPause();
      }
      refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <h1>Simulation</h1>
      {err && <ErrorBanner message={err} />}

      <div className="card">
        <h2>Sim Time</h2>
        {status?.sim_clock_error && <ErrorBanner message={status.sim_clock_error} />}
        {status?.sim_clock && (
          <div className="stat-row">
            <div className="stat">
              <div className="stat-label">Sim time</div>
              <div className="stat-value">{new Date(status.sim_clock.sim_time).toLocaleString()}</div>
            </div>
            <div className="stat">
              <div className="stat-label">Speed multiplier</div>
              <div className="stat-value">{status.sim_clock.speed_multiplier}x</div>
            </div>
            <div className="stat">
              <div className="stat-label">Wall time (UTC)</div>
              <div className="stat-value">{new Date(status.sim_clock.wall_time_utc).toLocaleString()}</div>
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <h2>
          Speed Slider <span className="badge badge-soon">Coming Soon</span>
        </h2>
        <p className="hint" title="Requires Phase 32 (live speed-change API) — deferred, see Future_Plans.md">
          Requires Phase 32 (live speed-change API) — deferred. This control is a placeholder shape only.
        </p>
        <div className="disabled-control">
          <input type="range" min={0} max={SPEED_PRESETS.length - 1} disabled />
          <div className="preset-row">
            {SPEED_PRESETS.map((p) => (
              <button key={p} disabled className="preset-btn">
                {p}x
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <h2>Orchestrator Tick Loop</h2>
        {status?.tick_error && <ErrorBanner message={status.tick_error} />}
        {status?.tick && (
          <>
            <div className="stat-row">
              <div className="stat">
                <div className="stat-label">State</div>
                <div className="stat-value">{status.tick.paused ? "Paused" : "Running"}</div>
              </div>
              <div className="stat">
                <div className="stat-label">Last tick (wall clock)</div>
                <div className="stat-value">
                  {status.tick.last_tick_at ? new Date(status.tick.last_tick_at).toLocaleString() : "—"}
                </div>
              </div>
              <div className="stat">
                <div className="stat-label">Tick interval</div>
                <div className="stat-value">{status.tick.tick_interval_seconds}s</div>
              </div>
            </div>
            <button className="action-btn" disabled={busy} onClick={togglePause}>
              {status.tick.paused ? "Resume tick loop" : "Pause tick loop"}
            </button>
            <p className="hint">
              Pauses/resumes orchestrator's own scheduling loop only — does not stop any container
              or the compose stack.
            </p>
          </>
        )}
      </div>
    </section>
  );
}

function LlmStatusTab() {
  const [status, setStatus] = useState<LlmStatus | null>(null);
  const [spend, setSpend] = useState<LlmSpend | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.llmStatus().then(setStatus).catch((e) => setErr(String(e)));
    api.llmSpend().then(setSpend).catch((e) => setErr(String(e)));
    const id = setInterval(() => {
      api.llmSpend().then(setSpend).catch(() => {});
    }, 15000);
    return () => clearInterval(id);
  }, []);

  return (
    <section>
      <h1>LLM Status</h1>
      {err && <ErrorBanner message={err} />}

      <div className="card">
        <h2>Provider / Fallback Chain</h2>
        {status?.provider_config?.error && <ErrorBanner message={status.provider_config.error} />}
        {status?.provider_config?.tiers && (
          <table className="table">
            <thead>
              <tr>
                <th>Tier</th>
                <th>Deployments (ordered by fallback)</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(status.provider_config.tiers).map(([tier, models]) => (
                <tr key={tier}>
                  <td>{tier}</td>
                  <td>{models.join(" → ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>Usage / Cost</h2>
        {spend && (
          <>
            <div className="stat-row">
              <div className="stat">
                <div className="stat-label">Total spend (all-time)</div>
                <div className="stat-value">${spend.total_spend.toFixed(4)}</div>
              </div>
              <div className="stat">
                <div className="stat-label">Total tokens</div>
                <div className="stat-value">{spend.total_tokens.toLocaleString()}</div>
              </div>
              <div className="stat">
                <div className="stat-label">$/wall-clock-hour (trailing 1h)</div>
                <div className="stat-value">${spend.spend_per_wallclock_hour.toFixed(4)}</div>
              </div>
              <div className="stat">
                <div className="stat-label">Speed-adjusted burn ($/sim-hour)</div>
                <div className="stat-value">${spend.burn_per_sim_hour.toFixed(4)}</div>
              </div>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Calls</th>
                  <th>Tokens</th>
                  <th>Spend</th>
                </tr>
              </thead>
              <tbody>
                {spend.by_model.map((m) => (
                  <tr key={m.model}>
                    <td>{m.model}</td>
                    <td>{m.calls}</td>
                    <td>{m.tokens?.toLocaleString?.() ?? m.tokens}</td>
                    <td>${Number(m.spend).toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </section>
  );
}

function NarrativeTab() {
  const [data, setData] = useState<NarrativeSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const load = () => api.narrativeSummary().then(setData).catch((e) => setErr(String(e)));
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, []);

  return (
    <section>
      <h1>Narrative</h1>
      {err && <ErrorBanner message={err} />}
      {data && (
        <>
          <div className="card">
            <h2>Open Threads ({data.threads.length})</h2>
            <table className="table">
              <thead>
                <tr>
                  <th>Priority</th>
                  <th>Topic</th>
                  <th>Department</th>
                  <th>Status</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {data.threads.map((t) => (
                  <tr key={t.id} className={t.priority > 0 ? "row-crisis" : ""}>
                    <td>{t.priority > 0 ? <span className="badge badge-crisis">CRISIS</span> : t.priority}</td>
                    <td>{t.topic}</td>
                    <td>{t.department ?? "—"}</td>
                    <td>{t.status}</td>
                    <td>{new Date(t.updated_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card">
            <h2>Action Items ({data.action_items.length})</h2>
            <table className="table">
              <thead>
                <tr>
                  <th>Description</th>
                  <th>Owner (employee id)</th>
                  <th>Status</th>
                  <th>Due</th>
                </tr>
              </thead>
              <tbody>
                {data.action_items.map((a) => (
                  <tr key={a.id}>
                    <td>{a.description}</td>
                    <td>{a.owner_employee_id}</td>
                    <td>{a.status}</td>
                    <td>{a.due_at ? new Date(a.due_at).toLocaleDateString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card">
            <h2>Pending Reactions ({data.pending_reactions.length})</h2>
            <table className="table">
              <thead>
                <tr>
                  <th>Thread</th>
                  <th>Target employee</th>
                </tr>
              </thead>
              <tbody>
                {data.pending_reactions.map((p) => (
                  <tr key={p.id}>
                    <td>{p.thread_id}</td>
                    <td>{p.target_employee_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card">
            <h2>Pending Approvals ({data.pending_approvals.length})</h2>
            <table className="table">
              <thead>
                <tr>
                  <th>Ref</th>
                  <th>Requester</th>
                  <th>Approver</th>
                  <th>Amount</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {data.pending_approvals.map((p) => (
                  <tr key={p.id}>
                    <td>{p.expense_request_ref}</td>
                    <td>{p.requester_employee_id}</td>
                    <td>{p.approver_is_principal ? "Principal" : p.approver_employee_id ?? "—"}</td>
                    <td>${Number(p.amount).toFixed(2)}</td>
                    <td>{new Date(p.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card">
            <h2>Meetings ({data.meetings.length})</h2>
            <table className="table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Thread</th>
                  <th>Attendees</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {data.meetings.map((m) => (
                  <tr key={m.id}>
                    <td>{m.meeting_type}</td>
                    <td>{m.thread_id ?? "—"}</td>
                    <td>{Array.isArray(m.attendees) ? m.attendees.length : "—"}</td>
                    <td>{new Date(m.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card">
            <h2>Pending Actions Retry Queue</h2>
            <div className="stat-row">
              <div className="stat">
                <div className="stat-label">Queue depth</div>
                <div className="stat-value">{data.pending_actions.retry_queue_depth}</div>
              </div>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Target</th>
                  <th>Status</th>
                  <th>Attempts</th>
                  <th>Next retry</th>
                </tr>
              </thead>
              <tbody>
                {data.pending_actions.recent.map((p) => (
                  <tr key={p.id}>
                    <td>{p.action_type}</td>
                    <td>{p.target_service}</td>
                    <td>{p.status}</td>
                    <td>{p.attempts}</td>
                    <td>{p.next_retry_at ? new Date(p.next_retry_at).toLocaleString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function SettingsTab() {
  return (
    <section>
      <h1>Settings</h1>
      <div className="card">
        <p>
          This is a reserved navigation slot. The full-purge "nuclear launch" control (danger-red,
          multi-step confirmation) lands here in Phase 36/38 — nothing destructive is wired up yet.
        </p>
      </div>
    </section>
  );
}
