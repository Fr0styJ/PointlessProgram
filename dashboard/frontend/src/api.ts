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
};
