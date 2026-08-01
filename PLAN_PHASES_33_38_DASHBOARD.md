# Planning document — Phases 33–38 (Control Dashboard + hardening)

**Status: SIGNED OFF 2026-08-01 — cleared for implementation.**

## User sign-off decisions (2026-08-01)

1. **Tech stack**: APPROVED as recommended — React + Vite SPA served by a thin FastAPI BFF
   (`dashboard/` service).
2. **Authentication**: some kind of basic auth in front of the BFF. Decision: HTTP Basic Auth
   (single Principal user/password, credentials via `.env`, matching this repo's existing
   pragmatic posture on internal-only credentials) — the cheapest real option from §4's list,
   applied from Phase 33 onward rather than deferred to Phase 38, since the dashboard is
   reachable the moment it exists.
3. **Full-purge UX**: move the full-purge control out of the Data Management tab entirely and
   into a dedicated **Settings menu**, styled deliberately alarming — "nuclear launch button"
   framing: distinct danger-red section, unambiguous copy about what it destroys, visually
   isolated from every other control in Settings. Requires the user to confirm **no fewer than
   3 separate times** after first selecting "purge all data" before it actually fires (e.g. an
   initial click → a modal restating the consequences → a typed-confirmation-phrase step → a
   final "are you REALLY sure" step — the exact 3+ step sequence is an implementation detail for
   Phase 36/settings work, but must be at least 3 distinct affirmative user actions, not 3
   clicks on the same dialog). Scoped purges (the 10-checkbox list) stay on the Data Management
   tab as originally planned — this extra-hardened flow applies specifically to **full** purge.
4. **"Worker scale"**: user has no concept in mind for this either — confirmed genuinely
   undefined, not just under-specified. Decision: **omit entirely from Phase 33's first cut**,
   per the plan's own fallback recommendation. Do not build a placeholder control for it (unlike
   the speed slider, which the user DID want as a visible placeholder — worker scale isn't even
   defined enough to show a disabled control for). Revisit only if a concrete definition emerges
   later.
5. **Speed slider (Phase 32 dependency)**: build the control now, visibly present but disabled,
   labeled "Coming Soon" rather than hidden — matches the plan's original recommendation exactly.

---

**Planning only — no code written, no `docker-compose.yml` edits, no service directories
created.** Grounded in `fakeco-real-appliances-BUILD-PROMPT.md` §25 (control dashboard
requirements, lines 617-639), §26 (deployment), §27 (deliverables checklist), `PHASES.md` lines
707-822 (Phase 33-38 exit criteria), `important.md` (recurring gotchas), `PLAN_REMAINING_PHASES.md`
(prior dashboard cross-cutting risk notes, lines 289-365), `PLAN_PHASES_27_28_31_32.md` (what
Phase 27/28/31 actually built, to avoid duplicating Grafana panels or re-deriving chaos/observability
data sources), `Future_Plans.md` (Phase 32 deferred design), `BUILD_LOG.md`'s STATUS HEADER, and the
live `docker-compose.yml` topology.

**Important housekeeping note on this repo's docs:** `BUILD_LOG.md`'s STATUS HEADER (lines 5-13,
9) is currently **stale** — it still reads "Phases 19-20, 23-38 not started." That is no longer
true: `important.md`, `PLAN_REMAINING_PHASES.md`, and `PLAN_PHASES_27_28_31_32.md` all confirm
Phases 19, 20, 23, 27, 28, 29, 30, 31 are done and runtime-verified; only Phase 24 (pay
negotiation/performance review meeting type) and Phases 32 (deferred), 33-38 remain genuinely
unbuilt. This plan treats the STATUS HEADER's claim as out of date and relies on the more
recently-written planning docs instead. **Recommend refreshing the STATUS HEADER as a small,
separate fix — not part of this dashboard plan's scope, but flagged so it doesn't confuse whoever
reads it next.**

---

## 0. Grounding: what actually exists right now to build a dashboard against

Current custom services running in `docker-compose.yml` (all `fakeco-*` containers, confirmed by
grep against the live file): `postgres`, `docker-socket-proxy`, `cadvisor`, `node-exporter`,
`prometheus`, `dns` (Technitium), `traefik`, `mailserver`, `roundcube`, `mattermost` (+db),
`zammad` (+db/memcached/redis/es/init/railsserver/scheduler/websocket/nginx), `wikijs` (+db),
`nextcloud` (+db), `wordpress` (+db), `akaunting` (+db), `litellm`, `loki`, `promtail`, `grafana`,
`sim-clock`, `narrative-db-migrate`, `provisioning`, `accounting-engine`, `kpi-engine`,
`branding-manager`, `meeting-simulator`, `human-bridge`, `orchestrator`, `external-world`,
`snapshot-manager`, `purge-manager`. `dashboard/` itself is still an empty `README.md` stub — this
is the last major unbuilt piece besides Phase 24 and the deferred Phase 32.

Networks (from `docker-compose.yml` lines 3-90): `net_clients`, `net_office`, `net_mail`,
`net_dmz`, `net_data` (all `internal: true`), `net_llm_bridge` (only network with real internet
egress — LiteLLM only), `net_mgmt` (`internal: false`, **host-published for dashboard/monitoring
browser access** — this is explicitly where `dashboard/` belongs, alongside `grafana`, per the
network comment block at line 196: "Net: net_mgmt (dashboard talks to it; dashboard is on
net_mgmt)"). The dashboard backend will therefore need multi-homing similar to Traefik/orchestrator
— `net_mgmt` (browser-reachable) plus whichever internal networks let it reach each backend service
it aggregates (`net_data` for direct Postgres reads, `net_office`/`net_mail`/`net_dmz` if it ever
needs to reach appliances directly rather than through their owning microservice — recommend
avoiding this and always going through the owning service's own API instead, to avoid duplicating
business logic).

**Phase 32 status — genuinely blocking, must be called out per-tab below**: confirmed DEFERRED
(`Future_Plans.md`, `PLAN_PHASES_27_28_31_32.md` line 21). `sim-clock` has no live `/speed` mutation
endpoint yet — `SPEED_MULTIPLIER` is still a static env var baked in at container boot
(`docker-compose.yml`'s `sim-clock` service, `"${SPEED_MULTIPLIER:-1.0}"`). **Any dashboard control
that would call a live speed-slider API has no backing endpoint today.** This is real, not a
theoretical gap — flagged explicitly in the per-tab feature list below (Phase 33's Simulation
tab) rather than glossed over.

**Phase 24 status — also a real gap**: `PLAN_REMAINING_PHASES.md`/`PHASES.md` both note Phase 24
(pay negotiation / performance review meeting type) is not started. `PHASES.md` line 734 makes
Phase 34's Payroll tab exit criteria explicitly dependent on it ("a cut correctly opens a
`pay_negotiation` meeting via Phase 24, never applying directly"). This is the dashboard's second
real backend gap, on top of Phase 32.

---

## 1. Tech stack recommendation

**Recommendation: a small React + Vite single-page app, served as static files by a thin FastAPI
backend-for-frontend (BFF) that aggregates/proxies calls to the other services.**

### Why not server-rendered Python (htmx + FastAPI)

Section 25's tab list is unusually UI-heavy for what's otherwise an all-Python-backend repo: a
node/edge relationship graph (Phase 34, HR tab), live-updating chat/ticket feeds and a sim-time
display for the `/tv` route (Phase 37), a speed slider, multiple tables with inline editors
(payroll, KPI scoreboards), and a log-tail stream (Traefik/Technitium, Phase 37). htmx can do
partial-page swaps well for CRUD-style tables (Payroll, Company Direction, Accounting), but the
node/edge graph and the auto-cycling `/tv` wall are the kind of thing that gets fought rather than
built in a swap-based model — you'd end up reaching for a JS charting/graph library inside htmx's
partials anyway, at which point you have both stacks' complexity without either one's full
benefit.

### Why not a heavier framework (Next.js, Angular, etc.)

This is explicitly a solo/small-scale simulation project (per `important.md`'s framing throughout
and the repo's consistent "one FastAPI service per concern, python:3.12-slim, no framework
sprawl" pattern). A full SSR framework adds build/deploy complexity (Node runtime in production,
routing/data-fetching conventions to learn) with no real benefit here — there's no SEO need, no
multi-tenant auth complexity, and the traffic pattern is "one Principal user, browser open most of
the time." Vite's dev server + a static `npm run build` output is the right amount of tooling for
this project's actual scale.

### Recommended shape

- **Frontend**: React + Vite, TypeScript optional (plain JS is fine given project scale — recommend
  TS anyway since the many tab-specific data shapes benefit from typed API responses, cheap
  insurance against a solo-dev's copy-paste-across-tabs mistakes). One shared design shell (nav +
  tab routing via a lightweight router like `react-router`), each tab a separate route/component.
  Charting: a single lightweight library reused everywhere a chart is needed (KPI trends, cost
  burn, relationship graph) — recommend `recharts` for standard charts (bar/line, matches Grafana's
  visual idiom loosely) and a small dedicated graph library (`react-force-graph` or `reactflow`,
  whichever proves simpler in a 30-minute spike) for the HR relationship node/edge view specifically
  — don't force one library to do both jobs.
- **Backend-for-frontend**: new `dashboard/` FastAPI service, following the exact same
  `Dockerfile`/`requirements.txt`/`main.py`/`/health` pattern as every other custom service in this
  repo (`python:3.12-slim`, `httpx` client wrapper per aggregated service, the
  `python -c "import urllib.request..."` healthcheck per `important.md` #1 — no curl). It:
  - Serves the built Vite static bundle (single `StaticFiles` mount) so there's exactly one
    container/port for the whole dashboard, consistent with this repo's "one container per
    deliverable" convention.
  - Exposes a small set of REST/aggregation endpoints per tab (e.g. `GET /api/narrative/summary`
    aggregating `narrative_threads` + `action_items` + `pending_reactions/approvals` in one call
    rather than making the browser fan out to 4 different services) — this is the actual value of a
    BFF layer here: fewer round-trips from the browser, and a single place to enforce dashboard-level
    access control (see §6 below) rather than teaching every backend microservice about dashboard
    auth.
  - For simple pass-throughs (e.g. "trigger a chaos stop"), just forwards to the owning service's
    existing endpoint — no duplicated business logic, matching every other phase's "reuse the
    existing service, don't rebuild logic" pattern established in `PLAN_PHASES_27_28_31_32.md`.
  - For `/tv` and the Errors panel's log tail, uses Server-Sent Events (simplest one-way live-update
    mechanism FastAPI supports natively, no extra dependency) rather than WebSockets — nothing on
    this dashboard needs bidirectional low-latency messaging, SSE is enough and keeps the stack
    simpler.

### Trade-offs acknowledged

- **Dev complexity**: two toolchains (Python + Node) instead of one is the real cost. Mitigated by
  keeping the split extremely clean — the BFF has almost no business logic of its own, it's a thin
  aggregation/proxy layer, so there's very little "where does this logic live" ambiguity to manage.
- **Consistency with the repo**: every other service is pure Python; this is the one place that
  isn't. Judged worth it given section 25's genuinely UI-heavy requirements (interactive graph,
  live feeds, sliders, multi-tab SPA navigation) — a plain server-rendered app would fight these
  requirements rather than serve them.
- **Realistic scope for solo project**: recommend NOT reaching for a component library beyond
  something minimal (e.g. plain CSS or a lightweight utility layer) — no need for a full design
  system for a single-user internal tool.

**This tech-stack choice is the single biggest open decision in this whole plan and needs explicit
user sign-off before Phase 33 starts** (see §6, Risks/open questions).

---

## 2. Phase-by-phase: scope, backend readiness, and feature list

### Phase 33 — Shell + Simulation / LLM / Narrative tabs

**Spec grounding**: `PHASES.md` lines 707-720 (spec section 25, partial); build-prompt §25 lines
619-621.

**Backend readiness**:
- Simulation controls: sim-clock (Phase 12, verified) has ticker + presumably a `/set_speed`-style
  endpoint already used at boot, but **no live runtime speed-change endpoint** — Phase 32 (deferred)
  is what would add `POST /speed`. **Blocked.**
- "Worker scale" (build-prompt §25/`PHASES.md` line 714's "worker scale... controls") — no concept
  of this exists anywhere in the current architecture (no worker-pool abstraction in any service);
  this was already flagged as needing its own investigation in `PLAN_REMAINING_PHASES.md` line 311
  and remains unresolved. **Blocked / needs definition before it can be built at all** — recommend
  treating "worker scale" as out of scope for Phase 33's first cut, revisit once/if a concrete
  meaning is defined (e.g. does it mean orchestrator tick concurrency? Number of simulated
  employees processed per tick? Nothing in the spec or current code defines this concretely).
- LLM status: LiteLLM config + `/spend/logs` (both proven working), Phase 31's `llm-spend.json`
  Grafana panel already built the exact query logic the dashboard tab needs — reuse, don't
  re-derive.
- Narrative view: `narrative_threads`, `action_items`, `pending_reactions`, `pending_approvals`
  (Phase 13/18, verified) — straightforward reads. Phase 27's `pending_actions` table (verified)
  is a bonus data source worth surfacing here too (retry-queue depth), even though spec doesn't
  explicitly name it — it's genuinely narrative-adjacent ("is anything stuck").

**Feature list**:
- Dashboard shell: top nav with tabs for every section-25 area (this phase builds the shell that
  Phases 34-37 plug tabs into), served on `net_mgmt`, gated behind HTTP Basic Auth (2026-08-01
  sign-off — applied from this phase onward, not deferred to Phase 38).
- Settings menu (new, per 2026-08-01 sign-off — not originally its own spec section, added here
  as the home for the full-purge "nuclear launch" control): a distinct nav item, separate from
  the Data Management tab. Houses the full-purge flow described under Phase 36/38 below — kept
  physically and visually separate from every routine control in the dashboard shell.
- Simulation tab:
  - Sim-time display (current sim date/time, current speed multiplier) — read-only, live via
    sim-clock's existing `GET` endpoint. **Available now.**
  - Speed slider / preset buttons (0.1/0.25/0.5/1/2/5/10x) — **NOT AVAILABLE YET.** Render as a
    disabled control with a tooltip/badge ("Requires Phase 32 — deferred, see Future_Plans.md")
    rather than omitting it entirely, so the UI shape is ready the day Phase 32 lands.
  - Start/stop simulation — needs clarification: does this mean stopping `orchestrator`'s tick loop
    (a real, buildable control against orchestrator's existing process) or stopping the whole
    compose stack (out of scope for a web dashboard)? Recommend scoping to "pause/resume
    orchestrator's tick loop" via a small new orchestrator endpoint — buildable now, doesn't need
    Phase 32.
  - Worker scale control — **NOT AVAILABLE, concept undefined.** Omit from Phase 33's first cut;
    flag as an open question (see §6).
- LLM Status tab:
  - Current provider + fallback chain display (from `litellm/config.yaml`, read via LiteLLM's own
    config-introspection endpoint if one exists, else parse the mounted config file). **Available.**
  - Manual override control (force a specific provider) — needs a LiteLLM API check for whether
    this is settable at runtime vs. config-file-only; if config-file-only, this control would need
    a container restart to take effect, worth surfacing that caveat in the UI. **Available with
    caveat.**
  - Usage/cost view (spend by day/provider) — reuses Phase 31's `llm-spend.json` query logic.
    **Available.**
  - Speed-adjusted burn rate ($/wall-clock-hour) — Phase 31's panel already annotates with
    `speed_multiplier`; the dashboard version is the same computation. **Available**, though its
    usefulness is naturally limited until Phase 32 makes speed changes live (today speed is fixed
    at boot, so "speed-adjusted" is currently just "current fixed multiplier applied to the same
    number" — still worth building, just flag as a lower-value feature until Phase 32 lands).
- Narrative tab:
  - Open threads list (from `narrative_threads`, filterable by type including `crisis` threads from
    Phase 28). **Available.**
  - Action items list (open/closed, assignee). **Available.**
  - Pending reactions/approvals queue (from `pending_reactions`/`pending_approvals`). **Available.**
  - Meetings list (recent + upcoming, all 5 meeting types incl. `crisis_response`). **Available.**
  - Pending-actions retry-queue depth widget (Phase 27's `pending_actions` table) — bonus, not
    spec-named but cheap to add given the table already exists. **Available.**

---

### Phase 34 — HR, Payroll, Accounting tabs

**Spec grounding**: `PHASES.md` lines 724-739; build-prompt §25 lines 622-626.

**Backend readiness**:
- HR/roster: `provisioning`'s Fire/Hire endpoints (Phase 14, verified) — direct reuse. **Available.**
- Relationship view: `employee_relationships` table (Phase 20, verified) — direct reads.
  **Available**, node/edge visualization is purely a frontend charting-library task (see §1).
- Payroll: raise-applies-immediately path already exists via `accounting-engine`'s existing raise
  endpoint (Phase 15, reused by Phase 23's KPI-driven raises). **Available for raises.** Cut-routes-
  to-`pay_negotiation`-meeting is explicitly Phase 24's job, and **Phase 24 is not built** —
  confirmed gap, matches `PHASES.md` line 734's own wording. **Blocked for the "cut" path
  specifically** — raises can ship in Phase 34's first cut, cuts must be a disabled/placeholder
  control until Phase 24 lands.
- Accounting: cash balance + P&L/balance-sheet deep link (Akaunting, live), expense-approval queue
  (`pending_approvals`, Phase 15, verified), payroll history (accounting-engine's transaction log),
  audit-correction log (Books Auditor output, Phase 15/28, verified — Phase 28 already proved this
  data is real and queryable). **All available.**

**Feature list**:
- Org Chart / HR tab:
  - Roster table: name, department, title, status (active/vacant/terminated/resigned/on-PTO — the
    last one from Phase 19's `pto_calendar`, worth surfacing even though not spec-named
    explicitly, since it directly affects who's "available" at a glance).
  - Fire button per employee row (confirmation dialog) → `provisioning`'s terminate endpoint.
  - Hire button (opens a small form: department, title) → `provisioning`'s `provision_employee()`.
  - Relationship graph view: node = employee, edge = `employee_relationships` row, edge weight/color
    = `affinity_score`. Click a node to filter/highlight that employee's edges.
- Payroll tab:
  - Per-employee pay editor: current pay, an input to propose a new figure.
  - **Raise path (increase)**: Save button applies immediately via accounting-engine's raise
    endpoint, confirmation toast, shows in payroll history immediately. **Available now.**
  - **Cut path (decrease)**: Save button — **DISABLED / placeholder until Phase 24 exists.** Show a
    tooltip: "Pay cuts require Phase 24 (pay negotiation meetings) — not yet built." Do not silently
    allow a cut to apply immediately; that would violate the spec's explicit "never applying
    directly" requirement (`PHASES.md` line 735) — better to disable the control than build a wrong
    behavior.
  - Payroll history table (all pay changes, timestamped, reason/source).
- Accounting tab:
  - Cash balance widget (from Akaunting, live).
  - "Open in Akaunting" deep link to the real P&L/balance-sheet report page.
  - Expense-approval queue: table of `pending_approvals` rows with Approve/Reject buttons wired to
    accounting-engine's existing approval endpoints.
  - Payroll history (shared with Payroll tab, or a filtered accounting-focused view of the same
    data).
  - Audit-correction log: table of Books Auditor findings/corrections (Phase 15/28's `run_audit()`
    output), including entries seeded by Phase 28's "surprise audit" crisis preset.

---

### Phase 35 — External World, KPI/Performance, Company Direction tabs

**Spec grounding**: `PHASES.md` lines 743-757; build-prompt §25 lines 627-631, §8.

**Backend readiness**:
- External World: `external-world`'s `system_audit_log` (BetaCorp offers/resignations, verified) +
  `customers` table (seeded per migration 005, per `PLAN_REMAINING_PHASES.md` line 8). **Available.**
- KPI/Performance: `kpi_snapshots` (Phase 23, populated), review-mode toggle (Phase 23's "review &
  approve mode toggle" config flag, currently env-var-only per `PLAN_REMAINING_PHASES.md` line
  150-152 — the dashboard tab is precisely what turns this into a real UI toggle rather than a
  restart-required env var). **Available**, though "actually switching Phase 24's behavior" per
  `PHASES.md` line 753 has the same Phase 24 gap as Phase 34's payroll-cut path — the toggle itself
  can be built and can flip the flag that gates *raises* into review mode (already real, via
  accounting-engine's existing approval queue), but anything about switching *cut* behavior
  specifically inherits Phase 24's absence.
- Company Direction: `company_directives` table (Phase 13, verified) + Wiki.js pinned-page sync
  (pattern already proven in meeting-simulator's Wiki.js integration). **Available.**

**Feature list**:
- External World tab:
  - BetaCorp news feed: chronological list from `system_audit_log`, filtered to BetaCorp-related
    entry types.
  - Job-offer/resignation log: same source, filtered to those specific event types.
  - Customer pipeline / at-risk list: table from `customers`, sortable by status/risk flag.
  - Revenue by customer: chart (bar, one bar per customer) joining `customers` with Akaunting
    revenue transactions — same data Phase 31's `customer-pipeline-revenue.json` Grafana panel
    already reads; reuse that query.
- KPI/Performance tab:
  - Department scoreboard: table/chart of `kpi_snapshots` aggregated by department.
  - Employee scoreboard: same, per-employee, sortable by metric.
  - Performance-review log: list of past raises applied via Phase 23's formula, with tier
    (top-quartile +5%, second +2%, rest +0%) shown per entry.
  - Automatic vs. review-and-approve mode toggle: a real UI switch that writes to whatever config
    store Phase 23's flag reads from (recommend, if it's currently an env var only, this dashboard
    phase adds a tiny `kpi-engine` config table/row so the toggle can be live without a container
    restart — a small, scoped addition to kpi-engine, not a new service).
- Company Direction tab:
  - Textarea showing current `company_directives` text.
  - Save button: writes new row/version to `company_directives`, triggers the existing Wiki.js
    pinned-page sync.
  - History view: prior versions with timestamps (needs `company_directives` to be append-only /
    versioned rather than update-in-place — confirm current schema supports this before building;
    if it's currently a single mutable row, this tab needs a small additive migration to add a
    history table).

---

### Phase 36 — Chaos, Data Management, Branding tabs

**Spec grounding**: `PHASES.md` lines 761-775; build-prompt §25 lines 632-634.

**Backend readiness**: this is the best-supported phase in the whole dashboard batch — Phases 27,
28, 29, 30 were all built specifically to have their dashboard tab be a thin wiring exercise.
- Chaos: orchestrator's `/chaos/appliances/{name}/{start|stop|restart}` (Phase 27, verified) +
  `/chaos/trigger-event` (Phase 28, verified). **Fully available.**
- Data Management: `purge-manager`'s scoped + full purge endpoints and `snapshot-manager`'s
  save/restore (Phase 29, verified, including the mandatory-pre-purge-snapshot rule and typed
  confirmation gate). **Fully available** — `PHASES.md` line 772's explicit note to "re-verify the
  confirmation gate specifically through the UI, not just the API" is the one real new testing
  obligation this phase adds, not new backend work.
- Branding: `branding-manager`'s bulk-apply/randomize/reset-to-default endpoints (Phase 30,
  verified). **Fully available.**

**Feature list**:
- Chaos tab:
  - Per-appliance status grid: one row/card per `fakeco-*` container on the chaos allow-list, live
    up/down/starting state (poll or SSE from orchestrator's reachability data).
  - Stop / Start / Restart buttons per appliance row → orchestrator's existing chaos endpoints.
    Confirmation dialog before Stop (reversible but still meaningfully disruptive).
  - Outage log: list of past outages from `narrative_events` (Phase 27 logs these in sim-time
    phrasing already — display verbatim).
  - Trigger Event control: dropdown of canned scenarios (data breach / surprise audit / viral
    complaint, per Phase 28's config) + free-text field for a custom scenario + a Trigger button.
    Show the resulting crisis thread/meeting/action-items once created.
- Data Management tab:
  - Scoped purge: checkbox list matching purge-manager's ten scopes (Emails, Chat, Tickets, Wiki,
    Meetings & narrative memory, Accounting ledger, External world, KPI history, Roster, Company
    direction) + a "Purge selected" button.
  - **Typed-confirmation gate**, rendered as a real modal requiring the user to type an exact phrase
    (e.g. "PURGE") before the button enables — this is the UI-level re-verification `PHASES.md`
    explicitly calls for; do not just trust that the API's own gate is "good enough," build the UI
    gate as a genuinely separate check.
  - Full purge: **MOVED per 2026-08-01 sign-off** — no longer lives on this tab at all. See the
    dedicated "Settings menu" note under Phase 33's shell description and Phase 38's hardening
    scope for the "nuclear launch" full-purge flow's actual home.
  - Snapshots: list of existing snapshots (name, sim-time tag, size), "Save Snapshot Now" button,
    Restore button per snapshot (own confirmation gate — restoring silently discards anything since
    that snapshot), Delete button per snapshot.
- Branding tab:
  - Asset library browser: avatar images + emoji pack, grid view.
  - Per-employee avatar picker (single employee at a time).
  - Bulk apply: employee multi-select + action (randomize / apply-one-to-all / reset-to-default) →
    branding-manager's `/branding/bulk-apply`.

---

### Phase 37 — TV wall, Errors panel, deep links, log tail

**Spec grounding**: `PHASES.md` lines 779-795; build-prompt §25 lines 635-638, §18.

**Backend readiness**: per spec's own framing this "should need no meaningful new backend logic"
— it composes data every other tab already exposes. The one piece needing new backend work is the
Errors panel and the Traefik/Technitium log tail, both flagged below.
- `/tv` composition: reuses Narrative (33), Accounting (34), KPI (35) tab data. **Available**, pure
  frontend composition + auto-cycle timer.
- Errors panel: **no dedicated mechanism exists yet.** Per `PLAN_REMAINING_PHASES.md` line 353's own
  recommendation (still valid), the cheapest path is a Loki query scoped to `level="ERROR"` across
  all `fakeco-*` containers, rather than adding a new per-service exceptions table/endpoint. Loki is
  already running and aggregating every container's stdout (Phase 11, verified) — this is a
  dashboard-side query against existing infrastructure, not new backend instrumentation.
  **Available via Loki, no new service code needed** (only a Loki query embedded in the BFF).
- Deep links: static config mapping, no backend needed beyond a JSON config file the BFF serves.
  **Available.**
- Traefik/Technitium log tail: same Loki mechanism, and per `PLAN_REMAINING_PHASES.md` line 359 this
  was "already prototyped as a Grafana panel" (`traffic-and-activity.json`) — the dashboard just
  needs to replicate that same Loki query, not invent a new one. **Available.**

**Feature list**:
- `/tv` route:
  - No navigation chrome, no interactive controls (spectator view only, per spec).
  - Auto-cycling panels (fixed interval, e.g. 15-20s per panel): live chat feed (recent Mattermost
    posts across channels), live ticket feed (recent Zammad tickets), financial snapshot (cash
    balance, burn rate), KPI highlights (top movers this period), sim-time/speed display, and a
    "recent digest highlights" panel (weekly-digest content from kpi-engine, if that concept
    exists — confirm against kpi-engine's actual output before building this specific panel).
- Errors panel:
  - Table of recent unhandled exceptions, one row per log line matching `level="ERROR"` across
    every custom service container, via a Loki query proxied through the BFF.
  - Filter by service name.
  - Explicitly covers every custom service named in spec §25's Errors-panel line: accounting-engine,
    meeting-simulator, human-bridge, orchestrator, external-world, kpi-engine, branding-manager,
    snapshot-manager, purge-manager.
- Deep links panel (**amended 2026-08-01, user sign-off — no iframe embedding, direct links
  only**): static list: Mattermost, Zammad, Wiki.js, Nextcloud, WordPress, Akaunting, Roundcube,
  Grafana — each linking to its real Traefik-routed hostname (the Principal's own login page for
  each, not just the generic home page), with the Principal's **username and password for that
  specific appliance displayed directly next to its link** (read from `.env`/each appliance's
  known Principal credential — the same credentials already used throughout this project's
  provisioning, not new secrets). Considered and explicitly rejected: embedding each app's UI via
  iframe — most appliances (Mattermost, Nextcloud, Akaunting) set `X-Frame-Options`/CSP
  `frame-ancestors` headers by default specifically to prevent this, requiring a Traefik
  middleware to strip those headers per-app (a real security trade-off, since that protection
  exists on purpose), plus embedding doesn't remove each app's own separate login — you'd still
  see a login form inside the iframe without real SSO across all appliances, which is out of
  scope. Direct links + visible credentials achieves the "get me into that app fast" goal without
  that added complexity/risk.
- Log tail:
  - Live-streaming (SSE) view of Traefik + Technitium (DNS) container logs via Loki, reusing the
    existing `traffic-and-activity.json` Grafana query.

---

### Phase 38 — Deployment hardening, first-boot polish, README

**Spec grounding**: `PHASES.md` lines 799-822; build-prompt §26-27.

This phase is last by construction — it depends on everything (Phases 0-37) and is explicitly
"no new services... validation and documentation work" per its own Size note. Fits naturally after
Phase 37 for this dashboard batch specifically, and after Phase 24 (still outstanding) for the
project as a whole, since Phase 38's exit criteria include walking the full §27 deliverables
checklist to confirm every item is checked off.

**What's realistically in scope by the time this batch reaches Phase 38:**
1. **Dashboard-specific hardening** (new, relative to the general Phase 38 scope already described
   in `PLAN_REMAINING_PHASES.md` lines 369-406):
   - **Authentication/access control on the dashboard itself.** This did not exist as a concern
     before the dashboard existed — `net_mgmt` is explicitly host-published (`internal: false`),
     meaning the dashboard is reachable from the host browser without any network-level isolation
     protecting it. A dashboard with a full-purge button and per-appliance stop/start controls
     reachable with zero authentication is a real safety gap, not just a nice-to-have (see §6 —
     this needs explicit user sign-off on the approach, being flagged here as Phase 38's job to
     implement once decided).
   - Error-state handling across every tab: what each tab shows when its backing service is down
     (should degrade gracefully — a KPI tab shouldn't crash the whole SPA if kpi-engine is
     unreachable, it should show a clear "service unavailable" state, especially given the Chaos
     tab exists specifically to take services down on purpose).
   - Placeholder-control cleanup pass: by Phase 38, confirm whether Phase 24 and/or Phase 32 have
     landed; if so, wire up the previously-disabled controls (payroll cuts, speed slider, worker
     scale once/if defined) for real. If not, confirm the disabled states still read clearly rather
     than looking like a bug.
2. **General Phase 38 scope** (from the existing `PLAN_REMAINING_PHASES.md` plan, still valid,
   repeated here for completeness since this document supersedes that one for phases 33-38):
   clean-environment first-boot test, first-boot automation (roster + Principal provisioning,
   Akaunting chart-of-accounts, initial branding pass all running unattended), `.env.example`
   accuracy audit (now needs to include every dashboard-related env var — BFF service URLs, any
   session/auth secret), and the README itself — deployment steps, resource footprint (measure the
   real RAM/disk usage of the now much-larger stack against the spec's 8-10GB estimate), a
   troubleshooting section, and **a walkthrough of every dashboard tab** (this is a Phase 38 exit
   criterion `PHASES.md` line 816 names explicitly, and it's naturally the first point in the whole
   project where a tab-by-tab user-facing walkthrough is even possible to write, since the tabs
   didn't exist before).

**Verification plan**: same clean-environment `docker compose up -d` test as the general Phase 38
plan, plus explicitly logging into the dashboard as the final step and clicking through every tab
to confirm nothing 500s and every "not yet available" placeholder (if Phase 24/32 are still
outstanding at this point) reads clearly rather than looking broken.

---

## 3. Dependencies / build order across 33-38

Recommended order: **33 → 34 → 35 → 36 → 37 → 38**, matching `PHASES.md`'s own numbering exactly —
there's no reason to deviate, since each phase's dependencies are already satisfied by the time it
starts (see per-phase "backend readiness" above) except for the two genuine gaps:

- **Phase 24 (pay negotiation)** is not part of this batch and not yet planned. It blocks: Phase
  34's payroll-cut path, and partially Phase 35's review-mode toggle (the raise half works without
  it, the cut-behavior-switching half doesn't). **Recommend**: build Phases 33-38 without waiting
  for Phase 24, shipping the affected controls in a disabled/placeholder state as described above,
  rather than blocking the entire dashboard batch on an unplanned phase. Revisit once Phase 24 is
  scheduled.
- **Phase 32 (speed slider, deferred)** blocks only the speed-slider control and the
  "speed-adjusted burn rate" feature's real usefulness within Phase 33's Simulation/LLM tabs.
  Same recommendation: ship Phase 33 with that one control disabled, not blocked.

No phase in 33-37 blocks another phase in 33-37 out of order except the trivial "shell must exist
before tabs plug into it" (33 builds the shell) and Phase 37's explicit dependency on 33-36 (it
composes their already-exposed data, per its own spec wording). Phase 38 is last across the whole
project, not just this batch, since its exit criteria reference "everything (Phases 0-37)."

---

## 4. Risks / open questions needing user sign-off

1. **Tech stack choice (React/Vite SPA + FastAPI BFF) — the single biggest open decision in this
   plan.** Needs explicit sign-off before Phase 33 starts. Alternative considered and rejected:
   server-rendered htmx+FastAPI (fights the graph-viz/live-feed/slider requirements); a heavier SPA
   framework (unjustified complexity for this project's solo/small scale).

2. **Authentication/access control for a control-plane dashboard that can trigger chaos events and
   full purges — a real safety concern, not a formality.** `net_mgmt` is host-published with no
   network-level isolation. Concretely: anyone who can reach the dashboard's URL in a browser can
   currently, by this plan's design, stop any appliance, trigger a crisis event, or (worst case)
   run a full data purge — the purge-manager's typed-confirmation gate protects against
   *accidental* clicks, not against an *unauthorized* user reaching the button at all. This plan
   does not resolve this on its own; options to put in front of the user for Phase 38 (or earlier,
   if the user wants it sooner):
   - Simple HTTP Basic Auth in front of the BFF (single Principal user, minimal effort, matches this
     project's generally pragmatic posture on internal-only credentials per Phase 31's precedent of
     reusing existing admin credentials rather than provisioning new roles).
   - A single shared session cookie/password gate (slightly more UI-friendly than Basic Auth, still
     minimal effort).
   - Rely on network-level protection only (e.g. don't actually expose `net_mgmt`'s host port beyond
     localhost/VPN) — cheapest, but weaker if the host is ever reachable beyond localhost.
   - Recommend, absent a stronger user preference: HTTP Basic Auth on the BFF as a first pass (cheap,
     real, better than nothing), revisited in Phase 38 if the user wants something stronger.
   **This needs an explicit user decision — do not default silently to "no auth."**

3. **The full-purge button specifically deserves its own UX sign-off**, independent of the general
   auth question above. Even with auth in place, a single dashboard button that can destroy the
   entire simulation's accumulated state (30+ employees, real meetings, Akaunting transactions,
   Zammad tickets) sitting in the same UI as routine controls is a real design risk. Recommend
   (for user sign-off, not unilaterally decided here): visually isolating the Data Management tab's
   full-purge control from every other control (distinct color/section, not just a checkbox among
   others), requiring the typed-confirmation phrase to be genuinely un-guessable/exact rather than
   a simple "yes" click, and displaying a clear reminder of when the last snapshot was taken
   immediately next to the button (purge-manager already mandates a pre-purge snapshot per Phase
   29 — surface that fact prominently in the UI, not just enforce it silently server-side).

4. **"Worker scale" is undefined** — build-prompt/`PHASES.md` name it as part of Phase 33's
   Simulation tab, but nothing in the current architecture defines what it means concretely (no
   worker-pool abstraction exists anywhere). Needs the user to clarify intent (does it mean
   orchestrator tick concurrency? Simulated-employee batch size per tick? Something else?) before
   this specific control can be scoped, let alone built. Recommend omitting it from Phase 33's
   first cut and treating it as a follow-up once defined, rather than guessing at an implementation.

5. **Company Direction history** (Phase 35) may need a small additive migration if
   `company_directives` is currently a single mutable row rather than versioned — cheap to add, but
   worth confirming against the actual schema before Phase 35 starts rather than assuming.

6. **Phase 24 and Phase 32 gaps are real and affect user-visible dashboard behavior** (payroll cuts,
   speed slider, review-mode cut-switching) — this plan's recommendation is to ship the rest of the
   dashboard now with those specific controls visibly disabled/placeholder rather than delaying the
   whole batch, but that's a scope trade-off worth the user explicitly agreeing to rather than
   assuming.

7. **Deep links panel now displays each appliance's Principal username/password in plaintext next
   to its link (2026-08-01 sign-off).** Noting for the record rather than re-litigating: this is
   protected by the same dashboard-wide HTTP Basic Auth gate as every other tab, and these are the
   Principal's own credentials for appliances only reachable on the project's internal Docker
   networks — acceptable given the project's existing pragmatic posture on internal-only
   credentials (same reasoning as Phase 31's datasource-credential reuse). If the dashboard's own
   auth is ever weakened or removed, this panel's exposure should be re-reviewed.

8. **BUILD_LOG.md's STATUS HEADER is stale** (see §0) — recommend a quick separate fix, not blocking
   this plan, but worth doing before or alongside Phase 33 so the next agent/session picking this up
   isn't misled by it.
