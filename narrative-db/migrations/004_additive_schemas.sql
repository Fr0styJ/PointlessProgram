-- Migration: 004_additive_schemas.sql
-- Additive phase tables — each introduced in its named phase.
-- Grouped here for reference; each section is idempotent (CREATE TABLE IF NOT EXISTS).

-- ---------------------------------------------------------------------------
-- pto_calendar — Phase 19
-- Spec §15: employee_id, start_sim_time, end_sim_time, reason (flavor only)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pto_calendar (
    id              BIGSERIAL   PRIMARY KEY,
    employee_id     BIGINT      NOT NULL REFERENCES employees (id) ON DELETE CASCADE,
    start_sim_time  TIMESTAMPTZ NOT NULL,
    end_sim_time    TIMESTAMPTZ NOT NULL,
    reason          TEXT        NOT NULL DEFAULT '',  -- flavor only, no functional consequence
    CHECK (end_sim_time > start_sim_time)
);

CREATE INDEX IF NOT EXISTS idx_pto_calendar_employee_id ON pto_calendar (employee_id);
CREATE INDEX IF NOT EXISTS idx_pto_calendar_start       ON pto_calendar (start_sim_time);
CREATE INDEX IF NOT EXISTS idx_pto_calendar_end         ON pto_calendar (end_sim_time);

-- ---------------------------------------------------------------------------
-- employee_relationships — Phase 20
-- Spec §5: employee_a_id, employee_b_id, relationship_type, affinity_score,
--           last_updated (sim-time), notes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS employee_relationships (
    id                BIGSERIAL   PRIMARY KEY,
    employee_a_id     BIGINT      NOT NULL REFERENCES employees (id) ON DELETE CASCADE,
    employee_b_id     BIGINT      NOT NULL REFERENCES employees (id) ON DELETE CASCADE,
    relationship_type TEXT        NOT NULL DEFAULT 'neutral'
                      CHECK (relationship_type IN ('ally', 'rival', 'mentor', 'mentee', 'neutral')),
    affinity_score    INTEGER     NOT NULL DEFAULT 0
                      CHECK (affinity_score BETWEEN -100 AND 100),
    last_updated      TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- sim-time
    notes             TEXT,
    UNIQUE (employee_a_id, employee_b_id),
    CHECK (employee_a_id < employee_b_id)   -- canonical ordering prevents duplicate pairs
);

CREATE INDEX IF NOT EXISTS idx_employee_relationships_a   ON employee_relationships (employee_a_id);
CREATE INDEX IF NOT EXISTS idx_employee_relationships_b   ON employee_relationships (employee_b_id);
CREATE INDEX IF NOT EXISTS idx_employee_relationships_type ON employee_relationships (relationship_type);

-- ---------------------------------------------------------------------------
-- customers — Phase 22
-- Spec §11.2: company_name, contact_name, contact_email, relationship_status,
--              assigned_sales_rep_id, assigned_support_rep_id
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    id                      BIGSERIAL   PRIMARY KEY,
    company_name            TEXT        NOT NULL,
    contact_name            TEXT        NOT NULL,
    contact_email           TEXT        NOT NULL,   -- externally-styled (display artifact)
    relationship_status     TEXT        NOT NULL DEFAULT 'prospect'
                            CHECK (relationship_status IN ('prospect', 'active', 'at_risk', 'churned')),
    assigned_sales_rep_id   BIGINT      REFERENCES employees (id) ON DELETE SET NULL,
    assigned_support_rep_id BIGINT      REFERENCES employees (id) ON DELETE SET NULL,
    deal_size               NUMERIC(15, 2),         -- set at thread-open time, never changed at close
    akaunting_transaction_id TEXT,                  -- revenue transaction ID once deal closes
    support_sla_hours       INTEGER     NOT NULL DEFAULT 24,  -- churn if open ticket exceeds this
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_customers_status         ON customers (relationship_status);
CREATE INDEX IF NOT EXISTS idx_customers_sales_rep      ON customers (assigned_sales_rep_id);
CREATE INDEX IF NOT EXISTS idx_customers_support_rep    ON customers (assigned_support_rep_id);

-- ---------------------------------------------------------------------------
-- kpi_snapshots — Phase 23
-- Spec §12.1: department/employee, metric, value, sim_time
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kpi_snapshots (
    id            BIGSERIAL   PRIMARY KEY,
    snapshot_date TIMESTAMPTZ NOT NULL,  -- sim-time of the daily rollup
    entity_type   TEXT        NOT NULL CHECK (entity_type IN ('department', 'employee')),
    entity_id     TEXT        NOT NULL,  -- department name or employee_id string
    metric        TEXT        NOT NULL,
    -- Known metrics: 'tickets_resolved', 'tickets_opened', 'avg_resolution_hours',
    --                'wiki_pages_created', 'wiki_pages_updated', 'chat_messages',
    --                'emails_sent', 'revenue_posted', 'action_items_completed'
    value         NUMERIC     NOT NULL DEFAULT 0,
    UNIQUE (snapshot_date, entity_type, entity_id, metric)
);

CREATE INDEX IF NOT EXISTS idx_kpi_snapshots_date        ON kpi_snapshots (snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_kpi_snapshots_entity      ON kpi_snapshots (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_kpi_snapshots_metric      ON kpi_snapshots (metric);
