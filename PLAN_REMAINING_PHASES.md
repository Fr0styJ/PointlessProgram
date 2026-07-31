# Expanded implementation plan — Phases 19, 20, 23, 29, 30, 33-38

Planning only — no code written. Grounded in `PHASES.md` (exit criteria) and
`fakeco-real-appliances-BUILD-PROMPT.md` (spec sections). Cross-checked against the actual
current repo state as of 2026-07-31: `pto_calendar`, `employee_relationships`, and
`kpi_snapshots` tables **already exist** (migration `004_additive_schemas.sql`), so schema work
for Phases 19/20/23 is done — these are pure service-building phases now. `dashboard/`,
`kpi-engine/`, `purge-manager/`, `snapshot-manager/`, `branding-manager/` are all still bare
`README.md` stubs — nothing built yet.

Real credentials/tokens needed for these phases already live in `.env`: `MATTERMOST_ADMIN_TOKEN`,
`ZAMMAD_ADMIN_TOKEN`, `WIKIJS_ADMIN_TOKEN`, `MAILSERVER_BOT_SECRET`, `PRINCIPAL_EMAIL`. No new
appliance accounts should be needed for 19/20/23; 29/30/33-38 will need the Principal's Zammad/
Wiki.js/Mattermost accounts (already provisioned in Phase 14).

---

## Phase 19 — PTO

**Depends on:** 4 (mail/Sieve), 5 (Mattermost status API), 14 (roster), 15 (accounting-engine
approval routing), 18 (orchestrator continuity loop) — all already verified working this session.

**What to build:** a scheduler + two real-appliance integrations, most naturally as new endpoints
on the existing `orchestrator` service (it already owns scheduled-job hosting) rather than a new
microservice — the spec doesn't call for a dedicated PTO service, and Phase 24's spec explicitly
folds "approval delegation" into the existing accounting-engine approval path.

1. **Scheduler.** A new `maybe_schedule_pto()` job in `orchestrator/main.py`'s tick loop
   (alongside the existing `maybe_run_standups` etc. pattern). Deterministic per-employee
   probability check against `sim_time`, spaced so nobody's out constantly (config: min gap
   between an employee's PTO windows, e.g. `PTO_MIN_GAP_DAYS`). Inserts a row into
   `pto_calendar` (table already exists).
2. **PTO-start hook — real Sieve vacation responder.** docker-mailserver supports Sieve natively
   (`ENABLE_MANAGESIEVE: 1` is already set in `docker-compose.yml`'s mailserver env from Phase 4).
   Need a small client (ManageSieve protocol, port 4190, or filing a `.sieve` script directly via
   `doctl`/docker exec similar to `provisioning`'s `setup email` pattern) that installs a real
   vacation-responder script on PTO start and removes it on PTO end. Research needed: does
   docker-mailserver's `setup` CLI have a direct Sieve subcommand, or does this need a raw
   ManageSieve client / direct file write to the mailbox's sieve directory?
3. **PTO-start hook — real Mattermost custom status.** `PUT /api/v4/users/{id}/status/custom`
   (or the equivalent v4 endpoint) — straightforward, same admin-impersonation-token pattern
   `human-bridge`'s `post_mattermost_as_employee` already established (create ephemeral PAT, act
   as the employee-bot, revoke). Set emoji + "Out of Office" text + expiry timestamp.
4. **Continuity-loop skip + "catching up" burst.** Extend `orchestrator`'s existing per-employee
   filler/routine-work checks (wherever standups/action-item assignment currently iterate active
   employees) to exclude anyone with an active `pto_calendar` row. On the tick where an employee's
   PTO window just ended, fire one extra burst of routine activity for them specifically.
5. **Approval delegation.** Extend `accounting-engine`'s existing `pending_approvals` routing
   logic (Phase 15, already verified) — before routing to an approver, check if they're currently
   on PTO; if so, route to a configured backup (`backup_approver_id` — needs a new nullable column
   on `employees`, or a simple config map) or escalate one tier, matching the existing 10.2
   escalation-tier logic already in accounting-engine.

**Verification plan (matches PHASES.md exit criteria):**
- Insert a test `pto_calendar` row starting now; confirm the Sieve script is live (`doveadm sieve
  list`/direct file check) and Mattermost status is set (`GET /users/{id}/status`).
- Confirm orchestrator's routine-work tick skips that employee.
- Create a `pending_approvals` row owned by that employee; confirm it reroutes.
- Advance sim-clock past the window end; confirm both effects revert and a burst fires.

**Risks:** Sieve/ManageSieve integration is the one genuinely uncertain piece — docker-mailserver's
`setup` CLI is well-understood from Phase 14, but Sieve script management may need raw protocol
handling. Budget research time here first before estimating the rest.

---

## Phase 20 — Interpersonal relationships

**Depends on:** 14 (roster), 16 (meeting-simulator) — both already verified working.

**What to build:** almost entirely a `meeting-simulator` extension, not a new service.
`employee_relationships` table already exists (migration 004).

1. **Seed at hire time.** `provisioning/main.py`'s `provision_employee()` (Phase 14, already
   verified) gets a small addition: on first provisioning, insert 1-2 lightweight starting
   `employee_relationships` rows (e.g. same-department pairs default to `neutral`/small positive
   affinity, deterministic — no LLM call). Needs the canonical-ordering constraint already in the
   schema (`employee_a_id < employee_b_id`) respected.
2. **Extend meeting-generation output schema.** `meeting-simulator/main.py`'s LLM call already
   asks for structured JSON (`decisions`, `action_items`, `outcome` — see the Phase 16 log entry).
   Add one more field to that same prompt/schema: a per-attendee `stance` on each decision
   (e.g. `"agree"`/`"disagree"`/`"neutral"`) — spec is explicit this must ride the *existing* LLM
   call, not a second one.
3. **Deterministic affinity update.** After parsing the LLM response, plain Python code (no LLM)
   walks attendee pairs: if two attendees' stances agree on a decision, nudge their
   `affinity_score` up by a small fixed delta; disagree, nudge down. Upsert into
   `employee_relationships` (respecting canonical ordering).
4. **Attendee-selection weighting.** `select_attendees()` (already exists in meeting-simulator,
   deterministic per Phase 16's spec §4.2 note) gets a scoring adjustment: for
   `cross_functional`/similar types where there's a choice of who attends, weight selection toward
   existing high-affinity pairs for the topic at hand. This needs to stay a pure scoring function
   callable directly (per the exit criteria's explicit "test via direct scoring-function call, not
   statistical sampling").
5. **Explicitly NOT in scope this phase:** any dashboard-facing relationship view — that's Phase
   34. Keep this phase backend-only.

**Verification plan:**
- Confirm a fresh employee gets seed relationship row(s) on provisioning.
- Trigger a real meeting with 2+ attendees; confirm each attendee's stance appears in the parsed
  LLM output at no extra LLM-call cost (check LiteLLM's spend log shows the same 1 call as a
  normal meeting of that type).
- Confirm affinity_score shifted by the exact deterministic delta for an agree/disagree pair.
- Call the attendee-scoring function directly with fixed relationship data; confirm allies are
  measurably favored — deterministic assertion, not a statistical sample.

**Risks:** low — this is one of the smaller phases and doesn't need any new appliance
integration, purely extending code paths already proven working.

---

## Phase 23 — KPI scoreboards

**Depends on:** 5 (Mattermost), 6 (Zammad), 7 (Wiki.js), 9 (Akaunting), 22 (external-world revenue
data) — all already verified. `kpi_snapshots` table already exists (migration 004).

**What to build:** a genuinely new service, `kpi-engine/` (currently empty stub) — first service
in this batch that needs its own Dockerfile/main.py/compose entry from scratch, following the
exact pattern established by `accounting-engine`/`external-world` (FastAPI + asyncpg + httpx,
`python:3.12-slim`, `python -c "import urllib.request..."` healthcheck — remember the curl bug
from this session, don't repeat it).

1. **Deterministic daily rollup job.** One function, callable via `POST /rollup/run` (manual
   trigger, matching every other service's pattern) and wired into `orchestrator`'s tick loop for
   the real daily cadence. Pulls, with zero LLM calls:
   - Zammad: ticket counts opened/resolved + avg resolution time, per department/employee
     (`GET /api/v1/tickets/search` or reports API, filtered by date range and group/owner).
   - Wiki.js: page create/update counts (GraphQL `pages.list` filtered by `updatedAt`/`createdAt`
     in range, or an activity/history query if available).
   - Mattermost: message counts per user/channel in range (Mattermost's own reporting API, or a
     `posts` count query per channel if no dedicated stats endpoint exists — needs a quick check
     against the live instance for the cleanest path).
   - Akaunting: revenue in range (reuse `accounting-engine`'s `AkauntingClient` pattern —
     remember it needs the `X-Company` header, per this session's Akaunting fix).
   Writes one row per (entity_type, entity_id, metric, snapshot_date) into `kpi_snapshots`
   (unique constraint already defined in the schema, so reruns for the same date are naturally
   idempotent/upsertable).
2. **Performance-review formula (12.2).** A plain-code function: given a normalization window,
   rank employees within department by a composite of recent `kpi_snapshots`, top quartile → +5%
   pay, second quartile → +2%, rest → +0% (all tunable via env vars, matching the pattern of
   `IC_AUTO_APPROVE_LIMIT` etc. in accounting-engine). Applies the raise the same frictionless way
   Phase 15's raise-application already works (immediate, no approval, `narrative_event` logged) —
   this reuses accounting-engine's existing raise path, kpi-engine just computes the number and
   calls it.
   - **Underperformance → meeting, never an automatic cut.** This half of 12.2 actually belongs to
     Phase 24 (`performance_review` meeting type), which isn't in this batch — kpi-engine should
     just expose "employee X is due a review, here's their KPI standing" (already partially
     present: `meeting-simulator` has a `GET /meetings/pending-performance-reviews` endpoint per
     this session's Phase 18 log — check whether that endpoint already reads from kpi-engine or
     needs kpi-engine to start feeding it).
3. **"Review & approve" mode toggle** — a config flag (env var or, once Phase 34's dashboard
   exists, a UI toggle) that queues proposed raises into `pending_approvals` instead of applying
   them — off by default per spec.

**Verification plan:**
- Run the rollup once over a fixed test date range; independently query each source appliance by
  hand (same style as this session's manual API checks) and confirm `kpi_snapshots` matches
  exactly.
- Confirm zero LLM calls anywhere in the rollup path (check LiteLLM spend log shows no new
  entries after a rollup run).
- Run the review formula against fixed test KPI data; confirm the correct tier's raise actually
  posts through accounting-engine's real raise path.

**Risks:** Mattermost message-count and Zammad resolution-time aggregation are the two pieces
most likely to need real API exploration before implementation (may need reporting/analytics
endpoints not yet touched in this project) — worth a quick research pass against the live
instances before committing to an approach.

---

## Phase 29 — Data purge & snapshots

**Depends on:** effectively everything through Phase 28 (not in this batch, but PHASES.md notes
24/28 recommended-not-required — proceeding without them just means pay-negotiation/crisis data
won't have dedicated purge handling yet, acceptable gap for a first pass).

**This is explicitly flagged in the spec itself as the highest-blast-radius phase in the entire
build ("test in a disposable test environment, not the primary dev environment").** Given this
dev environment now has real accumulated state (20+ employees provisioned, real meetings, real
Akaunting transactions, real Zammad tickets), **do not exercise full-purge or restore against
this environment** without an explicit throwaway clone or fresh `docker compose` project name.

**What to build:** two new services, `purge-manager/` and `snapshot-manager/` (both empty stubs
today), following the same FastAPI pattern as every other custom service.

1. **Purge Manager — scoped purge.** One endpoint per checkbox scope (Emails, Chat, Tickets,
   Wiki, Meetings & narrative memory, Accounting ledger, External world, KPI history, Roster,
   Company direction), each calling that appliance's own bulk-delete/reset API where one exists,
   falling back to truncating the relevant Postgres tables directly:
   - Emails: docker-mailserver `setup email del` per account, or truncate Maildir.
   - Chat: Mattermost channel/post bulk-delete API (`EnableAPIPostDeletion`/`EnableAPIChannelDeletion`
     settings exist in Mattermost's config — noticed during this session's Phase 5 work — will
     need enabling).
   - Tickets: Zammad ticket bulk-delete API.
   - Wiki: Wiki.js `pages.delete` GraphQL mutation, bulk.
   - Meetings & narrative memory: truncate `meetings`, `narrative_threads`, `narrative_events`,
     `action_items`, `pending_reactions`, `pending_approvals` (cascades handle most of this per
     the FK structure this session verified in Phase 13).
   - Accounting ledger: Akaunting has no bulk-wipe API typically — likely a direct DB truncate of
     Akaunting's own MariaDB tables (re-run `AKAUNTING_SETUP` idempotent-install flow after, using
     this session's `akaunting-init/entrypoint-idempotent.sh` fix).
   - External world: truncate `customers`, `market_benchmark`.
   - KPI history: truncate `kpi_snapshots`.
   - Roster: reset `employees` to the original migration-003 seed set (need to re-run that
     migration's INSERT, or store the seed separately for replay), which also implies
     de-provisioning every appliance account created since — this is the trickiest scope, needs
     careful ordering (deprovision appliance accounts *before* truncating the roster row that
     names them).
   - Company direction: reset `company_directives` to a hardcoded default row.
2. **Purge Manager — full purge.** A single endpoint that runs every scoped purge in sequence,
   gated by a typed-confirmation phrase check (the check itself is trivial — the real work is
   making sure the scoped purges above are individually correct and composable).
3. **`system_audit_log` exclusion.** By construction, since purge just doesn't touch that table
   — worth an explicit regression test rather than trusting it by omission.
4. **Snapshot Manager — save.** Captures: each appliance's own DB (`pg_dump`/`mysqldump` via
   docker exec through the socket-proxy pattern — note socket-proxy's `EXEC=0` restriction found
   in Phase 1 blocks direct `docker exec`; this needs either a sidecar dump approach or a
   deliberate, reviewed exception), docker-mailserver's Maildir volume (tar), the narrative
   Postgres schema, sim clock state, roster, company direction — into a named, sim-time-tagged
   bundle (local disk under a new `snapshot_storage` volume, per `net_data`'s description in
   `docker-compose.yml` mentioning "snapshot storage").
5. **Snapshot Manager — restore.** Stops affected containers, restores each captured piece,
   restarts. Same confirmation gate as scoped purge.

**Verification plan:** build and test purge/snapshot against a **separate throwaway Docker
Compose project** (`docker compose -p fakeco-test ...` or a git worktree with its own `.env`/
volume names) — never the primary environment with 20+ real employees and live Akaunting data.
Exercise each scoped-purge checkbox independently, confirm isolation from other scopes. Save a
snapshot, mutate significantly, restore, diff every appliance's state against the snapshot.

**Risks:** highest in this entire plan. The socket-proxy `EXEC=0` restriction (deliberately
locked down in Phase 1) directly conflicts with the most natural way to `pg_dump`/`mysqldump`
inside appliance containers — needs a real design decision (sidecar containers with direct DB
network access instead of `docker exec`, most likely) before implementation starts. Flag this for
explicit user sign-off before building, given the spec's own "highest blast-radius" warning.

---

## Phase 30 — Branding & asset manager

**Depends on:** 5 (Mattermost), 6 (Zammad), 7 (Wiki.js), 14 (roster) — all already verified.

**What to build:** a new service, `branding-manager/` (empty stub today), small per spec's own
"Size: S" estimate.

1. **First-boot emoji pack.** Mattermost supports custom emoji upload natively
   (`POST /api/v4/emoji`, multipart image upload) — a one-time provisioning step, could live in
   `branding-manager` or just be folded into `provisioning`'s first-boot flow. Needs a bundled
   image asset set (a handful of themed PNGs checked into the repo, e.g. under
   `branding-manager/assets/emoji/`).
2. **Asset library + employee_id -> avatar_asset_id mapping.** A small Postgres table (new
   migration, e.g. `006_branding.sql`) mapping `employee_id` to a chosen avatar asset. Bundled
   avatar image library also checked into the repo (`branding-manager/assets/avatars/`).
3. **Per-appliance avatar push.** Three real API calls per employee, matching this session's
   established impersonation-token pattern:
   - Mattermost: `POST /api/v4/users/{id}/image` (multipart).
   - Zammad: `PUT /api/v1/users/{id}` supports an avatar via a separate `/api/v1/avatars` upload
     endpoint — needs a quick check against the live instance for the exact multipart shape.
   - Wiki.js: user profile avatar is typically a URL/base64 field on the `users.update` GraphQL
     mutation, not a separate upload endpoint — confirm against the live schema (same
     introspection technique used to debug Wiki.js in Phases 7/14 this session).
4. **Bulk actions.** `POST /branding/bulk-apply` accepting employee-ID list + asset selection
   (`randomize`, `apply-one-to-all`, `reset-to-default`) — thin wrapper looping the per-appliance
   push above.

**Verification plan:**
- Bulk-apply a test avatar set to 3 employees; confirm each appliance's own profile shows the new
  image via that appliance's own API (not just "the call returned 200").
- Push the emoji pack; confirm a message using one of the new emoji renders correctly.
- Confirm reset-to-default and apply-to-everyone-selected both work.

**Risks:** low-to-moderate — mostly straightforward appliance API calls, similar difficulty to
Phase 14's provisioning work. Zammad and Wiki.js's exact avatar-upload API shapes are the only
unknowns; budget a short research pass against the live instances (same style as this session's
GraphQL introspection debugging) before implementing.

---

## Phases 33-37 — Dashboard (all tabs + TV wall)

**Depends on:** by the time this batch starts, effectively every backend phase through 32 should
exist — 33/34/35/36 each gate on a different subset. Given this plan's scope (19, 20, 23, 29, 30
+ dashboard), the dashboard can only be fully built once those backends exist; **build order
should be: 19 → 20 → 23 → 29 → 30 → (24, 27, 28, 31, 32 — not yet planned, needed for full
dashboard coverage) → 33-37.** If the user wants dashboard work sooner, it can proceed
tab-by-tab against whatever backends already exist (Phase 33's Simulation/LLM/Narrative tabs only
need Phases 10/12/18/31/32 — 31/32 aren't planned yet either, worth flagging).

**What to build:** `dashboard/` (empty stub today) is a genuinely large, multi-page web app —
first frontend-heavy piece in this entire project. Needs an explicit tech-stack decision this
plan doesn't make (spec is silent on framework — likely a lightweight server-rendered app or a
small SPA talking to a thin API-gateway backend, per BUILD_LOG's Phase 0 log noting "dashboard
backend = thin API gateway" as an absorbed spec clarification). Recommend deciding this
up-front rather than per-tab.

### Phase 33 — Shell + Simulation/LLM/Narrative tabs
- Dashboard shell + routing, deployed on `net_mgmt` (per network table).
- Simulation controls: start/stop, worker scale, speed slider — calls sim-clock's real
  `/set_speed` API (already verified this session) plus a not-yet-planned "worker scale" concept
  (Phase 32, not in this batch — needs its own investigation into what "worker scale" means
  concretely for this architecture before the tab can be built).
- LLM status tab: provider/fallback display reads LiteLLM's config + `/spend/logs` (both already
  proven working this session).
- Narrative view: open threads/action items/pending reactions&approvals/meetings — straight reads
  against tables already verified in Phase 13/17/18.

### Phase 34 — HR, Payroll, Accounting tabs
- Org Chart/HR: roster list + Fire/Hire wired to `provisioning`'s real endpoints (Phase 14,
  verified) + Phase 20's relationship view (node/edge viz — needs a charting library decision).
- Payroll: per-employee pay editor; raise applies immediately via accounting-engine's existing
  path; cut must route to a `pay_negotiation` meeting — **this specific behavior is Phase 24's
  responsibility, not yet planned in this batch** — the dashboard tab can be built, but the
  cut-routes-to-meeting backend logic needs Phase 24 first, or the tab will have a stubbed/
  disabled cut path until then.
- Accounting: cash balance + Akaunting deep link + expense-approval queue (Phase 15, verified) +
  payroll history + audit-correction log (Books Auditor output, Phase 15, verified this session
  once the Akaunting bug fix lands).

### Phase 35 — External World, KPI/Performance, Company Direction tabs
- External World tab: reads external-world's `system_audit_log` entries (BetaCorp offers/
  resignations, verified working this session) + `customers` table (now seeded, per the
  in-progress background task) for pipeline/at-risk/revenue-by-customer views.
- KPI/Performance tab: reads `kpi_snapshots` (Phase 23, planned above) + review-mode toggle.
- Company Direction: textarea + Save, writing `company_directives` (table exists, verified in
  Phase 13) + sync to a pinned Wiki.js page (straightforward GraphQL call, same pattern as
  meeting-simulator's Wiki.js integration built this session).

### Phase 36 — Chaos, Data Management, Branding tabs
- Chaos tab needs Phases 27/28 (not in this batch, not yet planned) — per-appliance up/down
  toggle via socket-proxy (Phase 1's START/STOP/RESTART allow-list, already verified working) and
  the crisis Trigger Event control.
- Data Management tab wires directly to Phase 29's purge-manager/snapshot-manager (planned above)
  — re-verify the typed-confirmation gate specifically through the UI, not just hitting the API
  directly, per the exit criteria's explicit wording.
- Branding tab wires to Phase 30 (planned above).

### Phase 37 — TV wall, Errors panel, deep links, log tail
- `/tv` route: presentation-only, composes data every other tab already exposes — genuinely the
  lightest phase in the dashboard batch per spec's own note ("shouldn't need meaningful new
  backend logic").
- Errors panel: needs every custom service to expose its own recent-exceptions endpoint or push to
  a shared error-log table/Loki stream — worth deciding the mechanism once, applied uniformly,
  rather than bolting it onto each service ad hoc. Loki is already running and aggregating every
  container's stdout (verified Phase 11) — likely cheapest path is a Loki query scoped to
  `level="ERROR"` across all `fakeco-*` containers rather than a new dedicated table.
- Deep links: static config mapping each appliance to its real hostname (all already resolvable
  via Traefik, verified throughout this session) plus the Principal's own account URLs.
- Live Traefik/Technitium log tail: another Loki query (`{container=~"fakeco-traefik|fakeco-dns"}`)
  — actually already prototyped as a Grafana panel in this session's Phase 11 dashboard work
  (`traffic-and-activity.json`); the dashboard just needs to embed/replicate that same query.

**Cross-cutting dashboard risks:** this is the single largest remaining scope in the whole
project (5 phases, dozens of UI surfaces) and is the first place a frontend framework choice
actually matters. Recommend a short up-front design pass (tech stack + auth/access model, since
`net_mgmt` is host-published) before Phase 33 starts, rather than deciding it mid-build.

---

## Phase 38 — Deployment hardening, first-boot polish, README

**Depends on:** everything (0-37) — genuinely last, and the plan above already surfaces several
phases not yet planned (24, 27, 28, 31, 32) that would need to land first for this phase's exit
criteria to be fully meetable. Treat this as the final phase once the rest of the roadmap is
actually built, not something to start in parallel.

**What to build:** no new service — this is integration/polish work across everything else.

1. **Clean-environment first-boot test.** From zero volumes and no `.env`, confirm
   `docker compose up -d` brings up the entire stack unattended. This session discovered several
   places where genuine manual/one-off steps were needed that should really be automated here:
   Wiki.js's `setApiState(enabled: true)` toggle, Mattermost's `EnableUserAccessTokens` config,
   the `external.relay@fakecorp.internal` mailbox, Akaunting's `X-Company` header requirement
   surfacing correctly, and Zammad's admin role/group assignment (all found and manually fixed
   in this session's earlier phases) — Phase 38 should turn every one of these into an automated
   first-boot step rather than tribal knowledge in `BUILD_LOG.md`.
2. **First-boot automation:** admin setup + account/token generation for the full roster +
   Principal (Phase 14's `provision --all` + `provision-principal`, already working — just needs
   to be the thing that actually runs on first boot, not a manual CLI invocation), Akaunting
   chart-of-accounts setup (this session created 3 categories manually during Phase 9 — should be
   scripted), initial branding pass (Phase 30).
3. **`.env.example` accuracy audit.** Diff every env var actually referenced across every
   service's `main.py`/`docker-compose.yml` against `.env.example` — this session already found
   and fixed several gaps here (`MAILSERVER_BOT_SECRET`, `WIKIJS_ADMIN_EMAIL/PASSWORD`,
   `AKAUNTING_*_CATEGORY_ID`, etc.) but a full systematic pass hasn't been done since the dashboard
   and remaining phases will add more variables.
4. **README.** Deployment steps, first-boot walkthrough, actual measured RAM/disk usage (spec
   estimates 8-10GB — worth measuring the real footprint of this now-30-container stack rather
   than trusting the estimate), troubleshooting section (this session's `BUILD_LOG.md` has
   substantial real troubleshooting material to draw from — the curl-healthcheck bug, the
   Zammad Redis dependency, the Traefik network-label routing bug, etc. are all exactly the kind
   of thing a README's troubleshooting section should preempt), and a walkthrough of every
   dashboard tab.

**Verification plan:** the literal exit criteria is the strongest test in the whole spec — wipe
everything (fresh volumes, fresh `.env` from `.env.example` plus real secrets) and confirm one
`docker compose up -d` produces a fully working, fully populated environment with no manual
intervention. This is also the natural point to retire `PLAN_REMAINING_PHASES.md` (this file) and
`BUILD_LOG.md`'s blow-by-blow entries into the polished README.

---

## Suggested overall build order for this batch

1. **Phase 20** (relationships) — smallest, purely extends already-verified meeting-simulator,
   no new appliance integration risk.
2. **Phase 23** (KPI engine) — new service but low integration risk (all four source appliances
   already have working clients elsewhere in the codebase to copy patterns from).
3. **Phase 19** (PTO) — needs a bit of Sieve-protocol research, otherwise reuses established
   patterns.
4. **Phase 30** (branding) — small, needs a short API-shape research pass for Zammad/Wiki.js
   avatars.
5. **Phase 29** (purge/snapshots) — flagged highest-risk; do this in an isolated environment, and
   get explicit sign-off on the socket-proxy `EXEC=0` vs. dump-mechanism design question before
   writing code.
6. **Phases 33-38** last, once a tech-stack decision is made for the dashboard and the plan gaps
   noted above (24, 27, 28, 31, 32) are at least scoped, since several dashboard tabs and Phase
   38's exit criteria directly depend on them.
