# snapshot-manager/

**Populated by:** Phase 29 — Data purge & snapshots (snapshot half)

This directory will contain the Snapshot Manager service: captures and restores full system
state as named, sim-time-tagged snapshots (spec §14.4).

**What a snapshot captures:**
- Every appliance's own database
- docker-mailserver's Maildir volume
- Narrative Postgres schema
- Sim clock state
- Roster state
- Company direction

**What a snapshot does NOT capture (SPEC_CLARIFICATIONS #8):**
- `system_audit_log` — excluded from both capture and restore. Stays a continuous honest
  record independent of which snapshot is loaded.

**Restore behavior:**
- Destructive to current unsaved state — requires same confirmation as scoped purge.
- Affected containers are stopped for the duration of save/restore, then resumed.

**Dashboard tab:** Snapshots (grouped under Data Management) — list, Save Now, Restore, Delete.

**Dependencies:** Phases 0–28.
