-- ---------------------------------------------------------------------------
-- Phase 29: Purge & snapshots — maintenance-mode flag + snapshot/purge audit log
--
-- Two small dedicated tables (not reusing company_directives, per Phase 29's
-- explicit "your call" note in the build instructions — a dedicated table is
-- cleaner than overloading a table that already has an unrelated meaning):
--
-- 1. system_maintenance_mode: single-row (id=1) flag. orchestrator's tick loop
--    checks `enabled` before firing any scheduled job (see orchestrator/main.py
--    tick_loop). snapshot-manager and purge-manager set it true before any
--    destructive/consistency-sensitive operation and clear it after, alongside
--    pausing sim-clock. Deliberately separate from sim-clock's own speed=0
--    concept since orchestrator's tick loop and sim-clock's speed setting are
--    logically separate concerns (PHASE29_PLAN.md §3).
--
-- 2. snapshot_purge_log: append-only audit trail of every snapshot save/restore
--    and every purge operation (scoped or full), independent of and NOT
--    overlapping with system_audit_log (which stays excluded from purge/
--    snapshot capture entirely, per prior sign-off in BUILD_LOG.md). This one
--    IS itself excluded from purge/restore scope for the same reason audit
--    log is: we always want a record that a purge/restore happened, even
--    across a restore that rewinds everything else.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS system_maintenance_mode (
    id          INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),  -- single row only
    enabled     BOOLEAN NOT NULL DEFAULT FALSE,
    reason      TEXT,
    set_by      TEXT,               -- 'snapshot-manager' | 'purge-manager'
    set_at      TIMESTAMPTZ,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO system_maintenance_mode (id, enabled)
VALUES (1, FALSE)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS snapshot_purge_log (
    id              BIGSERIAL PRIMARY KEY,
    operation       TEXT NOT NULL,      -- 'snapshot_save' | 'snapshot_restore' | 'purge_scope' | 'purge_full'
    scope           TEXT,               -- purge scope name, or NULL for snapshot ops / full purge
    snapshot_name   TEXT,               -- snapshot directory name involved, if any
    status          TEXT NOT NULL,      -- 'started' | 'succeeded' | 'failed'
    detail          JSONB,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_snapshot_purge_log_started ON snapshot_purge_log (started_at DESC);
