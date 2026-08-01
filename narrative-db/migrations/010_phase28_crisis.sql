-- ---------------------------------------------------------------------------
-- Phase 28: Chaos — crisis events
--
-- 1. narrative_threads.priority: user's 2026-07-31 sign-off (delegated to
--    implementer judgment, PLAN_PHASES_27_28_31_32.md) — no priority/urgency
--    column existed on narrative_threads (checked 002_narrative_core.sql
--    through 009_phase27_pending_actions.sql, confirmed absent). Adding it
--    keeps crisis threads visibly distinct from routine ones (better UX once
--    dashboards exist, e.g. Phase 31/33+). Default 0 (routine); existing rows
--    backfilled to 0 explicitly. Orchestrator's /chaos/trigger-event sets 100
--    for any crisis-typed thread it creates.
--
-- 2. narrative_events.source_type: widen additively (same pattern as
--    009's 'outage' addition) to add 'crisis' so the trigger-event log entry
--    doesn't have to masquerade as 'external'/'meeting' sourced content.
-- ---------------------------------------------------------------------------

ALTER TABLE narrative_threads ADD COLUMN IF NOT EXISTS priority SMALLINT NOT NULL DEFAULT 0;

-- Explicit backfill for any pre-existing rows (defensive: DEFAULT already covers
-- new inserts, but a column added to a populated table should still get an
-- explicit backfill statement per this repo's migration convention).
UPDATE narrative_threads SET priority = 0 WHERE priority IS NULL;

COMMENT ON COLUMN narrative_threads.priority IS
    'Higher = more urgent. 0 = routine (default/backfilled). Phase 28 crisis threads use 100.';

CREATE INDEX IF NOT EXISTS idx_narrative_threads_priority ON narrative_threads (priority DESC);

DO $$
BEGIN
    ALTER TABLE narrative_events DROP CONSTRAINT IF EXISTS narrative_events_source_type_check;
    ALTER TABLE narrative_events ADD CONSTRAINT narrative_events_source_type_check
        CHECK (source_type IN (
            'meeting', 'email', 'chat', 'ticket', 'wiki',
            'payroll_change', 'approval', 'customer', 'external', 'outage', 'crisis'
        ));
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;
