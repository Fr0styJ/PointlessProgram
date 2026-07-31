# purge-manager/

**Populated by:** Phase 29 — Data purge & snapshots (purge half)

This directory will contain the Purge Manager service: handles full and scoped data purge
across all appliances and the narrative Postgres schema (spec §14.1–14.3).

**Scoped purge checkboxes (§14.2):**
- Emails (docker-mailserver Maildir)
- Chat (Mattermost channels/messages)
- Tickets (Zammad)
- Wiki (Wiki.js pages)
- Meetings & narrative memory (Postgres narrative schema)
- Accounting ledger (Akaunting)
- External world (customers/BetaCorp state)
- KPI history (`kpi_snapshots`)
- Roster (reset to default)
- Company direction (reset to default)

**CRITICAL:** `system_audit_log` is NEVER wiped — not by scoped purge, not by full purge.
Full purge requires typed confirmation phrase "DELETE EVERYTHING".

**Dependencies:** Phases 0–28 (every appliance and table must exist first); run against
disposable test environment, not primary dev env.
