# accounting-engine/

**Populated by:** Phase 15 — Deterministic accounting engine

This directory will contain the Accounting Engine service: deterministic approval routing,
payroll runs, revenue posting, and the Books Auditor (spec §10.1–10.4).

**Critical principle:** ALL financial math is deterministic code — NEVER the LLM. Balances,
thresholds, payroll totals, burn rate, revenue postings — all plain backend logic. The LLM
only narrates around numbers already decided by code.

**Key responsibilities:**
- Expense approval workflow: deterministic routing per approval_policy table (§10.2)
- Payroll runs: posts aggregate transaction to Akaunting per cycle (SPEC_CLARIFICATIONS #2)
- Revenue posting: posts real revenue transactions to Akaunting when deals close (§11.2)
- Books Auditor: reconciles debits/credits, posts "audit correction" transactions (§10.4)
- Idempotency keys on all money-posting operations (§23)

**Approval tiers (§10.2):**
- Individual contributor: auto-approve ≤$25, escalate to department lead
- Department lead (is_lead=true): auto-approve ≤$500, escalate to Principal
- Principal: unlimited final approver

**Schema dependencies:** `pending_approvals`, `employees` (with `is_lead`/`role_tier`), `system_audit_log`
**Appliance dependencies:** Phase 6 (Zammad for expense_request tickets), Phase 9 (Akaunting)

**Pay cut path:** stubbed in Phase 15 (queues with "requires pay_negotiation meeting" placeholder);
fully wired in Phase 24 (meeting simulator extension).

**Dependencies:** Phases 6, 9, 13, 14.
