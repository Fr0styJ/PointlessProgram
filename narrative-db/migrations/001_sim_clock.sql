-- Migration: 001_sim_clock.sql
-- Phase 12: sim_clock table
-- Spec §19.1
-- Note: This table is also created by sim-clock/main.py on startup (idempotent CREATE IF NOT EXISTS).
-- This migration file allows the narrative-db service to pre-create it at first boot.

CREATE TABLE IF NOT EXISTS sim_clock (
    id                   INTEGER PRIMARY KEY DEFAULT 1,
    sim_time             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_wall_checkpoint DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
    speed_multiplier     DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    CONSTRAINT sim_clock_singleton CHECK (id = 1)
);

-- Seed the single row if not present
INSERT INTO sim_clock (id, sim_time, last_wall_checkpoint, speed_multiplier)
VALUES (1, NOW(), EXTRACT(EPOCH FROM NOW()), 1.0)
ON CONFLICT DO NOTHING;
