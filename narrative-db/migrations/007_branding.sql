-- ---------------------------------------------------------------------------
-- Phase 30: Branding & asset manager
-- Spec §17: bundled avatar/emoji asset library + employee_id -> avatar_asset_id
-- mapping, managed by the new branding-manager service. Bulk actions
-- (randomize / apply-one-to-all / reset-to-default) read/write this table and
-- then push the chosen asset through each appliance's own avatar-upload API.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS employee_branding (
    id                BIGSERIAL   PRIMARY KEY,
    employee_id       BIGINT      NOT NULL UNIQUE REFERENCES employees (id) ON DELETE CASCADE,
    avatar_asset_id   TEXT        NOT NULL,  -- filename stem under branding-manager/assets/avatars/
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_employee_branding_employee ON employee_branding (employee_id);
