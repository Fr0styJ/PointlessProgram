// Thin fetch wrapper for the dashboard BFF. The browser sends Basic Auth
// credentials automatically once the user answers the browser's native auth
// prompt (triggered by the BFF's 401 + WWW-Authenticate header) — no client-
// side credential handling needed here.

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export interface SimClockState {
  sim_time: string;
  last_wall_checkpoint: number;
  speed_multiplier: number;
  wall_time_utc: string;
}

export interface TickStatus {
  paused: boolean;
  paused_since: string | null;
  last_tick_at: string | null;
  tick_interval_seconds: number;
}

export interface SimulationStatus {
  sim_clock: SimClockState | null;
  sim_clock_error: string | null;
  tick: TickStatus | null;
  tick_error: string | null;
}

export interface LlmStatus {
  provider_config: {
    tiers?: Record<string, string[]>;
    model_group_alias?: Record<string, string>;
    fallbacks?: unknown[];
    num_retries?: number;
    error?: string;
  };
  speed_multiplier: number;
}

export interface LlmSpend {
  total_spend: number;
  total_tokens: number;
  spend_per_wallclock_hour: number;
  speed_multiplier: number;
  burn_per_sim_hour: number;
  by_model: { model: string; calls: number; tokens: number; spend: number }[];
}

export interface NarrativeThread {
  id: number;
  topic: string;
  department: string | null;
  status: string;
  summary: string | null;
  priority: number;
  created_at: string;
  updated_at: string;
}

export interface ActionItem {
  id: number;
  meeting_id: number | null;
  thread_id: number;
  owner_employee_id: number;
  description: string;
  due_at: string | null;
  status: string;
}

export interface PendingReaction {
  id: number;
  thread_id: number;
  target_employee_id: number;
  triggering_event_id: number | null;
  status: string;
}

export interface PendingApproval {
  id: number;
  expense_request_ref: string;
  requester_employee_id: number;
  approver_employee_id: number | null;
  approver_is_principal: boolean;
  amount: string;
  status: string;
  created_at: string;
}

export interface MeetingRow {
  id: number;
  thread_id: number | null;
  meeting_type: string;
  attendees: number[];
  created_at: string;
}

export interface NarrativeSummary {
  threads: NarrativeThread[];
  action_items: ActionItem[];
  pending_reactions: PendingReaction[];
  pending_approvals: PendingApproval[];
  meetings: MeetingRow[];
  pending_actions: {
    retry_queue_depth: number;
    recent: {
      id: number;
      action_type: string;
      target_service: string;
      status: string;
      attempts: number;
      next_retry_at: string | null;
      last_error: string | null;
    }[];
  };
}

// ---------------------------------------------------------------------------
// Phase 34: HR / Payroll / Accounting types
// ---------------------------------------------------------------------------
export interface EmployeeRosterRow {
  id: number;
  name: string;
  department: string;
  role: string;
  role_tier: string;
  status: string;
  display_status: string;
  hired_at: string;
  terminated_at: string | null;
  pay_rate: number;
  pay_frequency: string;
  on_pto: boolean;
}

export interface HrRoster {
  employees: EmployeeRosterRow[];
}

export interface RelationshipNode {
  id: number;
  name: string;
  department: string;
  status: string;
}

export interface RelationshipEdge {
  employee_a_id: number;
  employee_b_id: number;
  relationship_type: string;
  affinity_score: number;
  a_name: string;
  b_name: string;
}

export interface HrRelationships {
  nodes: RelationshipNode[];
  edges: RelationshipEdge[];
}

export interface PayrollEmployeeRow {
  id: number;
  name: string;
  department: string;
  role: string;
  role_tier: string;
  status: string;
  pay_rate: number;
  pay_frequency: string;
  pay_last_changed_at: string | null;
  pay_last_change_reason: string | null;
}

export interface PayrollRoster {
  employees: PayrollEmployeeRow[];
}

export interface PayrollHistoryEntry {
  id: number;
  actor: string;
  action: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface PayrollHistory {
  history: PayrollHistoryEntry[];
}

export interface AccountingSummary {
  cash: {
    cash_balance: number | null;
    accounts: { name: string; balance: number }[];
    error: string | null;
  };
  akaunting_deep_link: string;
  pending_approvals: {
    id: number;
    expense_request_ref: string;
    requester_employee_id: number;
    approver_employee_id: number | null;
    approver_is_principal: boolean;
    amount: string;
    status: string;
    created_at: string;
  }[];
  audit_log: PayrollHistoryEntry[];
}

// ---------------------------------------------------------------------------
// Phase 35: External World / KPI / Company Direction types
// ---------------------------------------------------------------------------
export interface ExternalWorldNewsEntry {
  id: number;
  actor: string;
  action: string;
  detail: Record<string, any>;
  created_at: string;
  category: "job_offer_resignation" | "pay_gap_flag";
}

export interface ExternalWorldNews {
  news: ExternalWorldNewsEntry[];
}

export interface CustomerRow {
  id: number;
  company_name: string;
  contact_name: string;
  contact_email: string;
  relationship_status: string;
  deal_size: number | null;
  akaunting_transaction_id: string | null;
  support_sla_hours: number;
  created_at: string;
  sales_rep: string | null;
  support_rep: string | null;
}

export interface ExternalWorldCustomers {
  customers: CustomerRow[];
}

export interface RevenueByCustomerRow {
  customer_id: number;
  company_name: string;
  relationship_status: string;
  revenue: number;
}

export interface RevenueByCustomer {
  revenue_by_customer: RevenueByCustomerRow[];
  error: string | null;
}

export interface KpiScoreRow {
  metric: string;
  total: number;
  avg: number;
}

export interface KpiDepartmentRow extends KpiScoreRow {
  department: string;
}

export interface KpiEmployeeRow extends KpiScoreRow {
  employee_id: number;
  name: string;
  department: string;
}

export interface KpiDepartmentScoreboard {
  lookback_days: number;
  rows: KpiDepartmentRow[];
}

export interface KpiEmployeeScoreboard {
  lookback_days: number;
  rows: KpiEmployeeRow[];
}

export interface KpiReviewLogEntry {
  id: number;
  actor: string;
  action: string;
  detail: Record<string, any>;
  created_at: string;
  tier: string;
}

export interface KpiReviewLog {
  reviews: KpiReviewLogEntry[];
}

export interface KpiReviewMode {
  approval_mode: boolean;
}

export interface CompanyDirective {
  id: number;
  content: string;
  version: number;
  created_at: string;
  created_by: string;
}

export interface CompanyDirectiveCurrent {
  current: CompanyDirective | null;
}

export interface CompanyDirectiveHistoryEntry extends CompanyDirective {
  is_current: boolean;
}

export interface CompanyDirectiveHistory {
  history: CompanyDirectiveHistoryEntry[];
}

// ---------------------------------------------------------------------------
// Phase 36: Chaos / Data Management / Branding + Settings full-purge types
// ---------------------------------------------------------------------------
export interface ChaosContainerStatus {
  name: string;
  state: string;
  status: string;
}

export interface ChaosStatus {
  containers: ChaosContainerStatus[];
}

export interface ChaosOutageEntry {
  id: number;
  source_ref: string;
  short_summary: string;
  created_at: string;
}

export interface ChaosOutages {
  outages: ChaosOutageEntry[];
}

export interface TriggerEventResult {
  status: string;
  scenario: string;
  thread_id: number;
  forced_attendee_ids: number[];
  audit_result: Record<string, unknown> | null;
  meeting_result: Record<string, unknown> | null;
  expense_result: Record<string, unknown> | null;
}

export interface DataManagementScope {
  scope: string;
  label: string;
  confirm_phrase: string;
}

export interface DataManagementScopes {
  scopes: DataManagementScope[];
}

export interface SnapshotManifest {
  snapshot_name: string;
  wall_clock_captured_at: string;
  sim_state: Record<string, unknown>;
  artifacts: Record<string, { size_bytes: number; sha256: string }>;
  total_size_bytes: number;
}

export interface SnapshotList {
  snapshots: SnapshotManifest[];
}

export interface BrandingAssets {
  avatars: string[];
  emoji: string[];
}

export interface EmployeeBranding {
  employee_id: number;
  avatar_asset_id: string | null;
  updated_at: string | null;
}

export interface LastSnapshotInfo {
  last_snapshot: SnapshotManifest | null;
  error: string | null;
}

export const api = {
  simulationStatus: () => apiFetch<SimulationStatus>("/api/simulation/status"),
  tickPause: () => apiFetch("/api/simulation/tick/pause", { method: "POST" }),
  tickResume: () => apiFetch("/api/simulation/tick/resume", { method: "POST" }),
  llmStatus: () => apiFetch<LlmStatus>("/api/llm/status"),
  llmSpend: () => apiFetch<LlmSpend>("/api/llm/spend"),
  narrativeSummary: () => apiFetch<NarrativeSummary>("/api/narrative/summary"),

  // Phase 34
  hrRoster: () => apiFetch<HrRoster>("/api/hr/roster"),
  hrRelationships: () => apiFetch<HrRelationships>("/api/hr/relationships"),
  hrHire: (body: { name: string; department: string; title: string; role_tier: string }) =>
    apiFetch("/api/hr/employees/hire", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  hrFire: (employeeId: number) =>
    apiFetch(`/api/hr/employees/${employeeId}/fire`, { method: "POST" }),

  payrollRoster: () => apiFetch<PayrollRoster>("/api/payroll/roster"),
  payrollHistory: () => apiFetch<PayrollHistory>("/api/payroll/history"),
  payrollRaise: (body: { employee_id: number; new_pay: number; reason: string }) =>
    apiFetch("/api/payroll/raise", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  accountingSummary: () => apiFetch<AccountingSummary>("/api/accounting/summary"),
  accountingApprove: (approval_id: number) =>
    apiFetch("/api/accounting/expense/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_id, actor: "principal" }),
    }),
  accountingReject: (approval_id: number) =>
    apiFetch("/api/accounting/expense/reject", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_id, actor: "principal" }),
    }),

  // Phase 35
  externalWorldNews: () => apiFetch<ExternalWorldNews>("/api/external-world/news"),
  externalWorldCustomers: () => apiFetch<ExternalWorldCustomers>("/api/external-world/customers"),
  externalWorldRevenueByCustomer: () =>
    apiFetch<RevenueByCustomer>("/api/external-world/revenue-by-customer"),

  kpiDepartmentScoreboard: () => apiFetch<KpiDepartmentScoreboard>("/api/kpi/department-scoreboard"),
  kpiEmployeeScoreboard: () => apiFetch<KpiEmployeeScoreboard>("/api/kpi/employee-scoreboard"),
  kpiReviewLog: () => apiFetch<KpiReviewLog>("/api/kpi/review-log"),
  kpiReviewMode: () => apiFetch<KpiReviewMode>("/api/kpi/review-mode"),
  kpiSetReviewMode: (enabled: boolean) =>
    apiFetch<KpiReviewMode>("/api/kpi/review-mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }),

  companyDirectionCurrent: () => apiFetch<CompanyDirectiveCurrent>("/api/company-direction/current"),
  companyDirectionHistory: () => apiFetch<CompanyDirectiveHistory>("/api/company-direction/history"),
  companyDirectionSave: (content: string) =>
    apiFetch("/api/company-direction/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    }),

  // Phase 36: Chaos tab
  chaosStatus: () => apiFetch<ChaosStatus>("/api/chaos/status"),
  chaosOutages: () => apiFetch<ChaosOutages>("/api/chaos/outages"),
  chaosApplianceAction: (name: string, action: "stop" | "start" | "restart") =>
    apiFetch(`/api/chaos/appliances/${name}/${action}`, { method: "POST" }),
  chaosTriggerEvent: (body: { scenario: string; custom_text?: string }) =>
    apiFetch<TriggerEventResult>("/api/chaos/trigger-event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  // Phase 36: Data Management tab (scoped purge + snapshots — full purge lives
  // under Settings, see below)
  dataManagementScopes: () => apiFetch<DataManagementScopes>("/api/data-management/scopes"),
  dataManagementPurgeScope: (scope: string, confirm: string) =>
    apiFetch("/api/data-management/purge-scope", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope, confirm }),
    }),
  dataManagementSnapshots: () => apiFetch<SnapshotList>("/api/data-management/snapshots"),
  dataManagementSnapshotSave: (label?: string) =>
    apiFetch<SnapshotManifest>("/api/data-management/snapshots/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: label ?? null }),
    }),
  dataManagementSnapshotRestore: (snapshot_name: string, confirm: string) =>
    apiFetch("/api/data-management/snapshots/restore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ snapshot_name, confirm }),
    }),
  dataManagementSnapshotDelete: (snapshot_name: string) =>
    apiFetch(`/api/data-management/snapshots/${snapshot_name}`, { method: "DELETE" }),

  // Phase 36: Branding tab
  brandingAssets: () => apiFetch<BrandingAssets>("/api/branding/assets"),
  brandingEmployee: (employeeId: number) =>
    apiFetch<EmployeeBranding>(`/api/branding/employee/${employeeId}`),
  brandingApply: (employee_id: number, asset_id: string) =>
    apiFetch("/api/branding/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ employee_id, asset_id }),
    }),
  brandingBulkApply: (body: { employee_ids: number[]; mode: string; asset_id?: string }) =>
    apiFetch("/api/branding/bulk-apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  // Phase 36/38: Settings' "nuclear launch" full-purge control.
  settingsLastSnapshot: () => apiFetch<LastSnapshotInfo>("/api/settings/full-purge/last-snapshot"),
  settingsFullPurge: (confirm: string) =>
    apiFetch("/api/settings/full-purge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm }),
    }),
};
