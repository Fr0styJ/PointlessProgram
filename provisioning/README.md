# provisioning/

**Populated by:** Phase 14 — Roster & per-employee provisioning

This directory will contain the provisioning scripts/service: creates real accounts for each
employee (and the Principal) across all four appliances, and writes back the resulting IDs
into the employee roster row (spec §9, §26).

**Provisioning routine — per employee:**
1. docker-mailserver: create mailbox (`setup email add`)
2. Mattermost: create bot account via REST API, store `mattermost_id`
3. Zammad: create agent account via REST API, store `zammad_agent_id`
4. Wiki.js: create editor account via GraphQL API, store `wiki_user_id`

**Principal provisioning:**
- Mailbox: `PRINCIPAL_EMAIL` on docker-mailserver
- Mattermost: real human account (not a bot)
- Zammad: agent account (for approving over-threshold expense requests)
- Wiki.js: editor account

**Key requirements:**
- Callable directly (script/CLI) — no dashboard needed until Phase 34.
- Idempotent: re-running for the same employee does NOT create duplicate accounts.
- Single-add capable: can provision just one new employee (used by Hire flow in Phase 34).
- Fire path: status → `terminated`; deactivates (never deletes) accounts everywhere.

**Placeholder roster (SPEC_CLARIFICATIONS #10):**
A 20-employee placeholder roster is invented by the building agent and seeded here.
It is explicitly marked as a placeholder and swappable for a real roster.
See the roster definition in this directory once Phase 14 runs.

**Dependencies:** Phases 4 (mail), 5 (Mattermost), 6 (Zammad), 7 (Wiki.js), 13 (schema).
