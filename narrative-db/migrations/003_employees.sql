-- Migration: 003_employees.sql
-- Phase 14: Employee roster table + FK additions to Phase 13 tables
-- Spec §9 + SPEC_CLARIFICATIONS #3 (is_lead / role_tier)
--
-- SPEC_CLARIFICATIONS #10: No seed roster provided. Building agent invents a
-- placeholder 20-employee roster. Clearly marked as swappable.

-- ---------------------------------------------------------------------------
-- employees roster table
-- Spec §9: id, name, email, department, role, personality, status,
--           hired_at, terminated_at, mattermost_id, zammad_agent_id,
--           wiki_user_id, mailbox_address + payroll fields (§10.3)
-- SPEC_CLARIFICATIONS #3: is_lead boolean (or role_tier enum ic/lead)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS employees (
    id                  BIGSERIAL   PRIMARY KEY,
    name                TEXT        NOT NULL,
    email               TEXT        NOT NULL UNIQUE,  -- mailbox_address / @fakecorp.internal
    department          TEXT        NOT NULL,
    role                TEXT        NOT NULL,         -- job title
    role_tier           TEXT        NOT NULL DEFAULT 'ic'
                        CHECK (role_tier IN ('ic', 'lead')),
    -- SPEC_CLARIFICATIONS #3: is_lead = (role_tier = 'lead') convenience bool
    -- Maintained by trigger or application logic; longest-tenured = lead if multiple.
    is_lead             BOOLEAN     NOT NULL GENERATED ALWAYS AS (role_tier = 'lead') STORED,
    personality         TEXT        NOT NULL DEFAULT '',  -- persona description for LLM prompts
    status              TEXT        NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'vacant', 'terminated', 'resigned')),
    hired_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- sim-time
    terminated_at       TIMESTAMPTZ,                          -- sim-time; NULL if active

    -- Appliance account IDs (written back after provisioning, Phase 14)
    mattermost_id       TEXT,
    zammad_agent_id     TEXT,
    wiki_user_id        TEXT,
    mailbox_address     TEXT,  -- full address e.g. alice.johnson@fakecorp.internal

    -- Payroll fields (spec §10.3)
    pay_rate            NUMERIC(15, 2) NOT NULL DEFAULT 0,  -- per-cycle pay
    pay_frequency       TEXT    NOT NULL DEFAULT 'biweekly'  -- 'weekly', 'biweekly', 'monthly'
                        CHECK (pay_frequency IN ('weekly', 'biweekly', 'monthly')),
    pay_last_changed_at TIMESTAMPTZ,         -- sim-time of last pay change
    pay_last_change_reason TEXT             -- brief reason string (raise, negotiation, etc.)
);

CREATE INDEX IF NOT EXISTS idx_employees_status     ON employees (status);
CREATE INDEX IF NOT EXISTS idx_employees_department ON employees (department);
CREATE INDEX IF NOT EXISTS idx_employees_role_tier  ON employees (role_tier);

-- ---------------------------------------------------------------------------
-- Add FK constraints to Phase 13 tables that reference employees.id
-- (Could not add them in migration 002 because employees didn't exist yet.)
-- ---------------------------------------------------------------------------
ALTER TABLE narrative_events
    ADD CONSTRAINT fk_narrative_events_employee
    FOREIGN KEY (employee_id) REFERENCES employees (id) ON DELETE SET NULL;

ALTER TABLE action_items
    ADD CONSTRAINT fk_action_items_owner
    FOREIGN KEY (owner_employee_id) REFERENCES employees (id) ON DELETE SET NULL;

ALTER TABLE pending_reactions
    ADD CONSTRAINT fk_pending_reactions_target
    FOREIGN KEY (target_employee_id) REFERENCES employees (id) ON DELETE CASCADE;

ALTER TABLE pending_approvals
    ADD CONSTRAINT fk_pending_approvals_requester
    FOREIGN KEY (requester_employee_id) REFERENCES employees (id) ON DELETE RESTRICT;

ALTER TABLE pending_approvals
    ADD CONSTRAINT fk_pending_approvals_approver
    FOREIGN KEY (approver_employee_id) REFERENCES employees (id) ON DELETE SET NULL;

-- ---------------------------------------------------------------------------
-- PLACEHOLDER ROSTER — 20 employees (SPEC_CLARIFICATIONS #10)
-- This is an invented placeholder. Swap out for a real roster by editing this
-- INSERT block and re-running migrations (or via the dashboard Hire/Fire UI).
-- Departments: Engineering (5), Sales (4), Support (3), Operations (3), HR (2), Finance (2), Marketing (1)
-- One lead per department (longest-tenured = first inserted per dept).
-- ---------------------------------------------------------------------------
INSERT INTO employees
    (name, email, department, role, role_tier, personality, status, hired_at, pay_rate, pay_frequency)
VALUES
-- Engineering (5) — lead: Alice Johnson
('Alice Johnson',   'alice.johnson@fakecorp.internal',   'Engineering', 'Engineering Lead',       'lead', 'Methodical, detail-oriented, champions code quality and mentors junior devs.',                         'active', NOW() - INTERVAL '3 years',  95000.00 / 26, 'biweekly'),
('Bob Martinez',    'bob.martinez@fakecorp.internal',    'Engineering', 'Senior Software Engineer','ic',   'Creative problem-solver, tends to over-engineer but produces solid results.',                         'active', NOW() - INTERVAL '2 years',  85000.00 / 26, 'biweekly'),
('Carol Okonkwo',   'carol.okonkwo@fakecorp.internal',   'Engineering', 'Software Engineer',       'ic',   'Fast learner, enthusiastic about new tech, sometimes needs scope guidance.',                          'active', NOW() - INTERVAL '1 year',   75000.00 / 26, 'biweekly'),
('David Chen',      'david.chen@fakecorp.internal',      'Engineering', 'QA Engineer',             'ic',   'Thorough tester, pessimistic by habit (good for QA), writes excellent bug reports.',                  'active', NOW() - INTERVAL '1.5 years', 70000.00 / 26, 'biweekly'),
('Eva Rossi',       'eva.rossi@fakecorp.internal',       'Engineering', 'DevOps Engineer',         'ic',   'Infrastructure-obsessed, loves automation, occasionally cryptic in stand-ups.',                      'active', NOW() - INTERVAL '2.5 years', 80000.00 / 26, 'biweekly'),

-- Sales (4) — lead: Frank Nakamura
('Frank Nakamura',  'frank.nakamura@fakecorp.internal',  'Sales',       'Sales Manager',           'lead', 'High-energy closer, relationship-builder, occasionally over-promises to customers.',                  'active', NOW() - INTERVAL '4 years',  90000.00 / 26, 'biweekly'),
('Grace Patel',     'grace.patel@fakecorp.internal',     'Sales',       'Account Executive',       'ic',   'Patient, consultative seller, strong follow-through, prefers steady pipeline over big swings.',       'active', NOW() - INTERVAL '1.5 years', 72000.00 / 26, 'biweekly'),
('Henry Kim',       'henry.kim@fakecorp.internal',       'Sales',       'Account Executive',       'ic',   'Competitive, quota-driven, sometimes rubs colleagues the wrong way but delivers numbers.',            'active', NOW() - INTERVAL '1 year',   68000.00 / 26, 'biweekly'),
('Ingrid Larsson',  'ingrid.larsson@fakecorp.internal',  'Sales',       'Sales Development Rep',   'ic',   'Eager junior rep, still learning the pitch, responds well to coaching.',                             'active', NOW() - INTERVAL '6 months', 58000.00 / 26, 'biweekly'),

-- Support (3) — lead: James Obi
('James Obi',       'james.obi@fakecorp.internal',       'Support',     'Support Lead',            'lead', 'Calm under pressure, encyclopedic product knowledge, advocates loudly for customers internally.',      'active', NOW() - INTERVAL '3.5 years', 78000.00 / 26, 'biweekly'),
('Karen Walsh',     'karen.walsh@fakecorp.internal',     'Support',     'Support Specialist',      'ic',   'Empathetic communicator, excellent written tone, occasionally slow to escalate.',                    'active', NOW() - INTERVAL '2 years',  62000.00 / 26, 'biweekly'),
('Leo Ferreira',    'leo.ferreira@fakecorp.internal',    'Support',     'Support Specialist',      'ic',   'Technical support mindset, good at reproducing bugs, thrives with clear tickets.',                    'active', NOW() - INTERVAL '1 year',   60000.00 / 26, 'biweekly'),

-- Operations (3) — lead: Maya Singh
('Maya Singh',      'maya.singh@fakecorp.internal',      'Operations',  'Operations Manager',      'lead', 'Process-driven, highly organized, pushes for documentation and SOPs on everything.',                 'active', NOW() - INTERVAL '5 years',  88000.00 / 26, 'biweekly'),
('Nathan Brooks',   'nathan.brooks@fakecorp.internal',   'Operations',  'Operations Analyst',      'ic',   'Data-oriented, good at spotting inefficiencies, quiet in meetings but sharp.',                       'active', NOW() - INTERVAL '2 years',  65000.00 / 26, 'biweekly'),
('Olivia Thompson', 'olivia.thompson@fakecorp.internal', 'Operations',  'Office Coordinator',      'ic',   'Cheerful, keeps the team glued together socially, manages vendor relationships.',                    'active', NOW() - INTERVAL '3 years',  55000.00 / 26, 'biweekly'),

-- HR (2) — lead: Paul Renard
('Paul Renard',     'paul.renard@fakecorp.internal',     'HR',          'HR Manager',              'lead', 'Discreet, policy-minded, fair mediator, privately stressed about headcount requests.',               'active', NOW() - INTERVAL '6 years',  85000.00 / 26, 'biweekly'),
('Quinn Foster',    'quinn.foster@fakecorp.internal',    'HR',          'HR Specialist',           'ic',   'Newer to HR, focused on employee experience, championing a benefits upgrade.',                       'active', NOW() - INTERVAL '1 year',   60000.00 / 26, 'biweekly'),

-- Finance (2) — lead: Rachel Nguyen
('Rachel Nguyen',   'rachel.nguyen@fakecorp.internal',   'Finance',     'Finance Manager',         'lead', 'Precise, fiscally conservative, flags any unusual expense pattern immediately.',                     'active', NOW() - INTERVAL '4 years',  92000.00 / 26, 'biweekly'),
('Sam Kowalski',    'sam.kowalski@fakecorp.internal',    'Finance',     'Financial Analyst',       'ic',   'Numbers-first personality, produces clean reports, asks clarifying questions before acting.',        'active', NOW() - INTERVAL '2 years',  70000.00 / 26, 'biweekly'),

-- Marketing (1) — lead by default (sole member)
('Tara Oduya',      'tara.oduya@fakecorp.internal',      'Marketing',   'Marketing Manager',       'lead', 'Creative, brand-conscious, sometimes at odds with Sales on messaging priorities.',                   'active', NOW() - INTERVAL '2 years',  78000.00 / 26, 'biweekly')
ON CONFLICT (email) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Market benchmark table (introduced in Phase 21, defined here as stub)
-- Actual Phase 21 migration will use ALTER TABLE IF NOT EXISTS to add columns.
-- Defining the table here makes Phase 14 idempotent with Phase 21.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_benchmark (
    id            BIGSERIAL   PRIMARY KEY,
    department    TEXT        NOT NULL,
    role_tier     TEXT        NOT NULL CHECK (role_tier IN ('ic', 'lead')),
    benchmark_pay NUMERIC(15, 2) NOT NULL,
    currency      TEXT        NOT NULL DEFAULT 'USD',
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (department, role_tier)
);

-- Seed conservative market benchmarks (placeholder — adjust as needed)
INSERT INTO market_benchmark (department, role_tier, benchmark_pay) VALUES
('Engineering', 'ic',   80000.00 / 26),
('Engineering', 'lead', 105000.00 / 26),
('Sales',       'ic',   75000.00 / 26),
('Sales',       'lead', 100000.00 / 26),
('Support',     'ic',   65000.00 / 26),
('Support',     'lead', 82000.00 / 26),
('Operations',  'ic',   65000.00 / 26),
('Operations',  'lead', 92000.00 / 26),
('HR',          'ic',   65000.00 / 26),
('HR',          'lead', 90000.00 / 26),
('Finance',     'ic',   72000.00 / 26),
('Finance',     'lead', 98000.00 / 26),
('Marketing',   'ic',   70000.00 / 26),
('Marketing',   'lead', 85000.00 / 26)
ON CONFLICT (department, role_tier) DO NOTHING;
