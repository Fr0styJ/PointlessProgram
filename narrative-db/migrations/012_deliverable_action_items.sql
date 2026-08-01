-- Migration: 012_deliverable_action_items.sql
-- Feature: WordPress + Nextcloud narrative-driven content creation
--
-- Adds a `deliverable_type` column to `action_items` so the meeting-simulator's
-- LLM output can explicitly flag an action item as requiring a real artifact:
--   'wordpress_post'  → a public-facing WordPress blog post / company news entry
--   'nextcloud_file'  → an internal document stored in Nextcloud
--   NULL              → no artifact required; routine task handled as before
--
-- This column is the single source of truth for human-bridge's deliverable
-- fulfillment loop: it only creates real WordPress posts / Nextcloud files
-- when this column is non-null on an open action_item row, ensuring zero
-- periodic/random content generation (every artifact is attributable to a
-- specific meeting outcome).
--
-- Also adds `deliverable_url` (output) and `deliverable_fulfilled_at` (timestamp)
-- to close the audit loop: after fulfillment, human-bridge writes the real
-- appliance URL/path and timestamp back here alongside the narrative_events entry.

ALTER TABLE action_items
    ADD COLUMN IF NOT EXISTS deliverable_type TEXT
        CHECK (deliverable_type IN ('wordpress_post', 'nextcloud_file')),
    ADD COLUMN IF NOT EXISTS deliverable_url TEXT,
    ADD COLUMN IF NOT EXISTS deliverable_fulfilled_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_action_items_deliverable_type
    ON action_items (deliverable_type)
    WHERE deliverable_type IS NOT NULL;

COMMENT ON COLUMN action_items.deliverable_type IS
    'Non-null when this action item requires a real artifact: '
    '''wordpress_post'' for a public WordPress post, '
    '''nextcloud_file'' for an internal Nextcloud document. '
    'Set by meeting-simulator based on LLM output. '
    'NULL = routine task, no appliance artifact needed.';

COMMENT ON COLUMN action_items.deliverable_url IS
    'The real appliance URL/path of the created artifact, written back by '
    'human-bridge after successful fulfillment.';

COMMENT ON COLUMN action_items.deliverable_fulfilled_at IS
    'Wall-clock timestamp when human-bridge successfully created the artifact.';
