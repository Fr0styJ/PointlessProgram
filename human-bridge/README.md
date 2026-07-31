# human-bridge/

**Populated by:** Phase 17 — Human interaction bridge

This directory will contain the Human Interaction Bridge service: detects Principal-authored
content via native webhooks (Mattermost, Zammad, Wiki.js) or IMAP polling (mail), converts
each into `narrative_events(origin='human')`, and writes a `pending_reactions` row for
whoever it was addressed to (spec §7).

**Integration surfaces:** 4
- docker-mailserver IMAP polling
- Mattermost webhook
- Zammad webhook
- Wiki.js webhook

**Dependencies:** Phases 4, 5, 6, 7 (appliances), 13 (schema), 14 (roster).
