-- Migration: 002_narrative_core.sql
-- Phase 13: Core narrative schema (8 tables)
-- Spec §4.1 + SPEC_CLARIFICATIONS
--
-- Tables created here (Phase 13 core set):
--   narrative_threads, narrative_events, meetings, action_items,
--   pending_reactions, pending_approvals, system_audit_log, company_directives
--
-- Tables DEFERRED to their introducing phase (per PHASES.md §Phase 13 note):
--   employee_relationships  → Phase 20
--   pto_calendar            → Phase 19
--   market_benchmark        → Phase 21
--   customers               → Phase 22
--   kpi_snapshots           → Phase 23
--
-- CRITICAL: system_audit_log has NO FK or CASCADE to any other table.
--   A delete against any other table MUST NOT remove audit rows.
--   This is the load-bearing guarantee for spec §14.3.

-- ---------------------------------------------------------------------------
-- narrative_threads
-- Spec §4.1: id, topic, department, status, summary, created_at, updated_at (sim-time)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS narrative_threads (
    id          BIGSERIAL PRIMARY KEY,
    topic       TEXT        NOT NULL,
    department  TEXT,
    status      TEXT        NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'in_progress', 'resolved', 'archived')),
    summary     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- sim-time at creation
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()   -- sim-time at last update
);

CREATE INDEX IF NOT EXISTS idx_narrative_threads_status     ON narrative_threads (status);
CREATE INDEX IF NOT EXISTS idx_narrative_threads_department ON narrative_threads (department);
CREATE INDEX IF NOT EXISTS idx_narrative_threads_updated_at ON narrative_threads (updated_at DESC);

-- ---------------------------------------------------------------------------
-- narrative_events
-- Spec §4.1: id, thread_id, employee_id (nullable), origin, source_type, source_ref,
--             short_summary, created_at
-- SPEC_CLARIFICATIONS #9: origin enum adds 'external' for BetaCorp/customer traffic
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS narrative_events (
    id            BIGSERIAL   PRIMARY KEY,
    thread_id     BIGINT      REFERENCES narrative_threads (id) ON DELETE CASCADE,
    employee_id   BIGINT,     -- nullable; FK to employees added in Phase 14 migration
    origin        TEXT        NOT NULL
                  CHECK (origin IN ('ai', 'human', 'external')),
    source_type   TEXT        NOT NULL
                  CHECK (source_type IN (
                      'meeting', 'email', 'chat', 'ticket', 'wiki',
                      'payroll_change', 'approval', 'customer', 'external'
                  )),
    source_ref    TEXT,       -- external ID (e.g. Mattermost message ID, Zammad ticket ID)
    short_summary TEXT        NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()  -- sim-time
);

CREATE INDEX IF NOT EXISTS idx_narrative_events_thread_id   ON narrative_events (thread_id);
CREATE INDEX IF NOT EXISTS idx_narrative_events_employee_id ON narrative_events (employee_id);
CREATE INDEX IF NOT EXISTS idx_narrative_events_origin      ON narrative_events (origin);
CREATE INDEX IF NOT EXISTS idx_narrative_events_created_at  ON narrative_events (created_at DESC);

-- ---------------------------------------------------------------------------
-- meetings
-- Spec §4.1: id, thread_id, meeting_type, attendees (json), agenda,
--             transcript_summary, decisions (json), outcome (json), created_at
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meetings (
    id                  BIGSERIAL   PRIMARY KEY,
    thread_id           BIGINT      REFERENCES narrative_threads (id) ON DELETE SET NULL,
    meeting_type        TEXT        NOT NULL
                        CHECK (meeting_type IN (
                            'standup', 'cross_functional', 'pay_negotiation',
                            'performance_review', 'crisis_response'
                        )),
    attendees           JSONB       NOT NULL DEFAULT '[]',  -- array of employee_ids
    agenda              TEXT,
    transcript_summary  TEXT,
    decisions           JSONB       NOT NULL DEFAULT '[]',  -- array of decision strings
    outcome             JSONB,                              -- structured: type-specific result
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()  -- sim-time
);

CREATE INDEX IF NOT EXISTS idx_meetings_thread_id    ON meetings (thread_id);
CREATE INDEX IF NOT EXISTS idx_meetings_meeting_type ON meetings (meeting_type);
CREATE INDEX IF NOT EXISTS idx_meetings_created_at   ON meetings (created_at DESC);

-- ---------------------------------------------------------------------------
-- action_items
-- Spec §4.1: id, meeting_id (nullable), thread_id, owner_employee_id,
--             description, due_at, status, resulting_event_ids (json)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS action_items (
    id                   BIGSERIAL   PRIMARY KEY,
    meeting_id           BIGINT      REFERENCES meetings (id) ON DELETE SET NULL,
    thread_id            BIGINT      REFERENCES narrative_threads (id) ON DELETE CASCADE,
    owner_employee_id    BIGINT      NOT NULL,  -- FK to employees added in Phase 14
    description          TEXT        NOT NULL,
    due_at               TIMESTAMPTZ,           -- sim-time deadline
    status               TEXT        NOT NULL DEFAULT 'open'
                         CHECK (status IN ('open', 'done', 'overdue', 'orphaned')),
    resulting_event_ids  JSONB       NOT NULL DEFAULT '[]'  -- narrative_events.id array
);

CREATE INDEX IF NOT EXISTS idx_action_items_thread_id         ON action_items (thread_id);
CREATE INDEX IF NOT EXISTS idx_action_items_meeting_id        ON action_items (meeting_id);
CREATE INDEX IF NOT EXISTS idx_action_items_owner_employee_id ON action_items (owner_employee_id);
CREATE INDEX IF NOT EXISTS idx_action_items_status            ON action_items (status);
CREATE INDEX IF NOT EXISTS idx_action_items_due_at            ON action_items (due_at);

-- ---------------------------------------------------------------------------
-- pending_reactions
-- Spec §4.1: id, thread_id, target_employee_id, triggering_event_id, status
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pending_reactions (
    id                  BIGSERIAL   PRIMARY KEY,
    thread_id           BIGINT      REFERENCES narrative_threads (id) ON DELETE CASCADE,
    target_employee_id  BIGINT      NOT NULL,   -- FK to employees added in Phase 14
    triggering_event_id BIGINT      REFERENCES narrative_events (id) ON DELETE SET NULL,
    status              TEXT        NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'done'))
);

CREATE INDEX IF NOT EXISTS idx_pending_reactions_target_employee ON pending_reactions (target_employee_id);
CREATE INDEX IF NOT EXISTS idx_pending_reactions_status          ON pending_reactions (status);

-- ---------------------------------------------------------------------------
-- pending_approvals
-- Spec §4.1 + SPEC_CLARIFICATIONS #1:
--   Uses two nullable columns (approver_employee_id, approver_is_principal)
--   instead of a single tagged column — simpler to query, no encoding needed.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pending_approvals (
    id                        BIGSERIAL   PRIMARY KEY,
    expense_request_ref       TEXT        NOT NULL,  -- Zammad ticket ID/ref
    requester_employee_id     BIGINT      NOT NULL,  -- FK to employees added in Phase 14
    approver_employee_id      BIGINT,                -- nullable; FK to employees in Phase 14
    approver_is_principal     BOOLEAN     NOT NULL DEFAULT FALSE,
    -- Exactly one of (approver_employee_id IS NOT NULL) or (approver_is_principal = TRUE)
    -- must be true. Enforced in application logic, not DB constraint (simpler queries).
    amount                    NUMERIC(15, 2) NOT NULL,
    status                    TEXT        NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending', 'approved', 'rejected', 'escalated')),
    idempotency_key           TEXT        UNIQUE,   -- prevents double-post on retry (§23)
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pending_approvals_requester  ON pending_approvals (requester_employee_id);
CREATE INDEX IF NOT EXISTS idx_pending_approvals_approver   ON pending_approvals (approver_employee_id);
CREATE INDEX IF NOT EXISTS idx_pending_approvals_status     ON pending_approvals (status);

-- ---------------------------------------------------------------------------
-- system_audit_log
-- Spec §4.1, §14.3: SURVIVES EVERY PURGE INCLUDING FULL PURGE.
-- CRITICAL: NO foreign keys, NO cascade from any other table.
--   This is the immutable audit trail — nothing can delete from it indirectly.
-- SPEC_CLARIFICATIONS #8: excluded from snapshot capture/restore.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_audit_log (
    id         BIGSERIAL   PRIMARY KEY,
    actor      TEXT        NOT NULL,   -- 'system', 'principal', employee_id string, service name
    action     TEXT        NOT NULL,   -- action verb (e.g. 'payroll_posted', 'audit_correction')
    detail     JSONB       NOT NULL DEFAULT '{}',  -- arbitrary structured details
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()   -- wall-clock time (NOT sim-time — this is real)
    -- NO FK to any other table.
    -- NO cascade from any other table.
    -- NO delete trigger.
    -- Any purge logic must explicitly exclude this table.
);

-- This index is intentionally NOT on sim-time — audit log uses wall-clock (created_at = real NOW())
CREATE INDEX IF NOT EXISTS idx_system_audit_log_actor      ON system_audit_log (actor);
CREATE INDEX IF NOT EXISTS idx_system_audit_log_action     ON system_audit_log (action);
CREATE INDEX IF NOT EXISTS idx_system_audit_log_created_at ON system_audit_log (created_at DESC);

-- ---------------------------------------------------------------------------
-- company_directives
-- Spec §8: current direction statement, versioned, editable via dashboard.
-- Injected as fixed block in every LLM prompt (§20.1 token-efficiency tip 1).
-- Synced to a pinned Wiki.js page.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS company_directives (
    id           BIGSERIAL   PRIMARY KEY,
    content      TEXT        NOT NULL,
    version      INTEGER     NOT NULL DEFAULT 1,
    is_current   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by   TEXT        NOT NULL DEFAULT 'system'  -- 'principal' or 'system'
);

CREATE INDEX IF NOT EXISTS idx_company_directives_is_current ON company_directives (is_current);
CREATE INDEX IF NOT EXISTS idx_company_directives_version    ON company_directives (version DESC);

-- Seed default company direction
INSERT INTO company_directives (content, version, is_current, created_by)
VALUES (
    'FakeCo is a growing B2B software company focused on delivering reliable, well-supported products to our customers. Our priorities are: (1) customer satisfaction and support quality, (2) sustainable revenue growth through the Sales team, (3) operational efficiency, and (4) employee development. We value clear communication, accountability, and continuous improvement.',
    1,
    TRUE,
    'system'
)
ON CONFLICT DO NOTHING;
