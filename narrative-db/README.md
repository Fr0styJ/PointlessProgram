# narrative-db/

**Populated by:** Phase 13 — Narrative DB core schema (core tables) + additive phases for deferred tables

This directory will contain PostgreSQL migrations for every table in the spec (spec §4.1, §5,
§8, §9, §11, §12, §15, §19).

**Tables created in Phase 13 (core — 8 tables):**
- `narrative_threads` — id, topic, department, status, summary, created_at, updated_at (sim-time)
- `narrative_events` — id, thread_id, employee_id (nullable), origin (`ai`/`human`/`external`), source_type, source_ref, short_summary, created_at
- `meetings` — id, thread_id, meeting_type, attendees (json), agenda, transcript_summary, decisions (json), outcome (json), created_at
- `action_items` — id, meeting_id (nullable), thread_id, owner_employee_id, description, due_at, status, resulting_event_ids (json)
- `pending_reactions` — id, thread_id, target_employee_id, triggering_event_id, status
- `pending_approvals` — id, expense_request_ref, requester_employee_id, approver_employee_id (nullable), approver_is_principal (boolean), amount, status (SPEC_CLARIFICATIONS #1)
- `system_audit_log` — id, actor, action, detail, created_at (NO FK/CASCADE that would allow delete via other tables)
- `company_directives` — versioned current direction statement

**Tables created in later phases (deferred to keep Phase 13 blast radius small):**
- `employee_relationships` — Phase 20
- `pto_calendar` — Phase 19
- `market_benchmark` — Phase 21
- `customers` — Phase 22
- `kpi_snapshots` — Phase 23

**Also contains:**
- `employees` roster table (created in Phase 14)
- `sim_clock` table (created in Phase 12)

**CRITICAL:** `system_audit_log` must have NO foreign key or cascade relationship that would
allow a delete against any other table to remove audit rows. Verified in Phase 13 exit criteria.

**Dependencies:** Phase 1 (Postgres).
