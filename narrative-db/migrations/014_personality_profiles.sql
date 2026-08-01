-- Migration: 014_personality_profiles.sql
-- Reusable detailed employee backgrounds/personas with stable roster assignment.

CREATE TABLE IF NOT EXISTS personality_profiles (
    id          TEXT PRIMARY KEY,
    short_label TEXT NOT NULL,
    profile     JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE employees
    ADD COLUMN IF NOT EXISTS personality_profile_id TEXT
    REFERENCES personality_profiles (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_employees_personality_profile
    ON employees (personality_profile_id);

COMMENT ON COLUMN employees.personality_profile_id IS
    'Stable randomly-balanced assignment from the reusable personality library.';
