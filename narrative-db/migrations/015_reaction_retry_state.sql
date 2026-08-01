-- Migration: 015_reaction_retry_state.sql
-- Persistent bounded retry state for Principal reaction delivery.

ALTER TABLE pending_reactions
    ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_error TEXT,
    ADD COLUMN IF NOT EXISTS failed_at TIMESTAMPTZ;

ALTER TABLE pending_reactions
    DROP CONSTRAINT IF EXISTS pending_reactions_status_check;

ALTER TABLE pending_reactions
    ADD CONSTRAINT pending_reactions_status_check
    CHECK (status IN ('pending', 'done', 'failed'));

CREATE INDEX IF NOT EXISTS idx_pending_reactions_retry
    ON pending_reactions (next_retry_at, id)
    WHERE status = 'pending';
