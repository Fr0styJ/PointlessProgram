-- ---------------------------------------------------------------------------
-- Phase 27: Chaos — service availability controls
--
-- pending_actions: the orchestrator retry queue that Phase 18's spec (§13.1,
-- PHASES.md:390) assumed already existed but did not (see
-- PLAN_PHASES_27_28_31_32.md, Phase 27 §2). Any outbound call the orchestrator
-- makes (to sim-clock, meeting-simulator, accounting-engine, kpi-engine,
-- external-world, or an appliance API) that fails with a connection error gets
-- queued here instead of raising, and is retried on a wall-clock schedule
-- (next_retry_at is timestamptz, NOT sim-time — a container being down is a
-- physical fact independent of sim speed, per spec §13.1's explicit
-- "wall-clock-based retry" instruction).
--
-- idempotency_key is UNIQUE and required on every row, per the user's
-- 2026-07-31 sign-off recorded in PLAN_PHASES_27_28_31_32.md: idempotency
-- keys apply to ALL pending_actions types, not just money-touching ones
-- (simpler, consistent, negligible overhead) — not scoped down to a subset.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS pending_actions (
    id              BIGSERIAL   PRIMARY KEY,
    action_type     TEXT        NOT NULL,   -- e.g. 'orchestrator_call', 'chaos_stop', 'chaos_start', 'chaos_restart'
    target_service  TEXT        NOT NULL,   -- e.g. 'meeting-simulator', 'accounting-engine', 'mattermost'
    payload         JSONB       NOT NULL DEFAULT '{}',
    idempotency_key TEXT        NOT NULL UNIQUE,
    status          TEXT        NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'retrying', 'done', 'failed')),
    attempts        INT         NOT NULL DEFAULT 0,
    next_retry_at   TIMESTAMPTZ NOT NULL DEFAULT now(),  -- wall-clock, not sim-time
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error      TEXT
);

CREATE INDEX IF NOT EXISTS idx_pending_actions_status_retry
    ON pending_actions (status, next_retry_at);
CREATE INDEX IF NOT EXISTS idx_pending_actions_idempotency_key
    ON pending_actions (idempotency_key);

-- Outage/retry narrative events reuse the existing narrative_events table
-- (no dedicated outage table needed — spec doesn't ask for one, only that
-- outages get logged as narrative_events). Widen the existing check
-- constraints additively so an outage event doesn't have to masquerade as
-- 'external'/'customer' sourced content.
DO $$
BEGIN
    ALTER TABLE narrative_events DROP CONSTRAINT IF EXISTS narrative_events_source_type_check;
    ALTER TABLE narrative_events ADD CONSTRAINT narrative_events_source_type_check
        CHECK (source_type IN (
            'meeting', 'email', 'chat', 'ticket', 'wiki',
            'payroll_change', 'approval', 'customer', 'external', 'outage'
        ));
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE narrative_events DROP CONSTRAINT IF EXISTS narrative_events_origin_check;
    ALTER TABLE narrative_events ADD CONSTRAINT narrative_events_origin_check
        CHECK (origin IN ('ai', 'human', 'external', 'system'));
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;
