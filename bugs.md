# bugs.md — Outstanding issues

Tracks currently-open bugs and gaps as of 2026-08-01. Fixed issues are not kept here; see
`BUILD_LOG.md` for the complete reverse-chronological fix history.

---

## Bugs (confirmed, reproducible)

### 1. Principal chat/email activity creates pending reactions but employees never reply

`human-bridge` correctly detects Principal-authored Mattermost messages, Zammad comments,
Wiki.js edits, and emails, then creates `narrative_events(origin='human')` and
`pending_reactions`. Nothing consumes those `pending_reactions`. The original specification says
they must be the orchestrator's highest-priority work and use the higher-tier model, but the
orchestrator currently has no such worker. As a result, direct chats and emails are detected but
never answered. The new 50-profile personality library and stable employee assignments provide
the persona data needed by a future reply worker; they do not themselves send replies. Also,
LiteLLM is intentionally stopped, so any LLM-backed reply worker must pause without consuming or
discarding queued reactions until the user explicitly restarts it.

### Recently fixed

The three deliverable-fulfillment bugs found during the WordPress/Nextcloud review were fixed and
live-verified on 2026-08-01:

- Nextcloud now creates every missing WebDAV parent collection before uploading a file.
- Generated title/content/excerpt fields are validated; an invalid response is retried once and
  rejected if the second response is still unusable.
- Failures now use persistent exponential backoff and become terminal after a configurable
  attempt limit instead of retrying every poll forever.

---

## Known feature gaps (not bugs — deliberately unbuilt or deferred)

### 1. Phase 24 — pay negotiation / performance-review-driven pay cuts

Not started. `meeting-simulator` has a `pay_negotiation` meeting-type schema/attendee-selection
stub, but nothing invokes it. The dashboard correctly blocks pay cuts until negotiation meetings
are implemented.

### 2. Phase 32 — simulation speed slider, full integration

Deliberately deferred by explicit user decision. The design is preserved in `Future_Plans.md`.
The dashboard shows the disabled slider with a “Coming Soon” label.

### 3. Phase 38 — hardening

- Create the top-level `README.md` with deployment, resource footprint, troubleshooting, and a
  tab-by-tab dashboard walkthrough.
- Audit `.env.example` systematically against every service's required variables.
- Add and verify graceful dashboard error states when individual backing services are down.
- Verify first boot end-to-end in a clean disposable environment: unattended Principal/roster
  provisioning, Akaunting chart-of-accounts setup, and initial branding.

---

## Narrative content invariant

WordPress posts and Nextcloud files are generated only for a real narrative action item whose
`deliverable_type` explicitly requests an artifact. The poller never invents random or periodic
content triggers.
