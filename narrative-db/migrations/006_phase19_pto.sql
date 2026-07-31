-- ---------------------------------------------------------------------------
-- Phase 19: PTO / out-of-office — approval-delegation support column
-- Spec §10.2 + §15: when an approver is on PTO, route to a configured backup
-- approver instead of stalling. Nullable — most employees have none, in which
-- case accounting-engine falls back to escalating one tier (existing 10.2
-- logic), matching PLAN_REMAINING_PHASES.md's Phase 19 item 5.
-- ---------------------------------------------------------------------------
ALTER TABLE employees
    ADD COLUMN IF NOT EXISTS backup_approver_id BIGINT REFERENCES employees (id);

CREATE INDEX IF NOT EXISTS idx_employees_backup_approver ON employees (backup_approver_id);
