# PHASES.md — FakeCo "Real Appliances" Build Plan

## Goal of this document

The build spec (`fakeco-real-appliances-BUILD-PROMPT.md`) describes a large,
28-section Dockerized corporate-network simulation, built up across many
handoffs and revisions. Its section order is not build order: several
sections describe custom logic that depends on real appliances being up
first, some describe deterministic/financial logic that needs isolation and
correctness testing before narrative complexity is layered on top, and
several late-numbered sections are explicitly additive and don't block
anything. This document reorders the spec into 39 phases (Phase 0–Phase 38),
each sized to be completable and independently verifiable in a single
session, so that any agent — with or without prior context — can look at
`BUILD_LOG.md`, find the current phase number, and know exactly what
"done" looks like and what to do next.

Phases 0–18 are a **strict sequential foundation**: a walking skeleton of
networks/Postgres/appliances with no AI content, then the deterministic
financial engine, then the narrative/continuity machinery, in that order.
Phases 19–32 are **additive features** — relationships, external world,
KPIs/performance reviews, PTO, chaos/crisis, purge/snapshots, branding,
speed-slider polish. They depend on the foundation but *not heavily on each
other*, so if a session runs out mid-way through this band, a later agent
can pick a different additive phase to work on next rather than being
blocked. Phases 33–38 are **final integration** — the dashboard (split by
tab group) and deployment hardening — and by design depend on nearly
everything before them.

---

## Phase list

### Phase 0 — Repo & build-log scaffolding

- **Spec sections:** 0 (build process & logging), 27 (deliverables checklist, as directory stubs only), 26 (`.env.example` skeleton only)
- **Depends on:** None
- **Entry criteria:** Empty repo.
- **Exit criteria:**
  - Git repo initialized, first commit made.
  - `BUILD_LOG.md` exists at repo root with the two-part structure from
    section 0: a status header block (current phase, percent complete,
    exact next action) and an empty reverse-chronological log below it.
    Status header currently reads "Phase 0, in progress."
  - Empty top-level directories exist for every custom deliverable named in
    section 27 (`orchestrator/`, `meeting-simulator/`, `human-bridge/`,
    `sim-clock/`, `accounting-engine/`, `purge-manager/`,
    `snapshot-manager/`, `external-world/`, `kpi-engine/`,
    `branding-manager/`, `narrative-db/`, `dashboard/`, `provisioning/`,
    `litellm/`, `monitoring/`), each with a placeholder `README.md` stating
    which phase will populate it.
  - `.env.example` exists with keys stubbed (no values) for every category
    listed in section 26 — LLM provider keys, per-appliance admin
    credentials, Postgres credentials, `PRINCIPAL_EMAIL`/`PRINCIPAL_NAME`,
    `speed_multiplier`, starting cash balance.
  - `.gitignore` excludes real `.env`, volumes, and secrets.
- **Size:** XS — no services, ~10 files.

---

### Phase 1 — Compose topology, networks, shared Postgres, socket-proxy

- **Spec sections:** 22 (network architecture), 3 (Postgres row, docker-socket-proxy row)
- **Depends on:** Phase 0
- **Entry criteria:** Phase 0 complete.
- **Exit criteria:**
  - `docker-compose.yml` defines all seven networks from section 22
    (`net_clients`, `net_office`, `net_mail`, `net_dmz`, `net_data`,
    `net_llm_bridge`, `net_mgmt`) with correct `internal: true` flags per
    the table.
  - `docker compose up` brings up only Postgres (on `net_data`) and
    `tecnativa/docker-socket-proxy` (on `net_mgmt`) successfully; both
    report healthy.
  - Postgres is reachable from a throwaway container on `net_data` via
    `psql`; is **not** reachable from a container placed on `net_clients`
    (confirms network isolation is real, not just declared).
  - Socket-proxy: confirm it allows a `START`/`STOP`/`RESTART` call against
    a labeled test container and rejects an unrelated Docker API call
    (e.g. image pull) — proves least-privilege wrapper is actually
    restrictive, not a passthrough.
- **Size:** S — 2 services, 7 network definitions.

---

### Phase 2 — Minimal observability slice (pulled forward)

- **Spec sections:** 21 (partial: cAdvisor, node-exporter, Prometheus only)
- **Depends on:** Phase 1
- **Entry criteria:** Phase 1 complete.
- **Exit criteria:**
  - cAdvisor and node-exporter running; Prometheus scraping both.
  - Prometheus UI shows both targets `up`, with visible metrics for the
    Postgres and socket-proxy containers from Phase 1.
  - No Grafana/Loki yet — this phase exists purely so every phase from here
    forward has "is the container actually up and healthy" answerable
    without `docker logs` archaeology.
- **Size:** S — 3 services, 1 scrape config.

---

### Phase 3 — DNS + router (Technitium, Traefik)

- **Spec sections:** 3 (`dns`, `router` rows), 22 (Traefik multi-homing note)
- **Depends on:** Phase 1, Phase 2
- **Entry criteria:** Phases 1–2 complete.
- **Exit criteria:**
  - Technitium up on `net_clients`; a test A record for
    `*.fakecorp.internal` resolves correctly from a container on that
    network.
  - Traefik up, multi-homed onto both `net_clients` and `net_mgmt` per the
    spec's implementation note; its own dashboard reachable from
    `net_mgmt`.
  - Prometheus (Phase 2) shows both containers healthy.
- **Size:** S/M — 2 services, DNS zone config, Traefik static config.

---

### Phase 4 — Mail (docker-mailserver + Roundcube)

- **Spec sections:** 3 (`mail` row), 7 (Principal mailbox), 26 (first-boot mailbox note)
- **Depends on:** Phase 3 (DNS)
- **Entry criteria:** Phase 3 complete.
- **Exit criteria:**
  - docker-mailserver + Roundcube up on `net_mail`.
  - A test mailbox and the `PRINCIPAL_EMAIL` mailbox both created.
  - A test email sent via SMTP is received and visible in Roundcube as that
    mailbox.
  - Confirm the mail server does **not** accept relay for arbitrary
    external destinations (see Open Questions — this phase should lock
    down anything beyond internal delivery even though section 11.1 later
    needs externally-*addressed*-looking sender fields).
- **Size:** M — mail stacks are fiddly; 2 services + DNS/relay config.

---

### Phase 5 — Chat (Mattermost)

- **Spec sections:** 3 (`chat` row), 7 (Principal Mattermost account)
- **Depends on:** Phase 3
- **Entry criteria:** Phase 3 complete.
- **Exit criteria:**
  - Mattermost up on `net_office`, reachable via Traefik hostname.
  - One test team/channel created; a Principal human account created.
  - A test bot account token successfully posts a message via the REST API
    and it's visible in the channel.
- **Size:** S/M — 1 service + bootstrap script.

---

### Phase 6 — Tickets (Zammad)

- **Spec sections:** 3 (`tickets` row), 7 (Principal Zammad agent account)
- **Depends on:** Phase 3
- **Entry criteria:** Phase 3 complete.
- **Exit criteria:**
  - Zammad up on `net_office`, reachable via Traefik.
  - Principal agent account created.
  - A test ticket created via REST API using a per-employee-style token,
    visible in the Zammad UI.
- **Size:** S/M — 1 service + bootstrap script.

---

### Phase 7 — Wiki (Wiki.js)

- **Spec sections:** 3 (`wiki` row), 7 (Principal editor account)
- **Depends on:** Phase 3
- **Entry criteria:** Phase 3 complete.
- **Exit criteria:**
  - Wiki.js up on `net_office`, reachable via Traefik.
  - Principal editor account created.
  - A test page created and updated via the GraphQL API, visible in the
    normal Wiki.js editor.
- **Size:** S — 1 service + bootstrap script.

---

### Phase 8 — Secondary flavor appliances (Nextcloud + WordPress)

- **Spec sections:** 3 (`web_public`, `web_portal` rows)
- **Depends on:** Phase 3
- **Entry criteria:** Phase 3 complete.
- **Exit criteria:**
  - Nextcloud up on `net_office`; WordPress up on `net_dmz`.
  - Each reachable via Traefik; a smoke-test API/WebDAV hit against
    Nextcloud and an HTTP hit against WordPress both succeed and are
    visible in Traefik's access logs.
  - These two are the lowest-value appliances in the spec (occasional-hit
    flavor only) — if a session must be cut short anywhere in the
    walking-skeleton band, this is the phase to defer.
- **Size:** S — 2 services, no meaningful bootstrap.

---

### Phase 9 — Accounting appliance bring-up (Akaunting)

- **Spec sections:** 3 (Accounting row), 10.1 (ledger appliance — real-appliance part only), 26 (first-boot chart-of-accounts note)
- **Depends on:** Phase 1
- **Entry criteria:** Phase 1 complete. (Does not need DNS/router, but routing it through Traefik is convenient — sequence after Phase 3 in practice.)
- **Exit criteria:**
  - Akaunting up on `net_office`/`net_data` per section 22.
  - Chart of accounts created manually via the Akaunting UI: at minimum a
    payroll expense account, a general expense account, and a revenue
    account.
  - A manual test transaction posted through the Akaunting UI and
    confirmed to change the ledger balance correctly — proves the
    appliance itself, independent of any custom code, does real
    double-entry accounting.
- **Size:** S/M — 1 service + manual first-boot config.

---

### Phase 10 — LLM gateway bring-up (LiteLLM Proxy)

- **Spec sections:** 20 (LLM gateway requirements, minus 20.1 token-efficiency which lands with the first real caller)
- **Depends on:** Phase 1
- **Entry criteria:** Phase 1 complete; at least one provider API key available (can be a placeholder/local model for this phase if real keys aren't ready).
- **Exit criteria:**
  - LiteLLM Proxy up on `net_llm_bridge`, with `net_llm_bridge` confirmed
    as its only route out per section 22.
  - `litellm/config.yaml` encodes the fallback chain (DeepSeek → Anthropic
    → OpenAI → local) even if not all providers are live yet.
  - A test completion call through the proxy succeeds and shows up in
    LiteLLM's own usage/cost tracking.
- **Size:** S — 1 service + config file.

---

### Phase 11 — Observability completion, pass 1

- **Spec sections:** 21 (Loki, Promtail, Grafana — base dashboards only)
- **Depends on:** Phases 2–10 (needs appliances/logs to exist to be worth dashboarding)
- **Entry criteria:** Walking skeleton (Phases 1–10) complete.
- **Exit criteria:**
  - Loki + Promtail aggregating logs from Traefik, Technitium, and all
    appliance containers.
  - Grafana dashboards exist for: container health, HTTP+DNS+mail traffic,
    per-appliance activity rate, appliance up/down state. (KPI/financial/
    LLM-burn panels are explicitly deferred to Phase 31, once there's real
    data to show.)
- **Size:** M — 2 services + several dashboard JSONs.

**— End of walking skeleton. Every real appliance is up, reachable, and
individually verified. No custom orchestration or AI-generated content
exists yet. —**

---

### Phase 12 — Sim clock

- **Spec sections:** 19.1 (sim clock)
- **Depends on:** Phase 1 (Postgres)
- **Entry criteria:** Phase 1 complete.
- **Exit criteria:**
  - `sim_clock` table exists (`sim_time`, `last_wall_checkpoint`,
    `speed_multiplier`).
  - Ticker advances `sim_time` correctly at `speed_multiplier = 1.0` —
    measure over a real 5-minute wall interval and confirm `sim_time`
    advanced by ~5 simulated minutes.
  - `set_speed` API changes the multiplier and the *next* tick reflects it
    immediately; verify at 10x and 0.1x over short measured intervals.
- **Size:** S — 1 custom service, 1 table.

---

### Phase 13 — Narrative DB core schema

- **Spec sections:** 4.1 (schema, minus the tables explicitly deferred to their own additive phases), 8 (`company_directives` table only)
- **Depends on:** Phase 1
- **Entry criteria:** Phase 1 complete.
- **Exit criteria:**
  - Migrations create: `narrative_threads`, `narrative_events`,
    `meetings`, `action_items`, `pending_reactions`, `pending_approvals`,
    `system_audit_log`, and `company_directives`.
  - `employee_relationships`, `pto_calendar`, `market_benchmark`,
    `customers`, and `kpi_snapshots` are **deliberately not created here**
    — each is created in the additive phase that first needs it (20, 19,
    21, 22, 23 respectively), keeping this phase's blast radius small.
  - Insert/select a test row in each of the 8 tables above.
  - Confirm `system_audit_log` has no FK/cascade relationship that would
    let a delete against any other table remove audit rows — this is the
    load-bearing guarantee for section 14.3 and should be proven now,
    before any purge logic exists to accidentally violate it later.
- **Size:** S/M — schema only, 8 tables, no new services.

---

### Phase 14 — Roster & per-employee provisioning

- **Spec sections:** 9 (roster management), 7 (Principal account creation across appliances), 26 (first-boot provisioning, partial)
- **Depends on:** Phase 13, Phases 4–7 (mail, chat, tickets, wiki)
- **Entry criteria:** Phases 4–7 and 13 complete.
- **Exit criteria:**
  - `employees` roster table exists with every field from section 9.
  - A provisioning function, callable directly (script/CLI, no dashboard
    yet), takes one roster row and creates real accounts on
    docker-mailserver, Mattermost, Zammad, and Wiki.js, then writes back
    the resulting IDs into the roster row.
  - Run provisioning for one test employee; confirm all four accounts
    exist via each appliance's own admin UI or API.
  - Re-run provisioning for the same employee; confirm it's idempotent
    (no duplicate accounts).
  - Fire path: set an employee's status to `terminated`, confirm accounts
    are deactivated (not deleted) everywhere, per section 9.
  - The initial 20-employee roster itself (names/departments/personalities/
    starting pay) is **not defined by the spec** — flagged in Open
    Questions; this phase should proceed with a placeholder roster the
    building agent invents, clearly marked as a placeholder in
    `BUILD_LOG.md`, pending direction.
- **Size:** M/L — no new services, but touches four external APIs; this is
  the single biggest early integration-risk phase.

---

### Phase 15 — Deterministic accounting engine (isolated, tested before narrative complexity)

- **Spec sections:** 10.1 (ledger appliance — deterministic-math principle), 10.2 (expense approval workflow), 10.3 (payroll — raises and posting only; pay-cut *meeting* path deferred to Phase 24), 10.4 (Books Auditor)
- **Depends on:** Phase 9 (Akaunting), Phase 13 (`pending_approvals`), Phase 14 (roster with pay fields), Phase 6 (Zammad, for `expense_request` tickets)
- **Entry criteria:** Phases 6, 9, 13, 14 complete.
- **Exit criteria (explicit correctness checks, not "it runs"):**
  - Post a $50 test expense through the full approval flow (Zammad ticket
    → deterministic `approval_policy` routing → approval) and confirm it
    appears in Akaunting's ledger with the correct account and exact
    amount.
  - Post a $600 test expense from an individual contributor; confirm it
    auto-escalates past the $25 IC limit to the department-lead tier, and
    past $500 to the Principal tier, per the table in 10.2 — and does
    **not** post to Akaunting until final approval.
  - Run a test payroll cycle for a fixed set of active employees; confirm
    the total posted to Akaunting equals the exact sum of their current
    pay, and that vacant/terminated employees draw nothing.
  - Apply a raise to a test employee; confirm it applies immediately with
    no approval step, per 10.3.
  - Deliberately mismatch one ledger record (simulate a missed post), run
    the Books Auditor, and confirm it posts a clearly-tagged "audit
    correction" transaction and a `system_audit_log` entry.
  - Pay *cuts* are explicitly stubbed here (reject/queue with a "requires
    pay_negotiation meeting" placeholder) — full handling waits for the
    meeting simulator in Phase 24. Log this deviation in `BUILD_LOG.md`.
- **Size:** L — no new appliance, but this is the financial-correctness-
  critical phase; test thoroughly before moving on.

---

### Phase 16 — Meeting simulator: standup & cross-functional

- **Spec sections:** 6 (meeting simulation — `standup`/`cross_functional` types only; `pay_negotiation`/`performance_review`/`crisis_response` deferred to Phases 24/28), 8 (company-direction injection, verified here), 20.1 (token-efficiency: cached static prefix, model tiering — implemented here, first real LLM caller)
- **Depends on:** Phase 10 (LiteLLM), Phase 13 (schema), Phase 14 (roster), Phase 7 (Wiki.js), Phase 5 (Mattermost)
- **Entry criteria:** Phases 5, 7, 10, 13, 14 complete.
- **Exit criteria:**
  - Trigger a test `standup` meeting manually (script call, no scheduler
    yet); confirm a `meetings` row, a Wiki.js `meeting-notes` page, and a
    Mattermost summary are all created.
  - Confirm resulting `action_items` rows are created and correctly
    reference the meeting/thread.
  - Confirm the current `company_directives` text appears verbatim in the
    LLM prompt sent (log/inspect the outgoing request) — proves the
    injection wiring from section 8 actually works, not just the table.
  - Confirm the static prefix (system instructions + persona + schema +
    company direction) is byte-identical across two calls with different
    tails, and that LiteLLM prompt caching is enabled for it.
  - Repeat for `cross_functional` type.
- **Size:** M/L — 1 custom service, first real generative content.

---

### Phase 17 — Human interaction bridge

- **Spec sections:** 7 (Human Interaction Bridge)
- **Depends on:** Phases 4–7 (webhook/IMAP sources), Phase 13 (schema), Phase 14 (roster, to resolve "addressed to")
- **Entry criteria:** Phases 4, 5, 6, 7, 13, 14 complete.
- **Exit criteria:**
  - Post a message as the Principal in Mattermost mentioning a test
    employee; confirm a `pending_reactions` row and a
    `narrative_events(origin='human')` row are created within a short,
    defined window.
  - Reply to a test email as the Principal (IMAP polling path); confirm
    the same.
  - Comment on a Zammad ticket as the Principal; confirm the same.
  - Edit a Wiki.js page as the Principal; confirm the same.
  - Fire the employee a reaction was pending on; confirm the pending item
    is reassigned using the same mechanism as `action_items` reassignment
    (section 9), not silently dropped.
- **Size:** M — 1 custom service, 4 integration surfaces.

---

### Phase 18 — Orchestrator continuity loop

- **Spec sections:** 4.2 (content origin), 4.3 (continuity loop, full priority order), 24 (orchestrator requirements — core loop + reachability/retry only; scheduled-job hosting for later features lands with those features), 13.1 (reachability check + `pending_actions` retry queue — built here as core reliability infrastructure, wired to dashboard toggles in Phase 27)
- **Depends on:** Phase 12 (sim clock), Phase 15 (approvals, priority 2), Phase 16 (action items, priority 3), Phase 17 (reactions, priority 1)
- **Entry criteria:** Phases 12, 15, 16, 17 complete.
- **Exit criteria:**
  - Seed one test employee with one pending reaction, one pending
    approval they own, and one open action item. Run one full cycle;
    confirm all three are processed in the exact priority order from
    4.3 (reaction → approval → action item → filler), each correctly
    marked consumed/done.
  - Confirm the reaction is generated on the higher-tier model regardless
    of what tier that content type would normally get, per priority 1's
    explicit instruction.
  - Confirm routine filler generation for priority 4 pulls only the
    targeted memory slice (thread summary + last 1–2 events + company
    direction), not full history — inspect the outgoing prompt.
  - Stop (docker stop) an appliance the cycle needs mid-run; confirm the
    action queues in `pending_actions` with wall-clock-based retry rather
    than erroring or crash-looping, and confirms/retries successfully once
    the appliance is restarted.
- **Size:** L — heaviest integration phase in the foundation band, but
  mostly wiring already-built pieces together.

**— End of strict sequential foundation. The system now generates real,
continuous, memory-aware narrative content end to end. Everything from here
is additive. —**

---

### Phase 19 — PTO

- **Spec sections:** 15 (PTO)
- **Depends on:** Phase 14 (roster), Phase 4 (mail/Sieve), Phase 5 (Mattermost status API), Phase 15 (approval delegation), Phase 18 (filler-skip logic)
- **Entry criteria:** Phases 4, 5, 14, 15, 18 complete.
- **Exit criteria:**
  - `pto_calendar` table created (this is where it's introduced, per
    Phase 13's note).
  - Schedule a test PTO window starting immediately in sim-time; confirm a
    real Sieve vacation auto-responder activates on that mailbox and a
    real Mattermost custom status is set, both via genuine appliance
    features.
  - Confirm the continuity loop skips new proactive filler for that
    employee during the window, and generates a "catching up" burst
    immediately after it ends.
  - Confirm an approval assigned to a PTO'd approver auto-routes to a
    configured backup or escalates a tier, per 10.2 + 15.
  - Confirm both effects revert automatically at window end.
- **Size:** M.

---

### Phase 20 — Interpersonal relationships

- **Spec sections:** 5 (interpersonal relationships)
- **Depends on:** Phase 14 (roster), Phase 16 (meeting simulator — needs a per-attendee "stance" field added to its output)
- **Entry criteria:** Phases 14, 16 complete.
- **Exit criteria:**
  - `employee_relationships` table created (introduced here per Phase
    13's note); seed lightly at hire time per the spec.
  - Extend Phase 16's meeting generation to include a structured
    per-attendee stance field, at no extra LLM-call cost (reuses the
    existing meeting-generation call).
  - Run a test meeting where two attendees take opposing stances; confirm
    their `affinity_score` shifts by the deterministic delta and persists
    — with **no separate LLM call spent updating relationships**, per the
    spec's explicit constraint.
  - Confirm meeting attendee selection is measurably weighted toward
    allies for a given topic (test via direct scoring-function call, not
    statistical sampling, for a deterministic check).
  - Confirm the dashboard-facing relationship view is *not* built yet —
    that's Phase 34 — this phase is backend + meeting-simulator hook only.
- **Size:** S/M.

---

### Phase 21 — External world: BetaCorp rival

- **Spec sections:** 11.1 (BetaCorp)
- **Depends on:** Phase 14 (roster/pay), Phase 15 (payroll data), Phase 4 (mail), Phase 18 (pending-reactions-style flag pattern)
- **Entry criteria:** Phases 4, 14, 15, 18 complete.
- **Exit criteria:**
  - `market_benchmark` table created (introduced here).
  - Set a test employee's pay artificially below benchmark; run the
    job-offer check; confirm a probabilistic (deterministic-probability,
    not LLM-judged) offer email is delivered to their mailbox with an
    externally-looking sender.
  - Confirm a near-miss case surfaces a flag visible to the Principal
    (reusing the `pending_reactions` pattern) rather than silently
    resolving.
  - Confirm an unaddressed large gap deterministically resolves the
    employee to `resigned` and the roster reflects the resulting vacancy.
  - Confirm the mail-injection mechanism used here cannot be reached from
    outside the closed network (see Open Questions re: Phase 4's relay
    lockdown).
- **Size:** M.

---

### Phase 22 — External world: customers & revenue

- **Spec sections:** 11.2 (external customers)
- **Depends on:** Phase 14 (roster/assignment), Phase 15 (extend accounting engine with a revenue-posting function), Phase 6 (Zammad), Phase 4 (mail)
- **Entry criteria:** Phases 4, 6, 14, 15 complete.
- **Exit criteria:**
  - `customers` table created (introduced here).
  - Create a test customer with a fixed deal-size field; simulate the
    sales thread reaching a decision; confirm the *exact* deal-size amount
    posts as a real revenue transaction in Akaunting, tagged to that
    customer — confirm the amount is read from the field set at
    thread-open time, never invented at close time.
  - Create a test active customer with a support ticket left open past
    the configured sim-time threshold; confirm deterministic churn to
    `churned`.
  - Confirm prospect/active-customer traffic generation follows the
    normal sim-time/business-hours cadence rather than firing constantly.
- **Size:** M/L.

---

### Phase 23 — KPI scoreboards

- **Spec sections:** 12.1 (KPI scoreboards)
- **Depends on:** Phase 5 (Mattermost), Phase 6 (Zammad), Phase 7 (Wiki.js), Phase 9 (Akaunting), Phase 22 (revenue data)
- **Entry criteria:** Phases 5, 6, 7, 9, 22 complete.
- **Exit criteria:**
  - `kpi_snapshots` table created (introduced here).
  - Run the deterministic daily rollup once over a fixed test window;
    independently query each source appliance (Zammad ticket
    counts/resolution time, Wiki.js page counts, Mattermost message
    counts, Akaunting revenue) and confirm `kpi_snapshots` matches exactly.
  - Confirm no LLM call is involved anywhere in this rollup.
- **Size:** S/M.

---

### Phase 24 — Meeting simulator extension: pay negotiation & performance review

- **Spec sections:** 6 (`pay_negotiation`, `performance_review` meeting types + HR-privacy exclusion), 10.3 (pay-cut path, completed here), 12.2 (performance review cycle)
- **Depends on:** Phase 16 (base meeting simulator), Phase 15 (accounting engine — extend payroll to accept a meeting-outcome-driven change), Phase 23 (KPI data for the review formula)
- **Entry criteria:** Phases 15, 16, 23 complete.
- **Exit criteria:**
  - Propose a test pay cut; confirm it opens a `pay_negotiation` meeting
    (not published to any public Wiki.js/Mattermost feed) seeded with the
    proposed figure.
  - Confirm the meeting's structured outcome — agreed figure, compromise,
    or resignation — and *not* the original proposed figure, is what
    actually gets applied to payroll. This closes the stub left open in
    Phase 15.
  - Run the performance-review formula against fixed test KPI data;
    confirm the correct raise tier (top quartile / second / rest) is
    computed by plain code, applied automatically (default mode, no
    approval needed) with a `narrative_event` logged.
  - Confirm underperformance opens a `performance_review` meeting instead
    of any automatic cut.
  - Confirm neither meeting type appears in the public meeting-notes feed.
- **Size:** L.

---

### Phase 25 — Weekly digest

- **Spec sections:** 12.3 ("This Week at FakeCo")
- **Depends on:** Phase 13 (threads), Phase 24 (HR-privacy exclusion logic, reused), Phase 21/22 (hires, customer wins/losses)
- **Entry criteria:** Phases 13, 21, 22, 24 complete.
- **Exit criteria:**
  - Seed a fixed test sim-week of events including at least one
    HR-sensitive thread; run the digest job; confirm the deterministic
    selection excludes HR-sensitive threads and includes the intended
    notable events.
  - Confirm exactly one LLM call (cheap/mid tier) turns the pre-selected
    list into the published digest, posted to Wiki.js and Mattermost
    `#general`.
- **Size:** S.

---

### Phase 26 — Ambient flavor events

- **Spec sections:** 16 (ambient flavor events)
- **Depends on:** Phase 10 (LiteLLM), Phase 5 (Mattermost), Phase 12 (sim clock)
- **Entry criteria:** Phases 5, 10, 12 complete.
- **Exit criteria:**
  - Run the generator once; confirm exactly one cheap-tier message is
    posted to a general channel.
  - Confirm **zero** rows are created in `narrative_threads`,
    `narrative_events`, or `action_items` — proving this path genuinely
    bypasses the memory system rather than just being cheap.
- **Size:** XS/S.

---

### Phase 27 — Chaos: service availability controls

- **Spec sections:** 13.1 (service availability — dashboard-toggle backend + retry-queue completion)
- **Depends on:** Phase 1 (socket-proxy), Phase 18 (retry queue already exists from the core loop)
- **Entry criteria:** Phases 1, 18 complete.
- **Exit criteria:**
  - A control-API endpoint (callable directly, dashboard UI comes later in
    Phase 36) stops/starts/restarts a labeled appliance container via
    socket-proxy.
  - Stop an appliance mid-flow; confirm an in-flight orchestrator action
    queues rather than erroring, and confirm it retries and succeeds after
    restart (extends Phase 18's reachability check to cover
    manually-triggered outages specifically).
  - Confirm a disallowed socket-proxy call (anything outside
    START/STOP/RESTART on labeled containers) is rejected.
  - Confirm the outage is logged as a `narrative_event` phrased in
    sim-time terms.
- **Size:** S/M.

---

### Phase 28 — Chaos: crisis events

- **Spec sections:** 13.2 (manually-triggered crisis events)
- **Depends on:** Phase 16/24 (meeting simulator, extend with `crisis_response` type), Phase 15 (Books Auditor)
- **Entry criteria:** Phases 15, 16 complete (24 recommended but not required).
- **Exit criteria:**
  - Trigger the "surprise audit" preset; confirm it invokes the *real*
    Books Auditor from Phase 15 and narrates its actual findings, not a
    fabricated result.
  - Trigger a free-text custom scenario; confirm it opens a high-priority
    `crisis` thread, schedules a `crisis_response` meeting with a forced
    attendee list, and seeds downstream action items — same machinery as
    any other meeting, invoked on demand.
  - Confirm a crisis-associated expense routes through the normal
    approval flow from Phase 15, not a special path.
- **Size:** M.

---

### Phase 29 — Data purge & snapshots

- **Spec sections:** 14 (full purge, scoped purge, immutable audit log, named snapshots)
- **Depends on:** Effectively everything through Phase 28 — every appliance and table this phase might need to wipe or capture must already exist.
- **Entry criteria:** Phases 0–28 complete. Run against a disposable test
  environment, not the primary dev environment — this phase is destructive
  by design.
- **Exit criteria:**
  - **Scoped purge:** exercise each checkbox (Emails, Chat, Tickets, Wiki,
    Meetings & narrative memory, Accounting ledger, External world, KPI
    history, Roster, Company direction) independently; confirm only the
    selected scope's data and corresponding `narrative_events` are
    removed, and unrelated scopes are untouched.
  - **Full purge:** confirm the typed-confirmation phrase gate blocks the
    button until the exact phrase is entered; confirm the resulting state
    matches a fresh first-boot roster/clock/company-direction default.
  - **Audit log:** confirm `system_audit_log` survives every purge type,
    including full purge, with no exceptions.
  - **Snapshots:** save a named snapshot, mutate state significantly,
    restore, and confirm the restored state matches the snapshot exactly
    across every appliance's own database, docker-mailserver's Maildir,
    the narrative schema, sim clock, roster, and company direction.
    Confirm affected containers are stopped for the duration of
    save/restore and correctly resume after.
- **Size:** L — highest blast-radius risk in the entire build; test in
  isolation before trusting it against real data.

---

### Phase 30 — Branding & asset manager

- **Spec sections:** 17 (branding & appearance)
- **Depends on:** Phase 14 (roster), Phase 5 (Mattermost), Phase 6 (Zammad), Phase 7 (Wiki.js)
- **Entry criteria:** Phases 5, 6, 7, 14 complete.
- **Exit criteria:**
  - Bulk-apply a test avatar set to 3 employees; confirm each appliance's
    own profile-image API reflects the change (Mattermost, Zammad,
    Wiki.js).
  - Push a themed custom-emoji pack to Mattermost; confirm it's usable in
    a message.
  - Confirm "reset to defaults" and "apply one set to everyone selected"
    both work as described.
- **Size:** S.

---

### Phase 31 — Observability completion, pass 2

- **Spec sections:** 21 (KPI/financial/LLM-burn panels)
- **Depends on:** Phase 11 (base observability), Phase 15 (accounting), Phase 23 (KPI), Phase 10 (LiteLLM)
- **Entry criteria:** Phases 10, 11, 15, 23 complete.
- **Exit criteria:**
  - Grafana panels added for: LLM token spend/cost (speed-annotated),
    narrative backlog, headcount by status, sim-time vs wall-clock, cash
    balance/burn rate/runway/payroll total from Akaunting, KPI trends,
    customer pipeline/revenue.
  - Spot-check each panel against its source: cash balance matches
    Akaunting, KPI trend matches `kpi_snapshots`, LLM spend matches
    LiteLLM's own usage tracking.
- **Size:** S — no new services, dashboards only.

---

### Phase 32 — Simulation speed slider, full integration

- **Spec sections:** 19.2 (the slider), 19.3 (behavioral calibration verification), 19.4 (business-hours gating verification), 19.5 (cost implication / burn-rate reconciliation)
- **Depends on:** Phase 12 (sim clock), Phase 18 (business-hours gating already affects filler generation), Phase 15 (Akaunting expense posting), Phase 10/31 (LLM cost data)
- **Entry criteria:** Phases 10, 12, 15, 18, 31 complete.
- **Exit criteria:**
  - `set_speed` API exposes the full continuous range with labeled
    presets; changes apply immediately.
  - At 10x, confirm `sim_time` advances at exactly 10x wall-clock over a
    measured interval, and confirm behavioral rates (filler frequency per
    sim-hour) stay at their calibrated 1x targets — i.e. compression
    doesn't also inflate the underlying rate.
  - Confirm business-hours gating (full weight Mon–Fri 9am–6pm sim-time,
    5–10% trickle otherwise) is observably in effect across a simulated
    day/night cycle.
  - Confirm a recurring "LLM burn" expense line reconciles into Akaunting
    at a rate matching the dashboard's estimated $/wall-clock-hour figure.
- **Size:** S/M.

**— End of additive-feature band. Everything the dashboard will expose now
has a working backend behind it. —**

---

### Phase 33 — Dashboard: shell + Simulation/LLM/Narrative tabs

- **Spec sections:** 25 (partial: simulation controls, LLM status, narrative view)
- **Depends on:** Phase 12, 32 (sim controls), Phase 10, 31 (LLM status), Phase 18 (narrative view)
- **Entry criteria:** Named dependencies complete.
- **Exit criteria:**
  - Dashboard shell deployed on `net_mgmt`.
  - Start/stop, worker scale, and speed slider controls call the real
    Phase 12/32 APIs and reflect true state.
  - LLM status tab shows provider/fallback, override control, usage/cost,
    and speed-adjusted burn rate, sourced live from Phase 10/31.
  - Narrative view shows open threads, action items, pending
    reactions/approvals, and meetings, sourced live from Phase 18's data.
- **Size:** S/M.

---

### Phase 34 — Dashboard: HR, Payroll, Accounting tabs

- **Spec sections:** 25 (partial: Org Chart/HR, Payroll, Accounting tabs)
- **Depends on:** Phase 9, 14 (roster/HR), Phase 20 (relationship view), Phase 15, 24 (payroll/accounting)
- **Entry criteria:** Named dependencies complete.
- **Exit criteria:**
  - Org Chart/HR tab: roster list with status, relationship view
    (node/edge visualization or equivalent), working Fire and Hire
    controls wired to Phase 14's provisioning function.
  - Payroll tab: per-employee pay editor; confirm a raise applies
    immediately and a cut correctly opens a `pay_negotiation` meeting via
    Phase 24, never applying directly.
  - Accounting tab: cash balance, P&L/balance-sheet deep link into
    Akaunting, expense-approval queue, payroll history, audit-correction
    log — all live data, not mocked.
- **Size:** M.

---

### Phase 35 — Dashboard: External World, KPI/Performance, Company Direction tabs

- **Spec sections:** 25 (partial), 8 (company-direction Save action)
- **Depends on:** Phase 21, 22 (external world), Phase 23, 24 (KPI/performance), Phase 13 (company direction table)
- **Entry criteria:** Named dependencies complete.
- **Exit criteria:**
  - External World tab: BetaCorp news feed, job-offer/resignation log,
    customer pipeline/at-risk list, revenue by customer — all live.
  - KPI/Performance tab: department/employee scoreboards, performance-
    review log, and the automatic/review-and-approve mode toggle, actually
    switching Phase 24's behavior.
  - Company Direction tab: textarea + Save + history; confirm saving
    updates `company_directives` and the synced pinned Wiki.js page, and
    that the next LLM call (any type) picks up the new text.
- **Size:** M.

---

### Phase 36 — Dashboard: Chaos, Data Management, Branding tabs

- **Spec sections:** 25 (partial)
- **Depends on:** Phase 27, 28 (chaos), Phase 29 (purge/snapshots), Phase 30 (branding)
- **Entry criteria:** Named dependencies complete.
- **Exit criteria:**
  - Chaos tab: per-appliance up/down toggle with live status, outage log,
    and the Trigger Event control (preset dropdown + free-text field),
    wired to Phases 27/28.
  - Data Management tab: full purge (hard-gated with typed confirmation),
    scoped purge (checkbox list), and Snapshots (save/restore/delete),
    wired to Phase 29 — re-verify the confirmation gate specifically
    through the UI, not just the API.
  - Branding tab: avatar/emoji picker with bulk apply, wired to Phase 30.
- **Size:** M.

---

### Phase 37 — Dashboard: TV wall, Errors panel, deep links, log tail

- **Spec sections:** 18 (TV wall), 25 (remaining: Errors panel, deep links, Traefik/Technitium log tail)
- **Depends on:** Phases 33–36 (composes their already-exposed data; per the spec this should need "no meaningful new backend logic")
- **Entry criteria:** Phases 33–36 complete.
- **Exit criteria:**
  - `/tv` route renders a no-controls, auto-cycling, screen-friendly view:
    live chat feed, live ticket feed, financial snapshot, KPI highlights,
    sim-time/speed display, recent digest highlights.
  - Errors panel surfaces recent unhandled exceptions across every custom
    service (accounting engine, meeting simulator, human bridge,
    orchestrator, external-world generator, KPI engine, branding manager,
    purge/snapshot managers).
  - Deep links from the dashboard reach every real appliance, including
    the Principal's own accounts.
  - A live Traefik + Technitium log tail streams in the dashboard.
- **Size:** S/M — presentation-layer composition, minimal new logic.

---

### Phase 38 — Deployment hardening, first-boot polish, README

- **Spec sections:** 26 (deployment requirements), 27 (final checklist pass)
- **Depends on:** Everything (Phases 0–37)
- **Entry criteria:** All prior phases complete.
- **Exit criteria:**
  - From a completely clean environment (no volumes, no `.env`), a single
    `docker compose up -d` brings up the full stack unattended.
  - First-boot section runs end to end: admin setup, account/token
    generation for the full roster + Principal, Akaunting chart-of-
    accounts setup, and an initial branding pass — all without manual
    intervention beyond supplying `.env` values.
  - `.env.example` is fully accurate against every service actually built,
    not just the Phase 0 skeleton.
  - README documents deployment, first-boot setup, resource requirements
    (confirm actual RAM/disk usage against the 8–10 GB estimate from
    section 26 and correct the number if it's drifted), troubleshooting,
    and how to use every dashboard tab.
  - Deliberately reproduce one documented failure mode and confirm the
    README's troubleshooting step actually resolves it.
  - Walk the full section 27 deliverables checklist and confirm every item
    is checked off, with partial items explicitly noted as such.
- **Size:** M — no new services; validation and documentation work, but
  broad in scope.

---

## How this plugs into `BUILD_LOG.md`

Section 0 of the build spec requires a status header whose "current phase"
field lets a brand-new agent instance pick up with zero prior context. That
field should reference the phase numbers and titles defined above verbatim
(e.g. "Phase 15 — Deterministic accounting engine, in progress: payroll
cycle test passing, Books Auditor correction test not yet run"). Percent
complete can be computed as completed phases over 39, optionally weighted
by each phase's size note (S/M/L) rather than a flat count, since Phase 29
and Phase 18 are not equivalent units of work to Phase 26. The "exact next
action" field should point at the specific unmet exit-criterion bullet
within the current phase, not just the phase name — that's the actual
resumption point. Any time a phase's real dependencies turn out to diverge
from what's mapped here (e.g. Phase 20 needing something from Phase 22 that
wasn't anticipated), that's a deviation from this plan and should be logged
in `BUILD_LOG.md` with reasoning, the same way deviations from the build
spec itself are logged.

---

## Open questions / spec gaps

These are ambiguities or possible inconsistencies noticed while phasing the
spec. Flagging rather than silently resolving, per the instructions.

1. **Polymorphic approver field.** `pending_approvals.approver_employee_id_or_principal`
   (4.1) doesn't specify its actual representation — one nullable-pair of
   columns, a single tagged/polymorphic column, or something else. Affects
   Phase 15's schema.

2. **No Akaunting-side employee identity.** The roster (section 9) stores
   IDs for Mattermost/Zammad/Wiki.js/mail but nothing for Akaunting. It's
   unclear whether payroll should post one aggregate lump transaction per
   cycle (with per-employee detail living only in Postgres) or whether each
   employee needs a corresponding contact/vendor record inside Akaunting
   itself — the latter would materially change Phase 15's and Phase 23's
   integration design.

3. **"Department lead" isn't a defined role.** The approval table (10.2)
   escalates individual-contributor requests to "Department lead," but the
   roster schema (section 9) has no flag distinguishing a lead from an
   ordinary employee in a department. Unclear how escalation resolves a
   department with zero or multiple candidates for that role.

4. **What triggers a pay cut in the first place?** Section 10.3 describes
   what happens *after* a cut is proposed (a `pay_negotiation` meeting) but
   never specifies what proposes one — purely a manual dashboard action
   from the Payroll tab, or can BetaCorp benchmark gaps (11.1) or
   performance data (12.2) automatically propose cuts? This affects
   whether Phase 21/24 need to call into Phase 15's pay-cut path.

5. **Mail relay lockdown vs. externally-looking senders.** Section 28's own
   assumptions note that docker-mailserver accepting external-looking
   envelope senders (BetaCorp, customers) is "a closed-network
   configuration choice, not real external mail delivery" — but the spec
   doesn't specify the actual Postfix/relay configuration that achieves
   this without incidentally functioning as an open relay. Worth an
   explicit lockdown check in Phase 4 and a regression check in Phase 21.

6. **Performance-review cold start.** Section 12.2's "normalizes against
   department peers" formula has no defined behavior for a newly-hired
   employee or a department with only one member (peer normalization is
   undefined at n=1).

7. **Who is the "requester" for a crisis-generated expense?** Section 13.2
   says crisis costs route through the normal approval flow (10.2), which
   requires a `requester_employee_id` — but crises are system-triggered,
   not filed by any particular employee. Unclear who that field should
   name.

8. **Snapshot/audit-log interaction.** Section 14.3 says `system_audit_log`
   "survives every purge, including the full purge," implying it's
   immutable. Section 14.4 doesn't say whether a snapshot's captured state
   includes the audit log, and if restoring a snapshot rolls the audit log
   back to its snapshot-time contents, that would contradict "survives
   everything" for any audit entries logged between snapshot and restore.
   Worth an explicit design decision before Phase 29.

9. **`narrative_events.origin` enum may be missing a value.** It's defined
   as `ai`/`human` (4.1), but BetaCorp job-offer emails (11.1) and customer
   inbound traffic (11.2) are LLM-generated yet not employee-bot-authored
   "work" content, nor Principal-authored — a third, synthetic-external
   origin may be needed for accurate downstream filtering (digest
   selection, KPI counts).

10. **No seed roster is provided.** Section 26 says first-boot provisions
    "the 20 employees and the Principal," but no names, departments,
    roles, personalities, or starting pay are given anywhere in the spec.
    Phase 14 proceeds with a placeholder roster invented by the building
    agent; flagging so it can be swapped for a real one if the requester
    has specific people/departments in mind.

11. **Traefik's full multi-homing footprint isn't fully enumerated.**
    Section 22's network table only explicitly calls out Traefik's
    exception onto `net_mgmt`; it necessarily also needs to reach
    `net_office`, `net_mail`, and `net_dmz` to route to the services listed
    there, but the table doesn't say so directly. Worth confirming the
    full set explicitly before Phase 3.

12. **"Local model" fallback tier is unspecified.** Section 20 lists a
    local model as the last LiteLLM fallback but never says which model or
    how it's hosted — which has real implications for the 8–10 GB RAM
    budget in section 26 if that tier is ever actually exercised.

13. **Orchestrator vs. dedicated managers — one service or many?** Section
    24 says the orchestrator "exposes a control API covering every
    dashboard action in section 25," while several of those same actions
    (purge, snapshot, branding, chaos toggles) are elsewhere described as
    belonging to their own dedicated custom managers (Purge Manager,
    Snapshot Manager, Branding/Asset Manager). Unclear whether "the
    orchestrator" is meant to be a thin gateway fronting all these other
    services, or whether the spec is using "orchestrator" loosely to mean
    "the backend" collectively. This affects how many separately
    deployable custom services the phases above should assume versus how
    much can be one process — flagged before Phase 18 locks in an
    architecture.
