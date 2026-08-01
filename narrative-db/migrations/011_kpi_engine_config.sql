-- Migration: 011_kpi_engine_config.sql
-- Phase 35: KPI/Performance dashboard tab — live-switchable review-mode toggle.
--
-- Phase 23's KPI_REVIEW_APPROVAL_MODE was env-var-only (kpi-engine/main.py),
-- meaning flipping "automatic" vs "review & approve" mode required a container
-- restart. Per PLAN_PHASES_33_38_DASHBOARD.md's Phase 35 feature list ("a small
-- kpi-engine config table/row so the toggle can be live without a restart"),
-- this adds a single-row config table kpi-engine reads/writes at runtime. The
-- env var remains the fallback default (used the first time this row is
-- seeded) — not removed, since it's still the documented way to set the
-- starting value for a fresh environment.

CREATE TABLE IF NOT EXISTS kpi_engine_config (
    id                     SMALLINT    PRIMARY KEY DEFAULT 1,
    review_approval_mode   BOOLEAN     NOT NULL DEFAULT FALSE,
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by             TEXT        NOT NULL DEFAULT 'system',
    CONSTRAINT kpi_engine_config_singleton CHECK (id = 1)
);

-- Seed the single row if it doesn't exist yet. Deliberately does NOT try to
-- read the KPI_REVIEW_APPROVAL_MODE env var from SQL (migrations can't see
-- container env) — kpi-engine's own startup code seeds this row from its env
-- var default the first time it finds the table empty (see main.py).
INSERT INTO kpi_engine_config (id, review_approval_mode, updated_by)
VALUES (1, FALSE, 'system')
ON CONFLICT (id) DO NOTHING;
