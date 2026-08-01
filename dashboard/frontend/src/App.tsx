import { useEffect, useMemo, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import {
  api,
  AccountingSummary,
  CompanyDirectiveCurrent,
  CompanyDirectiveHistory,
  EmployeeRosterRow,
  ExternalWorldCustomers,
  ExternalWorldNews,
  HrRelationships,
  KpiDepartmentScoreboard,
  KpiEmployeeScoreboard,
  KpiReviewLog,
  LlmSpend,
  LlmStatus,
  NarrativeSummary,
  PayrollEmployeeRow,
  PayrollHistory,
  RevenueByCustomer,
  SimulationStatus,
} from "./api";

// Phase 33 dashboard shell. Nav is a plain array of {key,label} entries so
// Phases 34-37 can extend it by adding entries — no router library needed at
// this scale (single Principal user, small tab count).
const NAV_ITEMS = [
  { key: "simulation", label: "Simulation" },
  { key: "llm", label: "LLM Status" },
  { key: "narrative", label: "Narrative" },
  { key: "hr", label: "HR / Org Chart" },
  { key: "payroll", label: "Payroll" },
  { key: "accounting", label: "Accounting" },
  { key: "external-world", label: "External World" },
  { key: "kpi", label: "KPI / Performance" },
  { key: "company-direction", label: "Company Direction" },
  { key: "settings", label: "Settings" },
  // Future phases plug in here: Chaos, Data Management, Branding, TV...
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
        {tab === "hr" && <HrTab />}
        {tab === "payroll" && <PayrollTab />}
        {tab === "accounting" && <AccountingTab />}
        {tab === "external-world" && <ExternalWorldTab />}
        {tab === "kpi" && <KpiTab />}
        {tab === "company-direction" && <CompanyDirectionTab />}
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

// ---------------------------------------------------------------------------
// Phase 34: HR / Org Chart tab
//
// Graph-viz library choice: react-force-graph-2d over reactflow. reactflow is
// built for manually-laid-out flowcharts (you own node x/y); this view is a
// pure "node=employee, edge=relationship, weight=affinity" graph with no
// natural manual layout, so a force-directed auto-layout library is the
// better fit and needs far less wiring code (no node-position state to own).
// ---------------------------------------------------------------------------
function HrTab() {
  const [roster, setRoster] = useState<EmployeeRosterRow[] | null>(null);
  const [rel, setRel] = useState<HrRelationships | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [fireTarget, setFireTarget] = useState<EmployeeRosterRow | null>(null);
  const [hireOpen, setHireOpen] = useState(false);
  const [hireForm, setHireForm] = useState({ name: "", department: "", title: "", role_tier: "ic" });
  const [busy, setBusy] = useState(false);
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<number | null>(null);

  const load = () => {
    api.hrRoster().then((d) => setRoster(d.employees)).catch((e) => setErr(String(e)));
    api.hrRelationships().then(setRel).catch((e) => setErr(String(e)));
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  const doFire = async () => {
    if (!fireTarget) return;
    setBusy(true);
    try {
      await api.hrFire(fireTarget.id);
      setFireTarget(null);
      load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const doHire = async () => {
    setBusy(true);
    try {
      await api.hrHire(hireForm);
      setHireOpen(false);
      setHireForm({ name: "", department: "", title: "", role_tier: "ic" });
      load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const graphData = useMemo(() => {
    if (!rel) return { nodes: [], links: [] };
    const visible = selectedEmployeeId
      ? rel.edges.filter(
          (e) => e.employee_a_id === selectedEmployeeId || e.employee_b_id === selectedEmployeeId
        )
      : rel.edges;
    const nodeIds = selectedEmployeeId
      ? new Set<number>([selectedEmployeeId, ...visible.flatMap((e) => [e.employee_a_id, e.employee_b_id])])
      : new Set(rel.nodes.map((n) => n.id));
    return {
      nodes: rel.nodes.filter((n) => nodeIds.has(n.id)).map((n) => ({ id: n.id, name: n.name, department: n.department })),
      links: visible.map((e) => ({
        source: e.employee_a_id,
        target: e.employee_b_id,
        affinity: e.affinity_score,
        type: e.relationship_type,
      })),
    };
  }, [rel, selectedEmployeeId]);

  return (
    <section>
      <h1>HR / Org Chart</h1>
      {err && <ErrorBanner message={err} />}

      <div className="card">
        <div className="card-header-row">
          <h2>Roster ({roster?.length ?? 0})</h2>
          <button className="action-btn" onClick={() => setHireOpen(true)}>
            + Hire
          </button>
        </div>
        {roster && (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Department</th>
                <th>Title</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {roster.map((e) => (
                <tr key={e.id} className={e.display_status === "on-PTO" ? "row-pto" : ""}>
                  <td>{e.name}</td>
                  <td>{e.department}</td>
                  <td>{e.role}</td>
                  <td>
                    <span className={`badge badge-status-${e.display_status.replace(/[^a-z-]/gi, "").toLowerCase()}`}>
                      {e.display_status}
                    </span>
                  </td>
                  <td>
                    {e.status === "active" && (
                      <button className="danger-btn-small" onClick={() => setFireTarget(e)}>
                        Fire
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>Relationship Graph</h2>
        <p className="hint">
          Node = employee, edge = relationship (color/weight = affinity score). Click a node to
          filter to that employee's edges; click empty space to clear.
        </p>
        {selectedEmployeeId && (
          <button className="action-btn" onClick={() => setSelectedEmployeeId(null)}>
            Clear filter
          </button>
        )}
        <div style={{ height: 420, background: "#0f1115", borderRadius: 8, marginTop: 8 }}>
          {rel && (
            <ForceGraph2D
              graphData={graphData}
              nodeLabel={(n: any) => `${n.name} (${n.department})`}
              nodeAutoColorBy="department"
              linkWidth={(l: any) => Math.max(0.5, Math.abs(l.affinity) / 20)}
              linkColor={(l: any) => (l.affinity >= 0 ? "rgba(80,180,255,0.6)" : "rgba(220,80,80,0.6)")}
              onNodeClick={(n: any) => setSelectedEmployeeId(n.id)}
              width={1100}
              height={420}
            />
          )}
        </div>
      </div>

      {fireTarget && (
        <div className="modal-overlay">
          <div className="modal danger-modal">
            <h3>Fire {fireTarget.name}?</h3>
            <p>
              This deactivates {fireTarget.name}'s Mattermost, Zammad, Wiki.js accounts and
              restricts their mailbox (nothing is deleted). Status becomes "terminated".
            </p>
            <div className="modal-actions">
              <button className="action-btn" onClick={() => setFireTarget(null)} disabled={busy}>
                Cancel
              </button>
              <button className="danger-btn" onClick={doFire} disabled={busy}>
                {busy ? "Firing..." : "Confirm Fire"}
              </button>
            </div>
          </div>
        </div>
      )}

      {hireOpen && (
        <div className="modal-overlay">
          <div className="modal">
            <h3>Hire New Employee</h3>
            <label className="form-label">
              Name
              <input
                className="form-input"
                value={hireForm.name}
                onChange={(e) => setHireForm({ ...hireForm, name: e.target.value })}
              />
            </label>
            <label className="form-label">
              Department
              <input
                className="form-input"
                value={hireForm.department}
                onChange={(e) => setHireForm({ ...hireForm, department: e.target.value })}
              />
            </label>
            <label className="form-label">
              Title
              <input
                className="form-input"
                value={hireForm.title}
                onChange={(e) => setHireForm({ ...hireForm, title: e.target.value })}
              />
            </label>
            <label className="form-label">
              Role tier
              <select
                className="form-input"
                value={hireForm.role_tier}
                onChange={(e) => setHireForm({ ...hireForm, role_tier: e.target.value })}
              >
                <option value="ic">IC</option>
                <option value="lead">Lead</option>
              </select>
            </label>
            <div className="modal-actions">
              <button className="action-btn" onClick={() => setHireOpen(false)} disabled={busy}>
                Cancel
              </button>
              <button
                className="action-btn"
                onClick={doHire}
                disabled={busy || !hireForm.name || !hireForm.department || !hireForm.title}
              >
                {busy ? "Hiring..." : "Hire"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Phase 34: Payroll tab
// ---------------------------------------------------------------------------
function PayrollTab() {
  const [roster, setRoster] = useState<PayrollEmployeeRow[] | null>(null);
  const [history, setHistory] = useState<PayrollHistory | null>(null);
  const [proposals, setProposals] = useState<Record<number, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = () => {
    api.payrollRoster().then((d) => setRoster(d.employees)).catch((e) => setErr(String(e)));
    api.payrollHistory().then(setHistory).catch((e) => setErr(String(e)));
  };

  useEffect(() => {
    load();
  }, []);

  const applyRaise = async (emp: PayrollEmployeeRow) => {
    const proposedStr = proposals[emp.id];
    const proposed = Number(proposedStr);
    if (!proposedStr || Number.isNaN(proposed) || proposed <= emp.pay_rate) return;
    setBusyId(emp.id);
    try {
      await api.payrollRaise({ employee_id: emp.id, new_pay: proposed, reason: "manual raise via dashboard" });
      setToast(`Raise applied for ${emp.name}: $${emp.pay_rate.toFixed(2)} → $${proposed.toFixed(2)}`);
      setProposals((p) => ({ ...p, [emp.id]: "" }));
      load();
      setTimeout(() => setToast(null), 4000);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section>
      <h1>Payroll</h1>
      {err && <ErrorBanner message={err} />}
      {toast && <div className="toast">{toast}</div>}

      <div className="card">
        <h2>Per-Employee Pay Editor</h2>
        {roster && (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Department</th>
                <th>Current pay ({roster[0]?.pay_frequency ?? "biweekly"})</th>
                <th>Proposed new pay</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {roster.map((emp) => {
                const proposedStr = proposals[emp.id] ?? "";
                const proposed = Number(proposedStr);
                const isDecrease = proposedStr !== "" && !Number.isNaN(proposed) && proposed < emp.pay_rate;
                const isValidRaise = proposedStr !== "" && !Number.isNaN(proposed) && proposed > emp.pay_rate;
                return (
                  <tr key={emp.id}>
                    <td>{emp.name}</td>
                    <td>{emp.department}</td>
                    <td>${emp.pay_rate.toFixed(2)}</td>
                    <td>
                      <input
                        className="form-input form-input-small"
                        type="number"
                        step="0.01"
                        placeholder={emp.pay_rate.toFixed(2)}
                        value={proposedStr}
                        onChange={(e) => setProposals((p) => ({ ...p, [emp.id]: e.target.value }))}
                      />
                    </td>
                    <td>
                      <button
                        className="action-btn"
                        disabled={!isValidRaise || busyId === emp.id}
                        title={
                          isDecrease
                            ? "Pay cuts require Phase 24 (pay negotiation meetings) — not yet built."
                            : undefined
                        }
                        onClick={() => applyRaise(emp)}
                      >
                        {busyId === emp.id ? "Saving..." : "Save"}
                      </button>
                      {isDecrease && (
                        <p className="hint hint-inline">
                          Pay cuts require Phase 24 (pay negotiation meetings) — not yet built.
                        </p>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>Payroll History</h2>
        {history && (
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Action</th>
                <th>Actor</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {history.history.map((h) => (
                <tr key={h.id}>
                  <td>{new Date(h.created_at).toLocaleString()}</td>
                  <td>{h.action}</td>
                  <td>{h.actor}</td>
                  <td>
                    {h.detail.employee_name ? `${h.detail.employee_name}: ` : ""}
                    {h.detail.old_pay !== undefined ? `$${h.detail.old_pay} → ` : ""}
                    {h.detail.new_pay !== undefined ? `$${h.detail.new_pay}` : ""}
                    {h.detail.proposed_pay !== undefined ? `proposed $${h.detail.proposed_pay}` : ""}
                    {h.detail.reason ? ` (${h.detail.reason})` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Phase 34: Accounting tab
// ---------------------------------------------------------------------------
function AccountingTab() {
  const [data, setData] = useState<AccountingSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = () => api.accountingSummary().then(setData).catch((e) => setErr(String(e)));

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  const decide = async (approvalId: number, action: "approve" | "reject") => {
    setBusyId(approvalId);
    try {
      if (action === "approve") await api.accountingApprove(approvalId);
      else await api.accountingReject(approvalId);
      load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section>
      <h1>Accounting</h1>
      {err && <ErrorBanner message={err} />}
      {data && (
        <>
          <div className="card">
            <h2>Cash Balance</h2>
            {data.cash.error && <ErrorBanner message={data.cash.error} />}
            {data.cash.cash_balance !== null && (
              <div className="stat-row">
                <div className="stat">
                  <div className="stat-label">Cash balance</div>
                  <div className="stat-value">${data.cash.cash_balance.toFixed(2)}</div>
                </div>
              </div>
            )}
            <a className="action-btn action-btn-link" href={data.akaunting_deep_link} target="_blank" rel="noreferrer">
              Open in Akaunting
            </a>
          </div>

          <div className="card">
            <h2>Expense Approval Queue ({data.pending_approvals.length})</h2>
            <table className="table">
              <thead>
                <tr>
                  <th>Ref</th>
                  <th>Requester</th>
                  <th>Amount</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.pending_approvals.map((p) => (
                  <tr key={p.id}>
                    <td>{p.expense_request_ref}</td>
                    <td>{p.requester_employee_id}</td>
                    <td>${Number(p.amount).toFixed(2)}</td>
                    <td>{new Date(p.created_at).toLocaleString()}</td>
                    <td>
                      <button
                        className="action-btn"
                        disabled={busyId === p.id}
                        onClick={() => decide(p.id, "approve")}
                      >
                        Approve
                      </button>{" "}
                      <button
                        className="danger-btn-small"
                        disabled={busyId === p.id}
                        onClick={() => decide(p.id, "reject")}
                      >
                        Reject
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card">
            <h2>Audit-Correction Log</h2>
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Action</th>
                  <th>Actor</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {data.audit_log.map((a) => (
                  <tr key={a.id}>
                    <td>{new Date(a.created_at).toLocaleString()}</td>
                    <td>{a.action}</td>
                    <td>{a.actor}</td>
                    <td>{JSON.stringify(a.detail)}</td>
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

// ---------------------------------------------------------------------------
// Phase 35: External World tab
// ---------------------------------------------------------------------------
function ExternalWorldTab() {
  const [news, setNews] = useState<ExternalWorldNews | null>(null);
  const [customers, setCustomers] = useState<ExternalWorldCustomers | null>(null);
  const [revenue, setRevenue] = useState<RevenueByCustomer | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [customerSort, setCustomerSort] = useState<"relationship_status" | "deal_size">("relationship_status");

  useEffect(() => {
    const load = () => {
      api.externalWorldNews().then(setNews).catch((e) => setErr(String(e)));
      api.externalWorldCustomers().then(setCustomers).catch((e) => setErr(String(e)));
      api.externalWorldRevenueByCustomer().then(setRevenue).catch((e) => setErr(String(e)));
    };
    load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, []);

  const sortedCustomers = useMemo(() => {
    if (!customers) return [];
    const rows = [...customers.customers];
    if (customerSort === "deal_size") {
      rows.sort((a, b) => (b.deal_size ?? 0) - (a.deal_size ?? 0));
    } else {
      rows.sort((a, b) => a.relationship_status.localeCompare(b.relationship_status));
    }
    return rows;
  }, [customers, customerSort]);

  const jobOfferNews = news?.news.filter((n) => n.category === "job_offer_resignation") ?? [];

  return (
    <section>
      <h1>External World</h1>
      {err && <ErrorBanner message={err} />}

      <div className="card">
        <h2>BetaCorp News Feed ({news?.news.length ?? 0})</h2>
        {news && (
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Event</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {news.news.map((n) => (
                <tr key={n.id} className={n.category === "job_offer_resignation" ? "row-crisis" : ""}>
                  <td>{new Date(n.created_at).toLocaleString()}</td>
                  <td>{n.action}</td>
                  <td>
                    {n.detail.name ? `${n.detail.name}: ` : ""}
                    {n.detail.gap_pct !== undefined ? `${n.detail.gap_pct}% below benchmark` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>Job Offers / Resignations ({jobOfferNews.length})</h2>
        <table className="table">
          <thead>
            <tr>
              <th>When</th>
              <th>Event</th>
              <th>Employee</th>
            </tr>
          </thead>
          <tbody>
            {jobOfferNews.map((n) => (
              <tr key={n.id}>
                <td>{new Date(n.created_at).toLocaleString()}</td>
                <td>{n.action === "betacorp_offer_sent" ? "Job offer sent" : "Resigned"}</td>
                <td>{n.detail.name ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="card-header-row">
          <h2>Customer Pipeline / At-Risk ({sortedCustomers.length})</h2>
          <select
            className="form-input form-input-small"
            value={customerSort}
            onChange={(e) => setCustomerSort(e.target.value as any)}
          >
            <option value="relationship_status">Sort: Status</option>
            <option value="deal_size">Sort: Deal size</option>
          </select>
        </div>
        {customers && (
          <table className="table">
            <thead>
              <tr>
                <th>Company</th>
                <th>Status</th>
                <th>Deal size</th>
                <th>Sales rep</th>
                <th>Support rep</th>
              </tr>
            </thead>
            <tbody>
              {sortedCustomers.map((c) => (
                <tr key={c.id} className={c.relationship_status === "at_risk" || c.relationship_status === "churned" ? "row-crisis" : ""}>
                  <td>{c.company_name}</td>
                  <td>
                    <span className={`badge badge-status-${c.relationship_status.replace(/_/g, "-")}`}>
                      {c.relationship_status}
                    </span>
                  </td>
                  <td>{c.deal_size !== null ? `$${c.deal_size.toFixed(2)}` : "—"}</td>
                  <td>{c.sales_rep ?? "—"}</td>
                  <td>{c.support_rep ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>Revenue by Customer</h2>
        {revenue?.error && <ErrorBanner message={revenue.error} />}
        {revenue && revenue.revenue_by_customer.length > 0 && (
          <div style={{ width: "100%", height: 320 }}>
            <ResponsiveContainer>
              <BarChart data={revenue.revenue_by_customer}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2e37" />
                <XAxis dataKey="company_name" tick={{ fill: "#b7bdc9", fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={70} />
                <YAxis tick={{ fill: "#b7bdc9", fontSize: 11 }} />
                <Tooltip contentStyle={{ background: "#171a21", border: "1px solid #2a2e37" }} />
                <Bar dataKey="revenue" fill="#2f6fed" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
        {revenue && revenue.revenue_by_customer.length === 0 && !revenue.error && (
          <p className="hint">No customers with posted revenue yet.</p>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Phase 35: KPI / Performance tab
// ---------------------------------------------------------------------------
function KpiTab() {
  const [deptScoreboard, setDeptScoreboard] = useState<KpiDepartmentScoreboard | null>(null);
  const [empScoreboard, setEmpScoreboard] = useState<KpiEmployeeScoreboard | null>(null);
  const [reviewLog, setReviewLog] = useState<KpiReviewLog | null>(null);
  const [approvalMode, setApprovalMode] = useState<boolean | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [toggling, setToggling] = useState(false);
  const [empSortMetric, setEmpSortMetric] = useState<string>("");

  const load = () => {
    api.kpiDepartmentScoreboard().then(setDeptScoreboard).catch((e) => setErr(String(e)));
    api.kpiEmployeeScoreboard().then((d) => {
      setEmpScoreboard(d);
      // Default to whatever metric actually has data — a hardcoded default
      // (e.g. "tickets_resolved") can legitimately have zero rows in a given
      // lookback window while the dropdown still visually shows its first
      // option, which reads as a bug even though it's a filter mismatch.
      setEmpSortMetric((current) => {
        const metrics = Array.from(new Set(d.rows.map((r) => r.metric))).sort();
        return current && metrics.includes(current) ? current : metrics[0] ?? "";
      });
    }).catch((e) => setErr(String(e)));
    api.kpiReviewLog().then(setReviewLog).catch((e) => setErr(String(e)));
    api.kpiReviewMode().then((r) => setApprovalMode(r.approval_mode)).catch((e) => setErr(String(e)));
  };

  useEffect(() => {
    load();
  }, []);

  const toggleMode = async () => {
    if (approvalMode === null) return;
    setToggling(true);
    try {
      const r = await api.kpiSetReviewMode(!approvalMode);
      setApprovalMode(r.approval_mode);
    } catch (e) {
      setErr(String(e));
    } finally {
      setToggling(false);
    }
  };

  const empRows = useMemo(() => {
    if (!empScoreboard) return [];
    return empScoreboard.rows
      .filter((r) => r.metric === empSortMetric)
      .sort((a, b) => b.total - a.total);
  }, [empScoreboard, empSortMetric]);

  const availableMetrics = useMemo(() => {
    if (!empScoreboard) return [];
    return Array.from(new Set(empScoreboard.rows.map((r) => r.metric))).sort();
  }, [empScoreboard]);

  return (
    <section>
      <h1>KPI / Performance</h1>
      {err && <ErrorBanner message={err} />}

      <div className="card">
        <h2>Automatic vs. Review &amp; Approve Mode</h2>
        <p className="hint">
          When on, performance-review raises are queued into the expense-approval queue instead of
          applying immediately. Writes to kpi-engine's kpi_engine_config table — takes effect
          immediately, no container restart needed.
        </p>
        {approvalMode !== null && (
          <div className="stat-row">
            <div className="stat">
              <div className="stat-label">Current mode</div>
              <div className="stat-value">{approvalMode ? "Review & Approve" : "Automatic"}</div>
            </div>
            <button className="action-btn" disabled={toggling} onClick={toggleMode}>
              {toggling ? "Switching..." : `Switch to ${approvalMode ? "Automatic" : "Review & Approve"}`}
            </button>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Department Scoreboard ({deptScoreboard?.lookback_days ?? 30}-day lookback)</h2>
        {deptScoreboard && (
          <table className="table">
            <thead>
              <tr>
                <th>Department</th>
                <th>Metric</th>
                <th>Total</th>
                <th>Avg (daily)</th>
              </tr>
            </thead>
            <tbody>
              {deptScoreboard.rows.map((r, i) => (
                <tr key={i}>
                  <td>{r.department}</td>
                  <td>{r.metric}</td>
                  <td>{r.total.toFixed(2)}</td>
                  <td>{r.avg.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <div className="card-header-row">
          <h2>Employee Scoreboard</h2>
          <select
            className="form-input form-input-small"
            value={empSortMetric}
            onChange={(e) => setEmpSortMetric(e.target.value)}
          >
            {availableMetrics.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Department</th>
              <th>Metric</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {empRows.map((r) => (
              <tr key={r.employee_id}>
                <td>{r.name}</td>
                <td>{r.department}</td>
                <td>{r.metric}</td>
                <td>{r.total.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>Performance-Review Log ({reviewLog?.reviews.length ?? 0})</h2>
        {reviewLog && (
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Tier</th>
                <th>Action</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {reviewLog.reviews.map((r) => (
                <tr key={r.id}>
                  <td>{new Date(r.created_at).toLocaleString()}</td>
                  <td>
                    <span className={`badge badge-status-${r.tier === "top_quartile" ? "active" : r.tier === "second_quartile" ? "on-pto" : "vacant"}`}>
                      {r.tier}
                    </span>
                  </td>
                  <td>{r.action}</td>
                  <td>
                    {r.detail.new_pay !== undefined ? `$${r.detail.new_pay}` : ""}
                    {r.detail.reason ? ` (${r.detail.reason})` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Phase 35: Company Direction tab
// ---------------------------------------------------------------------------
function CompanyDirectionTab() {
  const [current, setCurrent] = useState<CompanyDirectiveCurrent | null>(null);
  const [history, setHistory] = useState<CompanyDirectiveHistory | null>(null);
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const load = () => {
    api.companyDirectionCurrent().then((d) => {
      setCurrent(d);
      if (d.current) setText(d.current.content);
    }).catch((e) => setErr(String(e)));
    api.companyDirectionHistory().then(setHistory).catch((e) => setErr(String(e)));
  };

  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    setBusy(true);
    setSaveMsg(null);
    try {
      const r: any = await api.companyDirectionSave(text);
      if (r.wiki_sync_error) {
        setSaveMsg(`Saved as version ${r.version}, but Wiki.js sync failed: ${r.wiki_sync_error}`);
      } else {
        setSaveMsg(`Saved as version ${r.version} — Wiki.js pinned page synced.`);
      }
      load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <h1>Company Direction</h1>
      {err && <ErrorBanner message={err} />}
      {saveMsg && <div className="toast">{saveMsg}</div>}

      <div className="card">
        <h2>Current Directive {current?.current ? `(version ${current.current.version})` : ""}</h2>
        <textarea
          className="form-input"
          style={{ minHeight: 160, resize: "vertical" }}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button className="action-btn" disabled={busy || !text.trim()} onClick={save}>
          {busy ? "Saving..." : "Save"}
        </button>
        <p className="hint">
          Saving writes a new version to company_directives (previous version marked not-current —
          nothing is overwritten) and syncs the "Company Direction" pinned Wiki.js page.
        </p>
      </div>

      <div className="card">
        <div className="card-header-row">
          <h2>History ({history?.history.length ?? 0} versions)</h2>
          <button className="action-btn" onClick={() => setShowHistory((s) => !s)}>
            {showHistory ? "Hide" : "Show"}
          </button>
        </div>
        {showHistory && history && (
          <table className="table">
            <thead>
              <tr>
                <th>Version</th>
                <th>When</th>
                <th>By</th>
                <th>Content</th>
              </tr>
            </thead>
            <tbody>
              {history.history.map((h) => (
                <tr key={h.id} className={h.is_current ? "row-pto" : ""}>
                  <td>{h.version}{h.is_current ? " (current)" : ""}</td>
                  <td>{new Date(h.created_at).toLocaleString()}</td>
                  <td>{h.created_by}</td>
                  <td>{h.content.slice(0, 160)}{h.content.length > 160 ? "…" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
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
