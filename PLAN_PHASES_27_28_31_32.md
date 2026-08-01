# Planning document — Phases 27, 28, 31 (Phase 32 deferred)

Status: **SIGNED OFF 2026-07-31 — cleared for implementation, Phases 27/28/31 only.**

## User sign-off decisions (2026-07-31)

1. **Phase 27 idempotency keys**: apply to ALL `pending_actions` types, not just money-touching
   ones. Simpler, more consistent, and the overhead is negligible.
2. **Phase 28 open questions** (narrative_threads priority column, meeting-simulator attendee
   override): left to implementer judgment, optimizing for best QOL/coherence for the end user.
   Decision: add a `priority` column to `narrative_threads` if one doesn't already exist (cheap,
   keeps crisis threads visibly distinct from routine ones — better UX once dashboards exist),
   and extend `meeting-simulator`'s `select_attendees()` to accept an optional externally-forced
   attendee list for `crisis_response` (needed for the custom free-text scenario to work at all,
   and it's a small, additive extension point rather than a restructure).
3. **Phase 31 Grafana datasource credentials**: reuse existing admin credentials already in
   `.env` rather than provisioning new read-only DB roles, unless creating new roles turns out
   to be no harder — in which case prefer the more secure read-only route. Implementer should
   make the call live based on how much friction the read-only route actually adds.
4. **Phase 32 (speed slider full integration)**: DEFERRED, not being built in this pass. Full
   design content moved to `Future_Plans.md` so it isn't lost. Do not build any part of it now.

**Recommended build order for the phases actually being built: 31 → 27 → 28.**

---

Planning only — no code written, no `docker-compose.yml` edits, no service directories created.
Grounded in `fakeco-real-appliances-BUILD-PROMPT.md` (the original spec — §13.1, §13.2, §19.2-
19.5, §21, §24), `PHASES.md` (exit criteria for Phases 27/28/31/32, lines 580-700), `BUILD_LOG.md`
(current build status), `important.md` (recurring gotchas), and the live `docker-compose.yml`
(current service/network/profile topology as of the Phase 29/30 commits). These four phases were
explicitly flagged in `PLAN_REMAINING_PHASES.md` line 129 and `important.md` line 129 as "not
planned at all yet" — this document closes that gap.

Style/pattern baseline (unchanged from `PHASE29_PLAN.md`): every new custom service follows
`Dockerfile` (python:3.12-slim) + `requirements.txt` + `main.py` (FastAPI + httpx + asyncpg) +
`/health` endpoint using the `python -c "import urllib.request..."` healthcheck (curl is not
installed — see `important.md` #1), gated behind `profiles: [phaseN, ...]`, labeled
`fakeco.service`/`fakeco.phase`/`fakeco.managed`.

---

## Phase 27 — Chaos: service availability controls

### 1. What it is

Spec §13.1 (`fakeco-real-appliances-BUILD-PROMPT.md:374-384`): a dashboard-toggle-backed control
API that actually stops/starts/restarts a labeled appliance container via
`tecnativa/docker-socket-proxy` (never the raw socket), restricted to START/STOP/RESTART on
labeled containers only. The orchestrator must treat outages as first-class: a reachability check
before any action, queuing in `pending_actions` (wall-clock-based retry — a container being down
is a physical fact independent of sim speed) if unreachable, an optional visible reaction
(`reactive_outage_behavior`), and a `narrative_event` phrased in sim-time terms logging the
outage. `PHASES.md:580-597` gives the exit criteria: a control-API endpoint (dashboard UI is
explicitly deferred to Phase 36), a mid-flow-stop test proving queue-and-retry rather than
crash/error, a rejected-disallowed-call test, and the sim-time-phrased `narrative_event`.

**Explicit dependency note from the spec itself:** `PHASES.md:390` (Phase 18's own spec-sections
line) says the `pending_actions` retry queue is "built [in Phase 18] as core reliability
infrastructure, wired to dashboard toggles in Phase 27" — i.e. Phase 27 is meant to *extend* an
already-existing retry queue, not build one from scratch.

### 2. What already exists vs. what's missing

- **Missing entirely:** `important.md:124-126` and `BUILD_LOG.md`'s STATUS HEADER both confirm
  Phase 18's orchestrator has **no real `pending_actions` retry-queue** and no
  reaction→approval→action-item→filler priority loop — it is "a fixed sequence of scheduled-job
  checks instead. Not yet assigned to anyone." This means Phase 27's own stated dependency (Phase
  18's retry queue) does not actually exist yet, despite `PHASES.md` treating it as already-built
  infrastructure. **This is a real gap between the spec's assumed sequencing and this repo's
  actual state** and must be resolved as part of Phase 27's own scope (see §4 dependencies below)
  or explicitly folded in as Phase 31's true prerequisite work — the user's rough phase-32
  guidance in the task prompt calls this out as a likely Phase 31 item, but the spec text
  (`PHASES.md:390`) assigns it to Phase 18/27, not Phase 31. This document treats it as Phase 27
  scope, since Phase 27 is the first phase that actually *needs* a working retry queue to satisfy
  its own exit criteria (mid-flow-stop-and-retry test).
- **Exists:** `docker-socket-proxy` (Phase 1, `docker-compose.yml:199-241`) is already configured
  correctly for this phase's needs — `CONTAINERS: 1`, `POST: 1`, everything else `0` (including
  `EXEC: 0`, which stays untouched per the Phase 29 precedent). No compose changes needed to the
  proxy itself.
  Orchestrator (`docker-compose.yml:1433-1487`) already exists as a FastAPI service on
  `net_clients` + `net_data` + `net_office` + `net_mail`, with a `/health` endpoint and its own
  tick loop (`ORCHESTRATOR_TICK_INTERVAL`).
  `narrative_events` table exists (Phase 13, `002_narrative_core.sql`) and is already written to
  from multiple services — the outage-logging requirement is a straightforward reuse.
- **Missing:** any `pending_actions` table/migration, any orchestrator code path that calls
  docker-socket-proxy, any reachability-check wrapper around orchestrator's outbound HTTP calls
  (to sim-clock, meeting-simulator, accounting-engine, kpi-engine, external-world, mattermost,
  zammad, wikijs, akaunting), and any control-API endpoint for start/stop/restart.

### 3. Implementation plan

No new microservice — this is orchestrator-only work, matching the `PLAN_REMAINING_PHASES.md`
precedent of folding scheduler-adjacent features into `orchestrator/main.py` rather than spinning
up new services for things the orchestrator already owns (§24 explicitly assigns it "reachability
checks + idempotent `pending_actions` retry queue").

1. **Migration** `narrative-db/migrations/009_phase27_pending_actions.sql`:
   - `pending_actions` table: `id`, `action_type` (text — e.g. `orchestrator_call`,
     `mattermost_post`, `zammad_ticket`, etc.), `target_service` (text), `payload` (jsonb),
     `idempotency_key` (text, unique — required per spec §23 "Idempotency keys on anything that
     posts money, checked before the outage-retry queue can ever double-post"), `status`
     (`pending`/`retrying`/`done`/`failed`), `attempts` (int), `next_retry_at` (timestamptz —
     wall-clock, not sim-time, per §13.1's explicit "wall-clock-based retry" instruction),
     `created_at`, `last_error` (text, nullable).
   - `service_outage_log` table (or reuse `narrative_events` with a typed `event_type = 'outage'`
     — simpler, avoids a new table; recommend reusing `narrative_events` since the spec doesn't
     ask for a dedicated outage table, only that outages get logged as `narrative_event`s).
2. **`orchestrator/main.py` additions:**
   - `SocketProxyClient` httpx wrapper (`http://docker-socket-proxy:2375`), matching the
     `AkauntingClient`-style pattern already used elsewhere in this repo (base client class with
     required headers). Exposes `start(container_name)`, `stop(container_name)`,
     `restart(container_name)` — nothing else, matching the proxy's own lockdown.
   - Reachability wrapper: before every outbound call the tick loop already makes (to sim-clock,
     meeting-simulator, accounting-engine, kpi-engine, external-world, and the appliance APIs),
     wrap in a `try/except httpx.ConnectError`-style check; on failure, insert/update a
     `pending_actions` row (upsert on `idempotency_key`) instead of raising, and continue the tick
     rather than crash-looping (this satisfies §23's "never a silent crash-loop").
   - A new scheduled job `process_pending_actions()` in the tick loop: for every `pending_actions`
     row where `next_retry_at <= now()` (wall-clock `now()`, not `sim_time`), retry the original
     call; on success mark `done` and write the deferred `narrative_event` (phrased using the
     *sim_time at retry success*, per §13.1's "logged... in sim-time terms" — read current
     `sim_time` from sim-clock at retry time, not the original failure time, since that's the true
     narrative-relevant moment).
   - Control-API endpoints on the existing FastAPI app: `POST /chaos/appliances/{name}/stop`,
     `/start`, `/restart` — validate `{name}` against an explicit allow-list of labeled container
     names (read from `docker-socket-proxy`'s `CONTAINERS` label filter or a static config list of
     `fakeco-*` service names) before calling `SocketProxyClient`; anything not on the list 400s.
     This satisfies the "disallowed socket-proxy call is rejected" exit criterion at the
     application layer (the proxy itself already blocks non-CONTAINERS/POST verbs at the
     transport layer).
3. **`docker-compose.yml` wiring:** orchestrator needs a new network membership (`net_mgmt`, to
   reach `docker-socket-proxy`) added to its existing `networks:` list (currently `net_clients`,
   `net_data`, `net_office`, `net_mail`) and a new env var `DOCKER_SOCKET_PROXY_URL:
   "http://docker-socket-proxy:2375"`. No new `profiles:` entry needed beyond what orchestrator
   already has (`phase18`) — optionally add `phase27` to orchestrator's profile list if the user
   wants to gate this feature separately from base Phase 18, but since it's additive code in an
   existing container, a separate profile buys little; recommend just adding to the existing
   `phase18` profile and noting the phase-27 feature in the container's label comment block (same
   pattern already used for Phase 19's PTO additions living inside the Phase 18 orchestrator
   container — see `docker-compose.yml:1460-1464`).

### 4. Dependencies/ordering

- **Genuinely blocks nothing outside itself**, but its own stated dependency (Phase 18's retry
  queue) does not yet exist in this repo despite the spec assuming it does — Phase 27 must build
  it as part of its own scope (see §2).
- **Phase 27 blocks Phase 28**: Phase 28's crisis events reuse "the same continuity machinery as
  any other meeting" and route crisis-associated expenses through the normal approval flow — no
  hard technical dependency on Phase 27's specific code, but both phases touch orchestrator's core
  loop and outage/retry semantics are a natural shared foundation (a crisis triggered while an
  appliance is down should behave the same way an ordinary action does mid-outage). Build 27 first
  to avoid two competing partial implementations of "what happens when something's down."
  Practically: only a soft/ordering dependency, not a hard blocker.
- **Phase 31 depends on nothing from 27/28** (see Phase 31 section) but Phase 27's outage-retry
  work naturally feeds Phase 31's "narrative backlog" Grafana panel (a growing `pending_actions`
  queue is exactly the kind of backlog metric Phase 31 wants to chart) — sequence 27 before 31 so
  there's real data to chart, though not a hard build blocker either.

### 5. Verification plan

- `docker exec fakeco-postgres psql ... -c "insert pending row manually"` then confirm the next
  tick processes it.
- Live test per `PHASES.md` exit criteria: `docker stop fakeco-mattermost` mid-orchestrator-tick
  (or call the new `/chaos/appliances/mattermost/stop` endpoint), confirm the in-flight action
  lands in `pending_actions` rather than an unhandled exception in orchestrator logs, `docker
  start`/`POST .../start` it back, confirm the queued action retries and succeeds within one tick
  interval, and confirm exactly one `narrative_event` gets written phrased in sim-time terms
  (query `narrative_events` and eyeball the text for "at Tuesday 2pm" style phrasing, not
  wall-clock timestamps).
- Call `/chaos/appliances/postgres/stop` (not on the allow-list, or deliberately excluded since
  stopping the core DB would break everything) and confirm a 400, not a proxied call.
- Confirm `docker logs fakeco-orchestrator` shows no crash-loop (restart count stays 0) across the
  whole test.

### 6. Risks/open questions

- **Idempotency key design**: since `pending_actions` will hold arbitrary heterogeneous actions
  (Mattermost posts, Zammad tickets, Akaunting postings via other services), the idempotency-key
  scheme needs to be action-type-aware (e.g. hash of `action_type + target_service + payload`) to
  avoid the "double-post money" failure mode §23 explicitly warns about. Recommend user confirm
  whether *all* pending-action types need idempotency keys or only money-touching ones (lower
  overhead, but §23 doesn't scope it down that way in the raw spec text) — low-risk either way,
  worth a one-line sign-off before implementation, not a blocking risk.
- No destructive/data-loss risk (unlike Phase 29) — starting/stopping containers is easily
  reversible and the whole point of this phase.

---

## Phase 28 — Chaos: crisis events

### 1. What it is

Spec §13.2 (`fakeco-real-appliances-BUILD-PROMPT.md:386-398`): a "Trigger Event" control (a
dropdown of canned scenarios — data breach, surprise audit, viral public-site complaint,
extensible via config — plus a free-text field for a custom scenario). Triggering one opens a
high-priority `narrative_thread` (type `crisis`), immediately schedules a `crisis_response`
meeting (§6) with a forced relevant attendee list, and seeds downstream `action_items` — the same
continuity machinery as any other meeting, just invoked on demand. "Surprise audit" specifically
must invoke the *real* Books Auditor (§10.4) and narrate its actual findings rather than
fabricating a result. Crises may carry a real cost, routed through the normal approval flow
(§10.2) like any other expense. `PHASES.md:601-616` exit criteria: real Books Auditor invocation
for the audit preset, a free-text custom scenario producing a real `crisis` thread +
`crisis_response` meeting + forced attendees + seeded action items, and crisis-associated expenses
going through the normal (not special-cased) approval path.

### 2. What already exists vs. what's missing

- **Exists and directly reusable:**
  - `accounting-engine/main.py:664-737` already implements `run_books_audit()` — a real
    reconciliation/correction function, callable via the existing `/audit` endpoint
    (`accounting-engine/main.py:869-872`, `run_audit_endpoint`). Phase 28's "surprise audit" preset
    is a thin caller of this exact existing endpoint — no new audit logic needed.
  - `meeting-simulator/main.py` already recognizes `crisis_response` as a valid `meeting_type`
    (seen in the file's header comment at line 10: "crisis_response — triggered by unresolved
    narrative thread (§6.5)", and referenced again at lines 265-295 in `select_attendees()`'s
    branch logic, and line 473 in the outcome-schema prompt: `crisis_response:
    {resolution: string, responsible_employee: string}`). This means the meeting *type* is already
    wired into meeting-simulator's attendee-selection and outcome-schema logic — Phase 28's job is
    to build the *trigger* (something that calls meeting-simulator with `meeting_type:
    "crisis_response"` on demand), not the meeting-type handling itself.
  - `accounting-engine`'s existing `pending_approvals`/expense-approval flow (Phase 15,
    §10.2) is the reuse target for "crisis-associated expense routes through the normal approval
    flow, not a special path" — no new approval logic needed, just call the existing expense-create
    endpoint with a crisis-tagged narrative reference.
  - `narrative_threads`/`narrative_events`/`action_items` tables all exist (Phase 13).
- **Missing:** any Trigger-Event control API (dashboard UI is Phase 36's job per
  `PHASES.md:761-775`, but the *backend* control-API endpoint is Phase 28's job, matching Phase
  27's own "dashboard toggle backend, UI comes later" split), any canned-scenario config
  (data breach / surprise audit / viral complaint), any code path that opens a `crisis`-typed
  `narrative_thread` and forces a specific attendee list into `meeting-simulator`'s existing
  `select_attendees()` `crisis_response` branch (need to check whether that branch currently
  accepts an externally-forced attendee list or only derives attendees internally — likely needs a
  small `meeting-simulator` extension to accept an optional explicit attendee override, since
  right now the branch appears to derive "all active leads + any employees named in the crisis
  thread" itself, per `PLAN_REMAINING_PHASES.md:226`; a free-text custom scenario has no employees
  "named in the thread" yet at trigger time unless the trigger code seeds that first).

### 3. Implementation plan

No new microservice needed either — recommend hosting this as new orchestrator endpoints
(consistent with Phase 27 and with `PLAN_REMAINING_PHASES.md`'s stated preference for folding
scheduler/control-adjacent features into orchestrator rather than new services), calling out to
the already-existing `accounting-engine` (`/audit`, expense endpoints) and `meeting-simulator`
(`/meetings/run` or equivalent existing endpoint) services.

1. **Config**: a small static config (env var JSON or a new `crisis_scenarios.yaml` mounted into
   orchestrator) defining the canned presets: `{key: "data_breach", label: "Data Breach",
   forced_attendees: [...], seed_action_items: [...], cost_estimate: ...}`, `{key:
   "surprise_audit", ..., invokes_audit: true}`, `{key: "viral_complaint", ...}`. Extensible by
   editing this config file, per the spec's "extensible via config" wording.
2. **`orchestrator/main.py` additions:**
   - `POST /chaos/trigger-event` endpoint accepting `{scenario: "data_breach"|"surprise_audit"|
     "viral_complaint"|"custom", custom_text: Optional[str]}`.
   - Handler: creates a `narrative_thread` row with `thread_type = 'crisis'` and high priority
     flag/field (check `narrative_threads` schema for an existing priority column from Phase 13;
     if none exists, this phase needs a small additive migration adding a `priority` or
     `is_crisis` column — flag as an open question, see §6).
   - If `scenario == "surprise_audit"`: call `accounting-engine`'s existing `/audit` endpoint
     directly, capture its real return value (corrections made, amounts), and pass that real
     result into the crisis thread's seed content — never fabricate a result, per the spec's
     explicit "narrate its real findings, not a fabricated result."
   - Call `meeting-simulator` to schedule a `crisis_response` meeting, passing the forced attendee
     list from config (or, for `custom`, a sensible default forced list — e.g. all department
     leads) plus the crisis thread's ID/text as context. This is where meeting-simulator's
     `select_attendees()` may need a small extension to accept/prefer an externally-supplied
     attendee list over its own derivation — flag as a scoped one-function change to
     `meeting-simulator/main.py`, not a new service.
   - Seed `action_items` rows from the meeting's structured outcome (reuses the same
     outcome-to-action-item pipeline Phase 16's meeting-simulator already has for every other
     meeting type — no new code path, just triggering it with `crisis_response` as the type).
   - If the scenario config specifies `cost_estimate`, POST a normal expense request to
     accounting-engine's existing `pending_approvals`-creating endpoint (Phase 15), tagged with a
     reference to the crisis thread ID — explicitly *not* a bypass path, satisfying the "same
     normal approval flow" requirement.
3. **Migration** (if needed): `narrative-db/migrations/010_phase28_crisis.sql` — only if
   `narrative_threads` lacks a priority/urgency column; add `priority` (smallint or enum) with a
   default, and backfill existing rows to normal priority.
4. **`docker-compose.yml` wiring:** no new service; orchestrator gets a new
   `CRISIS_SCENARIOS_CONFIG_PATH` env var and a bind-mount of the new config file (or bake it into
   the image at build time, simpler — recommend baking it in since these are fixed canned
   scenarios, with the free-text path handling genuine runtime customization).

### 4. Dependencies/ordering

- **Depends on Phase 27 only loosely** (shared "what happens when things are in a degraded state"
  philosophy, not a hard code dependency) — Phase 28 does not require Phase 27's retry queue to
  function, since a crisis-trigger call is itself just a normal orchestrator action that would
  naturally flow through whatever reachability/retry mechanism Phase 27 builds, once built. Order
  27 before 28 anyway so crisis-triggered actions inherit the retry behavior rather than needing a
  second implementation.
- **Does not depend on Phase 31 or 32.**
- **Blocks Phase 36** (`PHASES.md:761-775`, Chaos dashboard tab) — Phase 36 explicitly lists
  "Phase 27, 28 (chaos)" as its dependency.

### 5. Verification plan

- Call `POST /chaos/trigger-event {"scenario": "surprise_audit"}`; independently call
  `accounting-engine`'s `/audit` endpoint directly beforehand/afterward and confirm the crisis
  thread's narrated content matches the audit's real corrections (not an LLM-invented figure).
- Call with `{"scenario": "custom", "custom_text": "a rogue vending machine is charging double"}`;
  confirm a `crisis` thread appears, a `crisis_response` meeting row appears in the meetings table
  with the expected forced attendee list, and at least one `action_items` row is seeded from its
  outcome.
- Trigger a scenario with a nonzero `cost_estimate`; confirm the resulting expense appears in
  accounting-engine's normal `pending_approvals` queue (same table/endpoint as any other expense),
  not a separate crisis-only table.
- Confirm neither the crisis thread nor its meeting bypasses existing HR-privacy-style exclusions
  if applicable (not directly required by spec, but worth a sanity check against Phase 24's
  privacy-exclusion precedent for `pay_negotiation`/`performance_review`).

### 6. Risks/open questions

- **`narrative_threads` schema gap**: needs confirmation whether a priority/urgency column already
  exists (quick to check against `002_narrative_core.sql` before implementation) — low-risk, just
  needs a look before writing the migration to avoid duplicating a column.
- **`meeting-simulator`'s attendee-override**: confirm whether forcing an attendee list from
  outside is a clean extension point or requires restructuring `select_attendees()`'s
  `crisis_response` branch — worth 15 minutes of code reading before implementation, not a
  fundamental blocker.
- No destructive/data-loss risk — crisis events are additive narrative content plus a normal
  approval-flow expense, fully reversible via Phase 29's scoped purge if ever needed.

---

## Phase 31 — Observability completion, pass 2

### 1. What it is

Spec §21 (`fakeco-real-appliances-BUILD-PROMPT.md:554-565`) and `PHASES.md:666-679`: Grafana
panels for LLM token spend/cost (speed-annotated), narrative backlog, headcount by status,
sim-time vs wall-clock, cash balance/burn rate/runway/payroll total from Akaunting, KPI trends, and
customer pipeline/revenue. Explicitly "no new services, dashboards only" (`PHASES.md:679`) — this
is the smallest of the four phases in scope. Exit criteria: panels exist for each named metric,
and each is spot-checked against its real source (cash balance vs Akaunting, KPI trend vs
`kpi_snapshots`, LLM spend vs LiteLLM's own usage tracking).

**Correction to the user's rough guess**: the task prompt's framing called this "maybe Grafana
dashboard additions, alerting" — the actual spec (§21) does not mention alerting at all, only
dashboards. No alerting scope should be added here unless the user explicitly wants it beyond
spec.

### 2. What already exists vs. what's missing

- **Exists:** `monitoring/grafana/dashboards/container-health.json` and
  `traffic-and-activity.json` (Phase 2/11 base dashboards, per `monitoring/README.md:3`),
  `monitoring/grafana/provisioning/{dashboards,datasources}/` (auto-provisioning config already
  wired — new dashboard JSON files just need to be dropped into `dashboards/` to auto-load, no
  compose changes needed). `monitoring/README.md:21` already has a stub note: "Phase 31 —
  Observability completion, pass 2 (needs real data to exist first)" confirming this repo already
  anticipated this phase and deferred it correctly.
  Prometheus (`docker-compose.yml:298-...`) already scrapes cAdvisor/node-exporter; per spec §21
  it should also scrape LiteLLM's `/metrics` and "app-level endpoints" — need to check
  `monitoring/prometheus.yml`'s current scrape-target list for whether custom services (kpi-engine,
  accounting-engine, orchestrator, etc.) already expose Prometheus-format `/metrics`, or only the
  JSON `/health` this repo's healthchecks use.
  `kpi_snapshots` (Phase 23), Akaunting (Phase 9, live), LiteLLM's own cost/usage tracking config
  (`litellm/config.yaml:130`, "Store usage data for cost tracking (§19.5, §20)" — already
  configured to track spend) all exist as real data sources to point new panels at.
- **Missing:** the actual new dashboard JSON files (narrative backlog, headcount-by-status,
  sim-time-vs-wall-clock, cash-balance/burn/runway/payroll, KPI trends, customer
  pipeline/revenue, LLM spend/cost) — none of these exist yet, only the two base dashboards.
  Also need to confirm whether any custom services currently expose a Prometheus `/metrics`
  endpoint at all (likely not — the existing pattern across this repo's custom services is a
  plain FastAPI `/health` returning JSON, not `prometheus_client`-instrumented `/metrics`). If not,
  this phase needs either (a) Grafana panels backed by direct Postgres queries via Grafana's
  Postgres datasource (simplest — no new instrumentation, just SQL panels against `kpi_snapshots`,
  `pending_actions`/`action_items` counts, `employees` status counts, `sim_clock` table, and
  Akaunting's own MySQL DB), or (b) adding `prometheus_client` instrumentation to every custom
  service (heavier, not required by spec since §21 doesn't mandate a specific data-source
  mechanism, just that the panels exist and are accurate).

### 3. Implementation plan

**No new microservice, no compose changes beyond possibly a new Grafana datasource.**

1. **Confirm Grafana already has a Postgres datasource** pointed at the shared `fakeco` Postgres
   instance (check `monitoring/grafana/provisioning/datasources/datasources.yml`); if not, add one
   — this is the only likely compose/config-adjacent change, and it's a Grafana provisioning YAML
   edit, not a `docker-compose.yml` service change.
2. **New dashboard JSON files** in `monitoring/grafana/dashboards/`, each a direct SQL panel
   (Grafana's native Postgres datasource, no new service needed) or a Prometheus panel where a
   metric already exists via cAdvisor/node-exporter (container health only):
   - `sim-time-vs-wallclock.json` — query `sim_clock` table's `sim_time`, `last_wall_checkpoint`,
     `speed_multiplier` directly; plot sim_time progression vs real elapsed time.
   - `headcount-by-status.json` — `SELECT status, count(*) FROM employees GROUP BY status`
     (active/vacant/terminated/resigned).
   - `narrative-backlog.json` — counts of open `narrative_threads`, open `action_items`, pending
     `pending_reactions`/`pending_approvals`, and (once Phase 27 lands) `pending_actions` queue
     depth — this panel genuinely benefits from Phase 27 existing first (see dependencies).
   - `financials.json` — cash balance/burn rate/runway/payroll total: either a direct query
     against Akaunting's own MySQL DB (Grafana MySQL datasource, read-only credentials) or, more
     safely given `important.md`'s warning about the Akaunting dual-header/TrustHosts quirks being
     an *API* issue, not a DB issue — reading Akaunting's DB tables directly via SQL avoids the
     whole API-header problem entirely and is simpler for pure reporting. Recommend this route.
   - `kpi-trends.json` — direct query against `kpi_snapshots` (Phase 23, already populated).
   - `customer-pipeline-revenue.json` — direct query against `customers` (Phase 22) joined with
     Akaunting revenue transactions (same DB-read approach as financials).
   - `llm-spend.json` — LiteLLM stores its own usage/cost data (per `litellm/config.yaml:130`) in
     its own Postgres/DB table (check LiteLLM's configured backing store — likely the shared
     Postgres instance under a separate schema/DB, per `BUILD_LOG.md`'s note that "LiteLLM's own
     spend-history DB shares the instance under a different DB name"); query that directly, and
     annotate with `speed_multiplier` from `sim_clock` for the "speed-annotated" requirement.
3. **`prometheus.yml`**: only touch if any custom service actually needs a scrape target added —
   likely unnecessary if going the direct-Postgres-panel route above; if the user wants live
   custom-service metrics (e.g. request latency) beyond what's asked in §21, that's out of scope
   for this phase.
4. **No `docker-compose.yml` service changes** — Grafana dashboard JSON files auto-load via the
   existing provisioning volume mount; only a possible datasource-YAML addition.

### 4. Dependencies/ordering

- **Depends on**: Phase 11 (base Grafana/Prometheus, done), Phase 15 (accounting, done), Phase 23
  (KPI engine, done), Phase 10 (LiteLLM, done) — all satisfied already per `PHASES.md:669`.
- **Benefits from (soft, not hard) Phase 27**: the "narrative backlog" panel is more meaningful
  once `pending_actions` (Phase 27) exists to chart; build 31 after 27 for a more complete panel,
  though 31 can technically ship without it (backlog panel just omits that one queue-depth metric
  until 27 lands).
- **Does not depend on Phase 28 or 32.**
- **Blocks nothing directly** but Phase 33 (`PHASES.md:707-720`) lists Phase 31 as a dependency
  for its "LLM status tab" (usage/cost, speed-adjusted burn rate) — Phase 31's LLM-spend panel and
  underlying query logic is the reusable groundwork for that dashboard tab's data source.

### 5. Verification plan

- For each new panel, run the equivalent raw SQL query directly against Postgres/Akaunting's DB/
  LiteLLM's usage table via `psql`/`mysql` CLI and confirm the number matches what Grafana renders
  — this is exactly the spot-check method `PHASES.md:676-678` specifies.
- Change `speed_multiplier` via sim-clock's existing API, confirm the sim-time-vs-wall-clock panel
  reflects the new slope within one refresh interval.
- Fire/hire a test employee (existing provisioning tooling), confirm headcount-by-status panel
  updates.

### 6. Risks/open questions

- **Read-only DB credentials for Grafana's cross-appliance datasources** — Akaunting's MySQL and
  LiteLLM's Postgres schema both need a real (ideally read-only) credential exposed to Grafana;
  confirm with the user whether a new read-only DB role should be created (best practice, mild
  extra work) or whether reusing existing admin credentials already in `.env` is acceptable for
  this stage of the simulation (lower effort, matches this repo's generally pragmatic posture on
  internal-only credentials). Low risk either way — not destructive, purely a read path.
- No data-loss/destructive risk at all — this phase is strictly additive/read-only.

---

## Phase 32 — Simulation speed slider, full integration (DEFERRED — see Future_Plans.md)

**Not being built in this pass.** Full design content has been moved to `Future_Plans.md` at
the repo root, verbatim, so it isn't lost. Skip straight to "Recommended build order" below.

<!-- Original section retained below for reference only; canonical copy now lives in Future_Plans.md -->

### 1. What it is

Spec §19.2-19.5 (`fakeco-real-appliances-BUILD-PROMPT.md:490-526`) and `PHASES.md:683-700`: the
`set_speed` API must expose the full continuous 0.1x-10x range with labeled presets
(0.1/0.25/0.5/1/2/5/10x), applying immediately. At any speed, `sim_time` must advance at exactly
that multiple of wall-clock (verified via a measured interval), while the underlying *behavioral
rates* (filler frequency per sim-hour, per §19.3's per-employee/per-sim-workday targets) stay
calibrated to their 1x targets — i.e., compression must not also inflate the rate. Business-hours
gating (full weight Mon-Fri 9am-6pm sim-time, 5-10% trickle otherwise, §19.4) must be observable
across a simulated day/night cycle. A recurring "LLM burn" expense line must reconcile into
Akaunting at a rate matching the dashboard's estimated $/wall-clock-hour figure (§19.5).

**Correction to the user's rough guess**: `docker-compose.yml:1106` shows `SPEED_MULTIPLIER` is
currently a static env var (`"${SPEED_MULTIPLIER:-1.0}"`) baked in at container start, not a live
mutable value — so "full integration" genuinely means building the actual runtime `set_speed` API
and propagating it, not just wiring up something that mostly already works. This matches the
user's own framing reasonably well.

### 2. What already exists vs. what's missing

- **Exists:** `sim-clock/main.py` (Phase 12) already implements the `sim_time += wall_elapsed *
  speed_multiplier` ticker per §19.1, reading `SPEED_MULTIPLIER` from its env var at startup
  (`docker-compose.yml:1103-1106`). It has a `/health` endpoint and is the authoritative sim-time
  source every other service (`SIM_CLOCK_URL`) already reads from — orchestrator, external-world,
  and others all reference `sim_clock`'s current time.
- **Missing:**
  - A live `PUT/POST /speed` (or similar) endpoint on `sim-clock` that changes
    `speed_multiplier` in the `sim_clock` table at runtime rather than only reading a static env
    var at boot — need to read `sim-clock/main.py` in full to confirm whether the ticker already
    re-reads the DB row's `speed_multiplier` on every tick (likely yes, since it's a DB-backed
    ticker per §19.1's schema) or only reads the env var once at startup and never revisits it.
    **This is the crux of "full integration" and needs direct code confirmation before
    implementation** — if the ticker already re-reads from the DB each tick, the missing piece is
    purely the HTTP endpoint to update that DB row (small); if it's cached at startup, the ticker
    loop itself needs a fix too (slightly larger, but still small).
  - Any behavioral-rate calibration logic anywhere — nothing in orchestrator, meeting-simulator,
    human-bridge, or external-world currently reads `speed_multiplier` to adjust its own
    per-sim-hour generation cadence independent of tick frequency. Currently, if these services
    run on a fixed wall-clock tick interval (e.g. orchestrator's `ORCHESTRATOR_TICK_INTERVAL:
    "60"` seconds), simply speeding up sim-time without also adjusting per-tick generation logic
    risks exactly the "compression also inflates the rate" failure mode §19.2 explicitly forbids
    — needs a design decision on whether cadence checks compare "wall-clock time since last
    filler" or "sim-time since last filler" (spec implies rates should be sim-hour-relative, not
    wall-clock-tick-relative, so the correct fix is ensuring every per-employee/per-workday rate
    check already reads `sim_time` deltas, not wall-clock-tick counts — likely already partially
    true since orchestrator reads sim-clock for scheduling, but needs an explicit audit).
  - Business-hours gating: no evidence yet of a 9am-6pm Mon-Fri sim-time check gating generation
    rate anywhere in orchestrator/meeting-simulator/human-bridge — needs to be added or, if
    partially present, extended to the full 5-10% nights/weekends trickle behavior.
  - The recurring "LLM burn" Akaunting expense line: no evidence this exists — needs a new
    scheduled job (natural home: orchestrator's tick loop, alongside its other scheduled jobs)
    that reads LiteLLM's live usage/cost data (same source Phase 31's LLM-spend panel reads),
    computes a $/wall-clock-hour rate, and posts a recurring expense transaction to
    `accounting-engine` at whatever cadence makes sense (e.g. hourly), scaled to reflect the
    actual measured cost, not a static assumption.

### 3. Implementation plan

No new microservice — extends `sim-clock` (new endpoint) and `orchestrator` (new scheduled job +
audit of existing cadence logic), matching this repo's established pattern of growing existing
core services rather than fragmenting into new ones for control-plane features.

1. **`sim-clock/main.py`**: add `POST /speed {"speed_multiplier": float}` — validate range
   0.1-10.0, update the `sim_clock.speed_multiplier` DB column, return the new value immediately
   (satisfying "changes apply immediately"). If the ticker loop doesn't already re-read this value
   per tick, fix that too (read fresh from DB each tick rather than caching at startup).
   Add `GET /speed/presets` returning the labeled preset list (0.1/0.25/0.5/1/2/5/10x) as a small
   static config, purely for the eventual Phase 33 dashboard slider to consume.
2. **Cadence audit across orchestrator/meeting-simulator/human-bridge/external-world**: confirm
   every "should I generate routine content now" check compares against `sim_time` deltas (e.g.
   "has N sim-hours passed since last filler for this employee") rather than wall-clock tick
   counts. Where a check is currently tick-count-based (e.g. "every Nth orchestrator tick"),
   convert it to a sim-time-window check instead, reading `sim_clock`'s current `sim_time` each
   time. This is the mechanism that keeps §19.3's calibrated rates (15 emails/employee/sim-workday
   etc.) accurate regardless of speed.
3. **Business-hours gating**: a small shared helper (e.g. in orchestrator, or a tiny shared
   module if multiple services need it — check whether meeting-simulator/human-bridge also
   generate filler independently of orchestrator's tick, which would mean the helper needs to live
   somewhere importable by all of them, or simplest: each service computes its own business-hours
   weight via a small inlined function reading `sim_time`'s weekday/hour). Given this repo's
   existing pattern of independent services each owning their own logic (no shared library
   currently exists across these Python services), recommend duplicating a small
   `business_hours_weight(sim_time) -> float` function per service rather than introducing a new
   shared package — lowest-risk, consistent with current repo conventions, at the minor cost of
   duplicated logic in 2-3 files.
4. **LLM-burn recurring expense**: new orchestrator scheduled job (e.g.
   `LLM_BURN_POST_INTERVAL_DAYS` or hourly-in-sim-time cadence), queries LiteLLM's usage data
   (same source as Phase 31's panel), computes actual $ spent since last posting, calls
   accounting-engine's existing expense-posting endpoint (Phase 15) with a clearly-labeled "LLM API
   costs" line item — this reuses the accounting-engine's already-atomic transaction posting
   (§23) rather than writing new financial-mutation code.
5. **`docker-compose.yml` wiring:** no new services. Possibly remove the static
   `SPEED_MULTIPLIER` env var from `sim-clock`'s definition (or keep it only as the *initial*
   seed value on first migration, which is arguably its correct remaining role) once the live
   `/speed` endpoint exists — flag as a design choice for the user rather than assuming: keep
   `SPEED_MULTIPLIER` as the bootstrap default, live changes happen via the API and persist in the
   DB from then on.

### 4. Dependencies/ordering

- **Depends on**: Phase 12 (sim clock, done), Phase 18 (business-hours gating already partially
  affects filler generation per `PHASES.md:687`, done), Phase 15 (Akaunting expense posting,
  done), Phase 10/31 (LLM cost data) — **this is a real hard dependency on Phase 31**, since Phase
  32's LLM-burn reconciliation needs the same LiteLLM-usage-reading logic Phase 31 builds for its
  spend panel. `PHASES.md:687` lists this dependency explicitly ("Phase 10/31 (LLM cost data)").
  **Build Phase 31 before Phase 32.**
- **Does not depend on Phase 27 or 28** directly, though the cadence-audit work (§3.2 above)
  touches the same orchestrator tick loop that Phase 27's reachability wrapper touches — sequence
  32 after 27 to avoid two people (or two passes) editing the same tick-loop code concurrently and
  conflicting, even though there's no logical dependency.
- **Blocks Phase 33** (`PHASES.md:707-720`) — the dashboard's "start/stop, worker scale, and speed
  slider controls" explicitly need Phase 32's real `set_speed` API to wire against.

### 5. Verification plan

- Call the new `/speed` endpoint with `2.0`; measure `sim_time` advancement over a fixed 60-second
  wall-clock window via repeated `GET /sim-clock` polls; confirm it advanced ~120 simulated
  minutes (2x), not 60.
- With speed at e.g. 5x, measure the actual count of emails/chat messages/tickets generated over a
  fixed *sim-time* window (e.g. one simulated workday) and confirm it lands near the §19.3
  calibrated targets (~15 emails/employee/workday etc.) — this is the test that actually catches
  the "compression inflates rate" bug if the cadence-audit in §3.2 was done incorrectly.
  Contrast against the same test at 1x to confirm the *rate per sim-hour* is stable across both
  speeds even though wall-clock time to reach that sim-hour differs.
- Advance sim-time across a simulated Saturday; confirm generation volume drops to the 5-10%
  trickle band relative to the prior Tuesday's volume.
- Let the LLM-burn job run for a few cycles; query Akaunting directly for the posted "LLM API
  costs" line items and cross-check the amount against LiteLLM's own usage/cost table for the same
  window — same spot-check methodology as Phase 31.

### 6. Risks/open questions

- **Real risk, needs sign-off**: the cadence-audit step (§3.2) touches shared, already-verified
  code in orchestrator/meeting-simulator/human-bridge/external-world that's currently
  runtime-verified per `BUILD_LOG.md`. Any refactor from tick-count-based to sim-time-window-based
  checks carries real regression risk to already-working Phase 12-22 behavior. Recommend doing
  this work behind careful before/after testing against the existing 1x baseline (confirm nothing
  changes at 1x) before testing at other speeds, and flag to the user that this phase touches more
  already-verified surface area than any of the other three phases in this batch (27/28/31 are
  each mostly additive/new-endpoint work; 32's cadence-audit is the one genuinely invasive piece).
- **Design choice needing a decision, not just a risk**: whether `SPEED_MULTIPLIER` env var
  becomes a first-boot-only default or is removed entirely in favor of always-DB-backed state —
  low-risk either way but worth a one-line confirmation before implementation.
- No destructive/data-loss risk.

---

## Recommended build order across these four phases

**31 → 27 → 28 → 32**

Reasoning:

1. **Phase 31 first.** Pure dashboards-only, zero new endpoints, zero risk to existing verified
   code, and it is Phase 32's genuine hard dependency (`PHASES.md:687` lists "Phase 10/31 (LLM cost
   data)" as a Phase 32 dependency) — building it first means Phase 32's LLM-burn reconciliation
   has real, already-tested spend-reading logic to reuse rather than building it twice.
2. **Phase 27 next.** Builds the `pending_actions` retry queue and reachability wrapper that
   Phase 18's spec assumed already existed but doesn't (a real gap uncovered during this planning
   pass, see Phase 27 §2) — this is genuinely foundational reliability infrastructure that Phase
   28's crisis-triggered actions and Phase 32's speed changes should both be able to lean on if an
   appliance happens to be down mid-action. Also directly improves Phase 31's own "narrative
   backlog" panel once it exists, though 31 was already sequenced first for the harder Phase 32
   dependency reason.
3. **Phase 28 next.** Almost entirely additive/reuse (real Books Auditor, real meeting-simulator
   crisis_response type, real approval flow) with low regression risk; naturally follows Phase 27
   since both touch orchestrator's action/outage semantics and building 28 after 27 avoids two
   separate partial "what happens when things are degraded" implementations.
4. **Phase 32 last.** Depends on Phase 31 (hard) and touches the largest amount of already-verified
   code (the cadence audit across four services) — the highest-regression-risk phase of the four,
   so it benefits most from having the other three's more isolated changes already stable and
   tested first, minimizing the number of moving parts changing at once when doing Phase 32's
   riskier refactor.
