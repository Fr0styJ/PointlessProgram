# kpi-engine/

**Populated by:** Phase 23 (KPI scoreboards) + Phase 24 (performance review formula) + Phase 25 (weekly digest)

This directory will contain the KPI Engine service: deterministic aggregation across every
appliance's own data (spec §12).

**KPI scoreboards (§12.1):**
- Daily (sim-time) rollup: Zammad ticket counts/resolution time, Wiki.js page counts,
  Mattermost message counts, Akaunting revenue.
- Stored in `kpi_snapshots` (department/employee, metric, value, sim_time).
- NO LLM involved — pure aggregation, same principle as accounting (§10.1).

**Performance review cycle (§12.2):**
- Scheduled job (default quarterly-equivalent, tunable via config).
- Deterministic formula: top quartile +5%, second quartile +2%, rest +0%.
- Runs fully automatically by default; dashboard toggle available for "review & approve" mode.
- Underperformance → opens `performance_review` meeting, never automatic cut.
- Cold start: skip entirely for <1 full cycle tenure or dept <2 members (SPEC_CLARIFICATIONS #6).

**Weekly digest (§12.3):**
- Deterministic selection of past sim-week's notable events.
- HR-sensitive threads EXCLUDED (pay negotiations, terminations, performance reviews).
- ONE LLM call (cheap/mid tier) converts the pre-selected list to newsletter voice.
- Published to Wiki.js and Mattermost #general.

**Dependencies:** Phases 5, 6, 7, 9, 13, 21, 22, 24.
