-- Migration: 013_deliverable_retry_state.sql
-- Feature: bounded, persistent retry state for narrative-driven deliverables.

ALTER TABLE action_items
    ADD COLUMN IF NOT EXISTS deliverable_attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS deliverable_next_retry_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS deliverable_last_error TEXT,
    ADD COLUMN IF NOT EXISTS deliverable_failed_at TIMESTAMPTZ;

ALTER TABLE action_items
    DROP CONSTRAINT IF EXISTS action_items_status_check;

ALTER TABLE action_items
    ADD CONSTRAINT action_items_status_check
    CHECK (status IN ('open', 'done', 'overdue', 'orphaned', 'failed'));

CREATE INDEX IF NOT EXISTS idx_action_items_deliverable_retry
    ON action_items (deliverable_next_retry_at, id)
    WHERE deliverable_type IS NOT NULL
      AND deliverable_url IS NULL
      AND status = 'open';

COMMENT ON COLUMN action_items.deliverable_attempts IS
    'Number of consecutive failed artifact-fulfillment attempts.';

COMMENT ON COLUMN action_items.deliverable_next_retry_at IS
    'Wall-clock time after which human-bridge may retry artifact fulfillment.';

COMMENT ON COLUMN action_items.deliverable_last_error IS
    'Most recent artifact-fulfillment error, retained for diagnosis.';

COMMENT ON COLUMN action_items.deliverable_failed_at IS
    'Wall-clock timestamp when bounded artifact retries were exhausted.';
