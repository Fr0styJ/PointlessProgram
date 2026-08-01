# bugs.md — Outstanding issues

Tracks currently-open bugs and gaps as of 2026-08-01. Fixed issues are not kept here; see
`BUILD_LOG.md` for the complete reverse-chronological fix history.

---

## Bugs (confirmed, reproducible)

None currently tracked. The three deliverable-fulfillment bugs found during the
WordPress/Nextcloud review were fixed and live-verified on 2026-08-01:

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
