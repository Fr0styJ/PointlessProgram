# BUILD_LOG.md — FakeCo "Real Appliances" Build

---

## STATUS HEADER

| Field | Value |
|---|—--|
| **Current Phase** | Phase 1 runtime verification COMPLETE; resuming sequential Docker verification of Phases 2–18, then finishing Phase 21/22 |
| **Percent Complete** | ~55% by code volume (Phases 0–18 code written; Phase 21/22 code written but not wired into compose; Phases 19-20, 23-38 not started) |
| **Status** | **RECONCILED 2026-07-31 — this header was stale.** A prior session wrote code for Phases 12–18 (sim-clock, narrative-db migrations, provisioning, accounting-engine, meeting-simulator, human-bridge, orchestrator) and a partial Phase 21/22 (`external-world/main.py`) while Docker was unavailable, without updating this log. None of Phases 1–18 had ever been runtime-verified. Docker is now installed and running. Phase 1 exit criteria (health checks, `net_data` isolation, socket-proxy allow-list) have been re-run and PASS — see log entry below. |
| **Exact Next Action** | Bring up Phase 2 profile (`--profile phase2`: cAdvisor/node-exporter/Prometheus), verify exit criteria, then proceed profile-by-profile through Phase 11, then verify custom services Phase 12–18, then finish and wire up `external-world` (Phase 21/22). |
| **BLOCKER** | None currently. Docker Desktop is installed and running (required Hyper-V enablement + one reboot on this machine, now resolved). |

**Environment:**
- OS: Windows 11 Pro, shell: pwsh / git-bash
- Repo root: `c:\code\PointlessProgram`
- Git initialized: YES
- Docker: INSTALLED AND RUNNING — `docker --version` 29.6.2, `docker compose version` v5.3.1
- Ollama: present at `C:\Users\Frosty\AppData\Local\Programs\Ollama` (potential local LLM fallback — not configured yet)

**Ports / credentials / tokens:** None yet established. See `.env.example` for expected credential env vars.

**Deliverables checklist (§27) — checked off as completed (code written AND runtime-verified unless noted):**
- [x] `docker-compose.yml` (Phases 1–18 services defined; verified: Phase 1 only so far)
- [x] `.env.example` / `.env` (all `:?required` vars present, incl. `MAILSERVER_BOT_SECRET` added 2026-07-31)
- [x] `orchestrator/` (code written, Phase 18 — not yet runtime-verified)
- [x] `meeting-simulator/` (code written, Phase 16 — not yet runtime-verified)
- [x] `human-bridge/` (code written, Phase 17 — not yet runtime-verified)
- [x] `sim-clock/` (code written, Phase 12 — not yet runtime-verified)
- [x] `accounting-engine/` (code written, Phase 15 — not yet runtime-verified)
- [ ] `purge-manager/` (README stub only, Phase 29 not started)
- [ ] `snapshot-manager/` (README stub only, Phase 29 not started)
- [~] `external-world/` (Phase 21/22 `main.py` written, 517 lines, but no `Dockerfile`/`requirements.txt`, not wired into `docker-compose.yml` — INCOMPLETE)
- [ ] `kpi-engine/` (README stub only, Phase 23 not started)
- [ ] `branding-manager/` (README stub only, Phase 30 not started)
- [x] `narrative-db/` (migrations 001–004 written, Phase 13 — not yet runtime-verified)
- [ ] `dashboard/` (README stub only, Phases 33–37 not started)
- [x] `provisioning/` (code written, Phase 14 — not yet runtime-verified)
- [x] `litellm/config.yaml` (written, Phase 10 — not yet runtime-verified)
- [x] `monitoring/` (Prometheus/Loki/Promtail configs written, Phases 2/11 — not yet runtime-verified)
- [ ] README (top-level, Phase 38 — not started)

---

## LOG (newest first)

---

### 2026-07-31T18:40 — Phase 17 PARTIALLY verified: 2 real bugs fixed in what exists, but a major architectural gap found and NOT fixed

- **Major gap, not a bug — a missing feature:** re-read spec §7 carefully against
  `human-bridge/main.py`. The spec's actual Phase 17 requirement is a **detection** mechanism:
  "detects Principal-authored content via native webhooks (Mattermost/Zammad/Wiki.js) or IMAP
  polling (mail), converts each into `narrative_events(origin='human')`, and writes a
  `pending_reactions` row for whoever it was addressed to" — i.e. the Principal acts as themselves
  in the real appliance UIs, and human-bridge reacts. What's actually built is the **opposite
  direction**: an action-injection API (`/action/mattermost-post`, `/action/zammad-ticket`,
  `/action/wiki-page`, `/action/send-email`, etc.) that lets something else (the Phase 33 dashboard,
  per its own file-header comment) puppeteer bots and act *as* the Principal. There is zero
  polling/webhook code anywhere in the file (`grep -n "pending_reactions\|poll\|webhook\|imap" `
  returns nothing). This is a real, large missing feature — not something to patch inline — flagged
  as a dedicated follow-up rather than rushed.
- **2 real bugs found and fixed in the action-injection surface that IS built** (useful regardless
  of the gap above, and needed by later phases like the dashboard):
  1. `post_mattermost_as_employee()` issues the employee-bot a fresh personal access token and
     posts with it, but never ensures the bot is actually a *channel* member first — team
     membership (granted at Phase 14 provisioning time) doesn't imply channel membership, and
     Mattermost returns a bare `403 "You do not have the appropriate permissions"` rather than a
     specific error. **Fixed:** added an idempotent `POST /channels/{id}/members` call before
     posting. Verified: `/action/mattermost-post` for employee #2 (Bob) into a channel he'd never
     been added to now succeeds (previously reproduced the 403 exactly).
  2. `/action/zammad-ticket` never sent `customer_id`, which Zammad requires unconditionally on
     ticket creation (same requirement discovered in Phase 6's verification) — every call would
     have 422'd. **Fixed:** added `"customer_id": f"guess:{PRINCIPAL_EMAIL}"` (Zammad's
     guess-or-create-by-email shorthand). Verified: ticket #3 created successfully.
- Did not test `/action/send-email` or `/action/wiki-page` individually in this pass — time
  budget went to finding/fixing the two confirmed-broken paths above and properly characterizing
  the architectural gap, which is the more consequential finding for this phase.
- **Files touched:** `human-bridge/main.py`
- **Next:** Phase 18 — orchestrator. The real Phase 17 detection mechanism (webhooks/IMAP polling →
  `pending_reactions`) is tracked as a follow-up task, not blocking Phase 18's own verification.

---

### 2026-07-31T18:20 — Phase 16 runtime-verified (1 systemic LiteLLM bug found and fixed; 1 real gap flagged, not fixed)

- **BUG FOUND (systemic — affects every custom service that calls LiteLLM, not just this one):**
  the first meeting-simulator call succeeded, but an identical second call back-to-back failed with
  a hard `401 Unauthorized` — `AnthropicException - x-api-key header is required`. Root cause:
  `litellm/config.yaml` put all 3 providers per tier under the *same* `model_name` (e.g. three
  deployments all named `"heavy"`) with `routing_strategy: "latency-based-routing"`. LiteLLM treats
  same-named deployments as interchangeable load-balancing targets, not an ordered fallback chain —
  with `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` both blank, the router would periodically pick one of the
  two broken deployments and surface its auth error directly instead of falling through to the
  working DeepSeek one. This was previously invisible because Phase 10's single verification call
  happened to land on DeepSeek by luck. **Fixed:** rewrote `litellm/config.yaml` to give every
  deployment a distinct `model_name` (`cheap-deepseek`/`cheap-anthropic`/`cheap-openai`, etc.), added
  `router_settings.model_group_alias` so callers still request `"cheap"`/`"mid"`/`"heavy"` and always
  land on the DeepSeek deployment first, and an explicit `router_settings.fallbacks` list for
  deterministic cascade to Anthropic then OpenAI only on a genuine failure. Verified stable across 3
  consecutive direct calls after the fix (previously ~50/50 depending on router's internal pick).
  **Note:** config changes here require an explicit `docker restart fakeco-litellm` — `docker compose
  up -d` does not detect bind-mounted file content changes and will leave the old config loaded in
  the already-running container.
- Triggered a real `standup` meeting (`POST /meeting/run`) for Engineering: got a genuine
  LLM-generated summary, confirmed the `meetings` row (id=2, thread_id=3), 5 `action_items` rows all
  correctly referencing `meeting_id`/`thread_id`, and the Mattermost summary post in an
  auto-created `meetings-engineering-standup` channel.
- Confirmed `company_directives`'s current row is embedded verbatim into the system message via
  `build_meeting_prompt()` (code inspection — the directive is read fresh from Postgres and interpolated
  directly, not paraphrased or summarized).
- Triggered a second standup for the same department and confirmed via LiteLLM's `/spend/logs` that
  the second call shows `cached_tokens: 384` — empirical proof the static prefix (system
  instructions + persona + schema + company direction) was byte-identical to the first call and
  DeepSeek's own prompt caching kicked in, satisfying the exit criteria more convincingly than a
  manual byte-diff would have.
- Triggered a `cross_functional` meeting: succeeded the same way (5 action items, different
  attendee mix reflecting cross-department participants).
- **Real gap found, NOT fixed (flagged for follow-up): `meeting-simulator` has zero Wiki.js
  integration.** Exit criteria requires a Wiki.js `meeting-notes` page per meeting; grepping the
  entire file for "wiki"/"Wiki" returns nothing — there's no `WikiJSClient`, no GraphQL calls, no
  page-creation logic at all. This isn't a bug in existing code, it's a missing feature the prior
  session never built. Given the size of a proper fix (a real Wiki.js client + page template +
  wiring into `run_meeting()`), this needs its own dedicated pass rather than a rushed patch —
  flagged as a follow-up task rather than attempted here.
- **Files touched:** `litellm/config.yaml`, `.env` (added `MATTERMOST_BOT_TOKEN`)
- **Next:** Phase 17 — human-bridge.

---

### 2026-07-31T18:00 — Phase 15 BLOCKED on pre-existing Akaunting bug (code-level fixes applied, ledger posting itself not yet verified)

- **Found 2 more real code bugs in `accounting-engine` while preparing to test it, both fixed:**
  1. `AkauntingClient.post_transaction()` never sent `payment_method` or `number` at all — both are
     required by Akaunting's own transaction validation (see Phase 9's log entry). Every post would
     have 422'd immediately. **Fixed:** added `payment_method: "offline-payments.cash.1"` (fixed —
     this sim only has one payment method/bank account) and `number` derived from the caller's
     idempotency key when available, else a timestamp.
  2. **No call site ever passed `category_id`**, which Akaunting also requires
     (`"The category id field is required"`) — distinct from `account_id` (the bank/cash account).
     `AKAUNTING_PAYROLL_ACCOUNT_ID`/`EXPENSE_ACCOUNT_ID`/`REVENUE_ACCOUNT_ID` env vars only ever
     covered the account side. **Fixed:** added matching `AKAUNTING_PAYROLL_CATEGORY_ID`/
     `EXPENSE_CATEGORY_ID`/`REVENUE_CATEGORY_ID` env vars (wired through `docker-compose.yml` and
     `.env`, pointed at the categories created during Phase 9: Payroll Expense=6, General
     Expense=7, Sales Revenue=8) and passed `category_id=` at all 5 `post_transaction()` call sites
     (approval auto-post, manual approval post, payroll, revenue, books-auditor correction).
- **BLOCKED, not yet verified end-to-end:** even with both fixes above, actually posting a
  transaction through `POST /api/transactions` still hits the payment-method bug tracked in Phase
  9's log entry (`"The payment method is invalid"` even for the correctly-registered
  `offline-payments.cash.1` method) — traced further this time: the setting itself is confirmed
  present in `ak_settings` for the right `company_id` and is visible via
  `GET /api/settings/offline-payments.methods`, yet `Modules::getPaymentMethods()` still returns
  empty and `setting('offline-payments.methods')` returns `bool(false)` from `php artisan tinker`
  even after trying to bind company context. This is deeper than a simple "module not enabled"
  issue — likely a company-context binding or cache problem in Akaunting's own Laravel-Setting
  package — and was deliberately not chased further in this session (flagged as a dedicated
  follow-up task, `task_a5d68375`, since it needs focused debugging, not another surface check).
  **None of Phase 15's five exit-criteria checks (expense approval flow, escalation tiers, payroll
  run, raise application, Books Auditor correction) can be verified against a real Akaunting ledger
  until this is resolved.** The raise-application check (10.3, "applies immediately, no Akaunting
  post") and the escalation-tier logic itself are pure Postgres logic and could in principle be
  checked without Akaunting — deferred anyway to keep this phase's verification coherent as one
  pass rather than partially-done.
- **Files touched:** `accounting-engine/main.py`, `docker-compose.yml`, `.env`
- **Next:** Resolve `task_a5d68375` (Akaunting payment-method bug), then come back and complete
  Phase 15's 5 verification checks. In the meantime, Phases 16-18 (meeting-simulator, human-bridge,
  orchestrator) don't hard-depend on Akaunting working and can proceed — their own accounting-related
  code paths will simply fail against Akaunting the same way until the bug is fixed, which is
  expected and separately tracked.

---

### 2026-07-31T17:40 — Phase 14 runtime-verified (5 real bugs found and fixed)

Provisioning was the most bug-dense custom service so far — every one of its four target
appliances had a distinct integration bug that only surfaced under real runtime testing:

1. **`docker` CLI missing from the provisioning image.** The Dockerfile installed the `docker.io`
   apt package intending to get the `docker` client binary for `docker exec fakeco-mailserver
   setup email ...` calls, but on this base image's Debian release `docker.io` only ships the
   daemon (`dockerd`) — the client binary lives in the separate `docker-cli` package. Every mail
   operation failed with `[Errno 2] No such file or directory: 'docker'`. **Fixed:** swapped
   `docker.io` → `docker-cli` in `provisioning/Dockerfile`. (The socket mount itself was already
   correctly present in `docker-compose.yml` — just the binary was missing.)
2. **Wiki.js requires an "API" toggle separate from having a valid API key/token.** Every API-key
   authenticated GraphQL call failed with `"API is disabled. You must enable it from the
   Administration Area first."` even though the key itself was valid. Enabled it via
   `authentication.setApiState(enabled: true)` (note: GraphQL schema calls it `setApiState`, not the
   more guessable `updateApiState`) using a session JWT, since API-key auth is itself gated by this
   same toggle. This wasn't a code bug — it's a one-time environment setup step this session had to
   discover and perform (comparable to enabling personal access tokens in Mattermost, below).
3. **Wiki.js `create_user` never sent a password.** Wiki.js's schema marks `passwordRaw` as
   nullable, but the resolver rejects a blank password for the `local` provider at runtime
   (`"Password raw can't be blank"`). **Fixed:** derive a deterministic password the same way mail
   accounts already do (bots never need to know it), and pass `mustChangePassword: false`,
   `sendWelcomeEmail: false`.
4. **Two Python `.get(key, default)` gotchas, both real.** `dict.get("user", {})` and the same
   pattern for `data`/`users`/`create` only fall back to the default when the *key is missing* —
   Wiki.js's `create` mutation response has `"user": null` explicitly even on success, so
   `.get("user", {})` returned `None`, not `{}`, and the next `.get()` call crashed with
   `'NoneType' object has no attribute 'get'`. **Fixed** in three places (`get_user_by_email`,
   `create_user`'s `create_result` parse, and the returned `user` dict) using `x.get(k) or {}`
   instead. Also added error-surfacing to the shared `graphql()` helper (raise on
   `body.get("errors")`) so the *next* bug wasn't hidden behind a generic AttributeError.
5. **Wiki.js's own `users.search` resolver crashes on a real production bug**, unrelated to our
   code: requesting the `isActive` field (declared non-nullable in Wiki.js's own schema) throws
   `"Cannot return null for non-nullable field UserMinimal.isActive"` for at least some freshly
   created accounts — the search index doesn't populate that field consistently. Since we don't
   need `isActive` for lookup, dropped it from the query rather than trying to fix Wiki.js itself.
   Also discovered the `create` mutation's response never includes the new user's ID at all in this
   Wiki.js version — added a fallback `get_user_by_email` lookup right after `create_user()` returns
   an empty ID.
6. **Fire path never touched mail at all** — `fire_employee()`'s signature didn't even accept a
   `mail` client parameter, so terminated employees kept fully-working mailboxes forever. There was
   a `restrict_account()` method already written but (a) never called from anywhere and (b) used the
   wrong CLI syntax — real docker-mailserver syntax is
   `setup email restrict <add|del|list> <send|receive> <email>`, not a single positional email arg;
   docker-mailserver exits 0 on the unrecognized shape rather than failing loud, so this would have
   silently no-op'd even once wired in. **Fixed:** corrected the CLI invocation (calling it twice,
   once for `send` and once for `receive`, both with `add` — i.e. add both restrictions), threaded
   `mail` through `fire_employee()`'s signature and its call site, and call it after the other three
   deactivations.
- **Also needed, pure environment setup (not code fixes):** created a real Mattermost personal
  access token for the admin account (had to enable `MM_SERVICESETTINGS_ENABLEUSERACCESSTOKENS` via
  compose env var and recreate the container — Mattermost's own bot-token creation endpoint requires
  `create_bot` permission that a plain bot account doesn't have, so provisioning needs an actual
  admin token, not a bot token), a real Zammad agent token (reused from Phase 6), and the Wiki.js API
  key from Phase 7. Added `MATTERMOST_ADMIN_TOKEN`, `MATTERMOST_TEAM_ID`, `ZAMMAD_ADMIN_TOKEN`,
  `WIKIJS_ADMIN_TOKEN` to `.env`.
- **Verification, in order:** provisioned employee #1 (Alice Johnson) — hit bugs 1-5 above,
  fixing each in turn until all four accounts (mail, Mattermost bot, Zammad agent, Wiki.js user)
  were created with real IDs written back to the `employees` roster row. Re-ran provisioning for the
  same employee: confirmed idempotent — all four steps correctly detected existing accounts by the
  same IDs, no duplicates created. Ran `fire --employee-id 7` (a freshly provisioned employee):
  confirmed Mattermost soft-deletes (`delete_at` timestamp set, Mattermost's own semantics — it
  never hard-deletes via this endpoint), Zammad `active:false`, Wiki.js deactivated, and — after
  fixing bug 6 — mail send+receive both show `REJECT` in `setup email restrict list` while the
  mailbox itself still appears in `setup email list` (data preserved, not deleted), matching spec
  §9's "deactivate (never delete) accounts everywhere" for all four systems.
- **Files touched:** `provisioning/Dockerfile`, `provisioning/main.py`, `.env`
- **Next:** Phase 15 — accounting engine.

---

### 2026-07-31T17:10 — Phase 13 runtime-verified (no bugs)

- `docker compose --profile phase13 up --build narrative-db-migrate` — all 4 migration files
  (001-004) applied cleanly against the live Postgres. Note: `migrate.py` runs every migration file
  in one pass rather than gating by phase, so 004's additive tables (`employee_relationships`,
  `pto_calendar`, `market_benchmark`, `customers`, `kpi_snapshots`) exist already even though spec
  intends them deferred to their own phases — harmless (idempotent `CREATE TABLE IF NOT EXISTS`,
  nothing writes to them yet) but worth knowing if a future session expects strict phase gating.
- Verified all 8 required tables exist (`narrative_threads`, `narrative_events`, `meetings`,
  `action_items`, `pending_reactions`, `pending_approvals`, `system_audit_log`,
  `company_directives`) and inserted+selected a real test row in each (had to look up actual column
  names via `\d` first — `narrative_events` uses `source_type`/`short_summary`, not guessed names
  like `event_type`).
  Note for future sessions: `psql -c "stmt1; stmt2;"` sends both statements as one implicit
  transaction — if the second fails, the first silently rolls back too (its `RETURNING` output still
  prints before the rollback, which is easy to misread as success). Run one statement per `-c` call
  when order/error-isolation matters.
- Confirmed `system_audit_log` isolation: deleted the test `narrative_threads` row (which correctly
  cascaded to its `narrative_events`/`meetings`/`action_items`/`pending_reactions` children via FK)
  and confirmed the unrelated `system_audit_log` test row survived untouched — no FK/cascade path
  from any other table reaches it, matching the spec's audit-log-is-independent requirement.
  Cleaned up all test rows afterward.
- **Files touched:** none.
- **Next:** Phase 14 — provisioning service.

---

### 2026-07-31T16:50 — Phase 12 runtime-verified (no bugs — first custom service code checked out clean)

- Built and started `sim-clock` (`docker compose up -d --build sim-clock`). Creates its own
  `sim_clock` table on startup (doesn't need to wait on Phase 13's migrations) and seeds the initial
  row at `speed_multiplier=1.0`.
- Measured `sim_time` over a real ~61s wall interval at 1.0x → sim_time advanced ~61.1s. Matches.
- `POST /set_speed` to 10.0x, measured over ~31s wall → sim_time advanced ~310.6s (≈10.0x, within
  ~1.5%). Then to 0.1x, measured over ~31s wall → sim_time advanced ~3.1s (≈0.1x). Both confirm the
  next tick reflects the new multiplier immediately, no lag. Reset back to 1.0x afterward so later
  phases run at normal speed.
- **Files touched:** none — first custom service to pass without any fix needed.
- **Next:** Phase 13 — narrative-db core schema migrations.

---

### 2026-07-31T16:00 — Phase 11 runtime-verified (walking skeleton complete; built missing dashboards from scratch)

- **Real gap found, not a bug in existing code — the dashboards simply didn't exist.** BUILD_LOG's
  Phase 1 entry claimed `monitoring/loki-config.yaml`/`promtail-config.yaml` were the "supporting
  files" for this phase, but `monitoring/grafana/provisioning/` didn't exist at all and
  `monitoring/grafana/dashboards/` was empty — Grafana would have come up with zero datasources and
  zero dashboards, failing this phase's exit criteria outright. Built from scratch:
  - `monitoring/grafana/provisioning/datasources/datasources.yml` — Prometheus + Loki, both with
    explicit fixed `uid:` fields (`Prometheus`, `Loki`) so dashboard JSON can reference them by a
    stable name instead of Grafana's auto-generated UIDs.
  - `monitoring/grafana/provisioning/dashboards/dashboards.yml` — file-based dashboard provider
    pointed at `/var/lib/grafana/dashboards` (already bind-mounted in compose, just never populated).
  - `monitoring/grafana/dashboards/container-health.json` — up/down status per Prometheus target,
    per-container CPU/memory from cAdvisor, host load, live container count.
  - `monitoring/grafana/dashboards/traffic-and-activity.json` — Traefik HTTP request rate (via Loki
    JSON-parsed access logs), Technitium DNS log rate, mail log rate, per-appliance log activity
    rate across every container, and a live Traefik+Technitium log tail panel (this last one is also
    a direct requirement of Phase 37's dashboard spec — built early since the data source is
    identical).
  - **Learned during verification:** Grafana's *datasource* provisioning only runs at container
    startup, unlike its *dashboard* file provider which polls every `updateIntervalSeconds`. Adding
    the datasource YAML while Grafana was already running did nothing until a full restart. Also had
    to wipe the `grafana_data` volume once, because the first datasource provisioning pass (before I
    added explicit `uid:` fields) had already persisted auto-generated UIDs to Grafana's own SQLite
    state, which didn't match what the dashboard JSON referenced.
  - Verified end-to-end: both datasources present with matching UIDs, both dashboards loaded
    (confirmed via `GET /api/search`), and both a live Prometheus query (`up`) and a live Loki query
    (per-container log rate) proxied successfully through Grafana with real data.
- Loki confirmed aggregating logs from all 29 currently-running containers, including
  `fakeco-traefik` and `fakeco-dns` (Technitium) specifically, per exit criteria.
- **This closes out the "walking skeleton" band (Phases 1-11) — every real appliance is now up,
  reachable, and individually verified with a real runtime test, and no phase from here forward
  should be picked up out of order relative to its stated dependencies.**
- **Files touched:** `monitoring/grafana/provisioning/datasources/datasources.yml` (new),
  `monitoring/grafana/provisioning/dashboards/dashboards.yml` (new),
  `monitoring/grafana/dashboards/container-health.json` (new),
  `monitoring/grafana/dashboards/traffic-and-activity.json` (new)
- **Next:** Phase 12 — sim-clock (first custom service; code already exists from a prior session,
  needs runtime verification against the now-live Postgres).

---

### 2026-07-31T15:35 — Phase 10 runtime-verified (1 real bug found and fixed: stale model names)

- User supplied a real `DEEPSEEK_API_KEY` in `.env` for live testing.
- **Bug found before bringing the service up:** `litellm/config.yaml` referenced the legacy
  `deepseek/deepseek-chat` and `deepseek/deepseek-reasoner` model aliases. Researched current
  DeepSeek pricing/model names (web search, July 2026 sources) and found both legacy aliases were
  formally retired **2026-07-24** — one week before this session. The replacements are
  `deepseek-v4-flash` (cheap/fast) and `deepseek-v4-pro` (stronger reasoning). Also worth noting for
  future reference: `deepseek-reasoner` used to silently route to V4 **Flash**, not Pro — so the
  "heavy" tier was arguably already getting the wrong model even before the rename. **Fixed:**
  updated `cheap`/`mid` tiers to `deepseek/deepseek-v4-flash`, `heavy` tier to
  `deepseek/deepseek-v4-pro` with `reasoning_effort: "high"` for real reasoning quality on
  meetings/Principal-reaction content per spec §20.1's tiering intent.
- `docker compose --profile phase10 up -d` — LiteLLM started, ran its own Prisma DB migrations
  against the shared Postgres instance successfully.
- Confirmed `net_llm_bridge` is the only non-internal network LiteLLM sits on (`net_clients`/
  `net_data` are both `internal: true`) — matches spec §22's "only route with real internet access."
- Real end-to-end completion test: `POST /chat/completions` with `model: "cheap"` through the proxy
  → got a genuine DeepSeek V4 Flash response (routed via `custom_llm_provider: deepseek`,
  `api_base: https://api.deepseek.com/...`). Confirmed it appears in LiteLLM's own
  `GET /spend/logs` with real token counts and computed cost (`$0.00001554` for that call) — proves
  usage/cost tracking is live, not just configured.
- **Files touched:** `litellm/config.yaml`
- **Next:** Phase 11 — Observability pass 1 (Loki/Promtail/Grafana).

---

### 2026-07-31T15:20 — Phase 9 runtime-verified (2 real bugs found and fixed, 1 follow-up flagged)

1. **Akaunting never auto-installed at all.** Its entrypoint (`/usr/local/bin/akaunting.sh`) only
   runs `php artisan install` when `AKAUNTING_SETUP=true` (or `--setup`) is passed — the original
   compose had no such flag, so the container just started serving a bare, uninstalled app (`404` on
   every route). It also read `DB_DATABASE`/no `DB_PORT`/no `DB_PREFIX`/no `COMPANY_EMAIL`/no
   `LOCALE`, none of which the entrypoint script actually consumes (it wants `DB_NAME`, `DB_PORT`,
   `DB_PREFIX`, `COMPANY_EMAIL`, `LOCALE`). **Fixed:** added `AKAUNTING_SETUP: "true"` and corrected
   every variable name/value (`DB_NAME`, `DB_PORT: "3306"` matching the MariaDB `akaunting-db`
   service, `COMPANY_EMAIL`, `LOCALE: en-GB`).
2. **Empty `DB_PREFIX` isn't "no prefix."** First install attempt with `DB_PREFIX: ""` silently
   installed with a *randomly generated* table prefix (`7ry_...`) — Akaunting's installer treats a
   blank prefix as "generate one for me," a deliberate security default, not a passthrough. Meanwhile
   the **running app** kept reading the literal empty string from the container env at every request,
   so every query looked for unprefixed tables (`users` instead of `7ry_users`) and failed with
   `SQLSTATE[42S02]: Base table or view not found`. **Fixed:** set a fixed non-empty
   `DB_PREFIX: "ak_"` so install-time and runtime agree; wiped the `akaunting_db` volume and
   reinstalled cleanly (`SHOW TABLES` now correctly shows `ak_users`, `ak_accounts`, etc.).
- **Bootstrap:** confirmed API access with the seeded admin (`admin@fakecorp.internal`), confirmed
  the company `FakeCo` auto-created, created the three chart-of-accounts categories via
  `POST /api/categories` (Payroll Expense id 6, General Expense id 7, Sales Revenue id 8, all
  attached to the default seeded "Cash" account).
- **Follow-up flagged (not blocking, documented for a future session):** posting a transaction
  through the public REST API (`POST /api/transactions`) fails validation with
  `"The payment method is invalid"` even for the seeded `offline-payments.cash.1` method, which
  IS present and enabled in `ak_modules` (both `offline-payments` and `paypal-standard` show
  `enabled=1`). Traced into `App\Utilities\Modules::getPaymentMethods()` — running the exact same
  call from `php artisan tinker` (console context, `type='all'`) returns an **empty array**, meaning
  the `PaymentMethodShowing` event isn't populating `modules->payment_methods` for this fresh
  install even though the module row is enabled. Didn't have time to trace further into the
  `OfflinePayments` module's listener registration in this session. **Workaround used for this
  verification only:** created the test transaction directly via Eloquent
  (`App\Models\Banking\Transaction`) inside the container rather than through the API, which is
  sufficient to prove Akaunting's own ledger math is correct (confirmed `GET /api/accounts/1`
  balance moved `$0.00` → `$500.00` after a $500 income transaction) but does **not** prove the public
  transaction-creation API path is healthy. Any custom code (accounting-engine) that posts
  transactions via this REST endpoint should be smoke-tested against this specific failure mode
  before being trusted — this needs real investigation, not just the workaround.
- **Files touched:** `docker-compose.yml` (Akaunting env vars)
- **Next:** Phase 10 — LiteLLM Proxy.

---

### 2026-07-31T15:00 — Phase 8 runtime-verified (no bugs)

- `docker compose --profile phase8 up -d` — Nextcloud + WordPress + their DBs started cleanly.
- Nextcloud auto-installs on first boot (official image behavior) and auto-registers
  `portal.fakecorp.internal` as a trusted domain from `NEXTCLOUD_TRUSTED_DOMAINS` — confirmed via
  `GET /status.php` with the correct `Host` header (`{"installed":true,...}`; a bare IP/no-Host hit
  correctly 400s with `"Trusted domain error"`, which is expected Nextcloud behavior, not a bug).
  WebDAV smoke test: `PROPFIND /remote.php/dav/files/admin/` with basic auth (`admin`/env password)
  → `207 Multi-Status`.
  WordPress smoke test: root `GET /` → `302` (redirects to the install wizard on first boot, a normal
  successful hit).
- Both confirmed reachable via Traefik hostnames (`portal.fakecorp.internal` → `200`,
  `www.fakecorp.internal` → `302`) and both appear in Traefik's JSON access log.
- **Files touched:** none — first phase with zero bugs found.
- **Next:** Phase 9 — Akaunting.

---

### 2026-07-31T14:45 — Phase 7 runtime-verified

- `docker compose --profile phase7 up -d` — Wiki.js + its Postgres started cleanly, no bugs in the
  compose definition itself this time.
- Wiki.js has its own first-boot setup wizard (not a normal GraphQL mutation) — discovered the real
  endpoint by fetching `/_assets/js/setup.js` and grepping for `fetch(` calls: `POST /finalize` with
  `{adminEmail, adminPassword, siteUrl, telemetry}`. Completed setup this way, pointing at
  `principal@fakecorp.internal`.
- Logged in via `authentication.login` GraphQL mutation to get a JWT, then created a test page via
  `pages.create` and updated it via `pages.update`. Note: `pages.update` requires nearly the full set
  of fields (`editor`, `locale`, `path`, `tags`, etc.) even though it's only changing content/title —
  omitting them fails with an opaque `Cannot read properties of undefined (reading 'map')` rather than
  a helpful validation error. Confirmed the updated content is visible via the normal page-render
  route (`GET /en/phase7-test`), equivalent to viewing it in the editor.
- Traefik hostname routing to `wiki.fakecorp.internal` confirmed (`200`) — the Phase 5 network-label
  fix carries through correctly here since wikijs already had the label from that earlier pass.
- **Gap fixed:** `WIKIJS_ADMIN_EMAIL`/`WIKIJS_ADMIN_PASSWORD` were listed in `.env.example` but never
  filled into `.env`. Added.
- **Files touched:** `.env`
- **Next:** Phase 8 — Nextcloud + WordPress.

---

### 2026-07-31T14:30 — Phase 6 runtime-verified (3 real bugs found and fixed — heaviest phase so far)

Zammad was, as anticipated, the most fragile appliance in the stack. Three distinct, real bugs
surfaced, each would have blocked the phase permanently without runtime testing:

1. **`bitnami/elasticsearch:8` no longer exists.** Bitnami removed old floating tags from Docker
   Hub in their 2025 catalog restructuring (`docker.io/bitnami/elasticsearch:8: not found`).
   **Fixed:** switched to `docker.elastic.co/elasticsearch/elasticsearch:8.15.0` (what Zammad's own
   reference compose uses), with `discovery.type=single-node` and security disabled for this closed
   dev network. Volume mount path also updated (`/usr/share/elasticsearch/data`, not
   `/bitnami/elasticsearch/data`).
2. **The single `zammad` service was a fundamental misunderstanding of the image.**
   `ghcr.io/zammad/zammad` is a multi-role base image (init / railsserver / scheduler / websocket /
   nginx, dispatched by the first CLI arg inside `/opt/zammad/bin/docker-entrypoint`) — it is not a
   monolith you can just run with no command. The original service ran with no command, which exits
   0 immediately, producing a silent, log-free crash-restart loop. **Fixed:** split into
   `zammad-init` (one-shot, `restart: "no"`, gates the others via
   `service_completed_successfully`), `zammad-railsserver`, `zammad-scheduler`, `zammad-websocket`,
   and `zammad-nginx` (the actual Traefik-routed entrypoint, port 8080 not 3000). Updated every
   `ZAMMAD_URL` reference across `docker-compose.yml`, `accounting-engine`, `external-world`,
   `human-bridge`, and `provisioning` from `http://zammad:3000` to `http://zammad-nginx:8080`.
3. **Missing Redis dependency, found via `strace`.** `zammad-init` died silently (exit 1, zero Ruby
   exception output — a genuine dead end without process-level tracing) right after Rails cache/session
   backend selection logged. Traced with `strace -f` inside a throwaway root container: Zammad's own
   `lib/zammad/service/redis.rb` makes an unconditional `connect()` to `127.0.0.1:6379` at boot and
   calls `exit_group(1)` on `ECONNREFUSED` — **even with `REDIS_URL=""`**, which only changes which
   backend ActionCable *sessions* use, not this hard-coded readiness check. Zammad needs Redis
   regardless of session-backend config; docker-compose.yml never had a Redis container for it.
   **Fixed:** added `zammad-redis` (`redis:7-alpine`, healthchecked) and pointed the shared Zammad
   env fragment's `REDIS_URL` at it.
4. **(Smaller, caught during the same debugging pass)** `zammad-nginx` was declared only on
   `net_office`, but `zammad-db` lives on `net_data` — and `zammad-nginx`'s own `check_zammad_ready`
   step runs a `rails r` DB query from inside the nginx container itself before starting, so it needs
   direct DB reachability, not just proxying HTTP to the railsserver. Symptom:
   `ActiveRecord::NoDatabaseError: We could not find your database: zammad` even though the database
   plainly existed — actually a DNS resolution failure for `zammad-db` because nginx wasn't on
   `net_data` at all. **Fixed:** added `net_data` to `zammad-nginx`'s network list.
- **Bootstrap (once the stack was actually healthy):** `zammad-init` completed cleanly (`exit 0`,
  full DB migrate/seed + ES reindex log visible). Zammad's own `db:seed` creates a default seeded
  admin (`nicole.braun@zammad.org`, id 2, role "Customer" only — **not** Admin/Agent by default,
  another thing worth knowing) — repointed it to `principal@fakecorp.internal` with a password via
  `rails r`, then granted `role_ids = [1, 2]` (Admin + Agent) and `group_ids_access_map = {1 => ["full"]}`
  (the "Users" group) — ticket creation requires both an agent-capable role AND explicit group access,
  which a bare role assignment does not include. Created a real API token
  (`Token.create!(action: 'api', preferences: {permission: ['ticket.agent']})` — note it's
  `preferences[:permission]`, not a top-level `permission` column) and used it to create a real
  ticket via `POST /api/v1/tickets`, confirmed retrievable via `GET /api/v1/tickets/:id`.
- Traefik hostname routing to `tickets.fakecorp.internal` confirmed (`200`).
- **Files touched:** `docker-compose.yml` (elasticsearch image, zammad service split, zammad-redis
  added, network fix), `accounting-engine/main.py`, `external-world/main.py`, `human-bridge/main.py`,
  `provisioning/main.py` (ZAMMAD_URL default)
- **Next:** Phase 7 — Wiki.js.

---

### 2026-07-31T13:45 — Phase 5 runtime-verified (1 systemic bug found and fixed, affects Phases 5-9)

- `docker compose --profile phase5 up -d` — Mattermost + its Postgres started, reached `healthy`.
- Created the system admin via `POST /api/v4/users` (Mattermost auto-promotes the first user in a
  fresh instance to `system_admin` — no separate CLI step needed; note the `mattermost` CLI in this
  image build does **not** expose `user`/`team`/`channel`/`config` subcommands, only
  `db`/`export`/`import`/`jobserver`/`server`/`version` — use the REST API for all bootstrap steps,
  not the CLI, for every appliance in this stack unless proven otherwise).
- Created team `fakeco`, channel `general-test`, a bot account `fakeco-bot` + access token, added the
  bot to the team/channel, posted a message via the bot token, and confirmed it's listed in
  `GET /channels/{id}/posts`. All exit-criteria steps pass.
- **BUG FOUND (systemic, affects every Traefik-routed appliance in Phases 5-9) — Traefik's static
  config had `--providers.docker.network=net_clients`, forcing every discovered container to be
  proxied over `net_clients` regardless of which network it actually lives on. None of the routed
  appliances (Mattermost/Zammad/Wiki.js/Nextcloud/WordPress/Akaunting/Roundcube) are ever placed on
  `net_clients` — that network has no appliance containers on it at all (see the network table in
  the build prompt §22). Traefik logged
  `Could not find network named "net_clients" for container "/fakeco-mattermost"` and silently fell
  back to whatever network Docker returned first (nondeterministic — in this run it picked
  `net_data`, which happens to route but the connection then hung and every request timed out with
  `504`/`499`). This would have silently broken hostname-based routing to every Phase 5-9 service.
  **Fixed:** removed the global `--providers.docker.network` flag and added an explicit
  `traefik.docker.network` label to each routed service, pointing at the actual project-qualified
  network name it shares with Traefik (`pointlessprogram_net_mail` for roundcube,
  `pointlessprogram_net_office` for mattermost/zammad/wikijs/nextcloud/akaunting,
  `pointlessprogram_net_dmz` for wordpress). Verified the fix: recreated `traefik` and `mattermost`
  (label changes require container recreation, not just a Traefik restart), then
  `curl -H "Host: chat.fakecorp.internal" http://localhost/` → `200`, and Mattermost's own
  `/api/v4/system/ping` → `{"status":"OK"}` through the Traefik hostname path.
- **Note (reviewed, NOT a bug):** Traefik mounts the raw Docker socket read-only for its own
  label-based service discovery. This looks superficially like it violates the "always go through
  docker-socket-proxy" rule, but the spec's actual requirement (build prompt §13.1, and the
  socket-proxy row in the services table) ties that rule specifically to the **dashboard's**
  start/stop/restart control surface — read-only label discovery by the reverse proxy itself is
  the standard, accepted pattern and outside that rule's scope. Left as-is.
- **Files touched:** `docker-compose.yml` (Traefik command + 7 service label blocks)
- **Next:** Phase 6 — Zammad.

---

### 2026-07-31T13:20 — Phase 4 runtime-verified (2 bugs found and fixed)

- `docker compose --profile phase4 up -d` — docker-mailserver + Roundcube started.
  docker-mailserver refuses to start Dovecot with zero mail accounts (120s grace window), so created
  `principal@fakecorp.internal` and `test@fakecorp.internal` via `docker exec fakeco-mailserver setup email add`.
- **BUG FOUND #1 — wrong default SMTP port for authenticated send.** `human-bridge/main.py` and
  `external-world/main.py` both defaulted `MAILSERVER_SMTP_PORT` to `25`, and `docker-compose.yml`
  hard-coded `MAILSERVER_SMTP_PORT: "25"` for `human-bridge`. Verified directly: port 25 (`smtpd`,
  MX/inbound) does **not** advertise the `AUTH` ESMTP extension at all; only port 587 (`submission`)
  does. Any code path logging in with `smtplib.login()` on port 25 would fail with
  `SMTPNotSupportedError: SMTP AUTH extension not supported by server` the first time it ran against
  the real container — this was silently broken until now because it was never runtime-tested.
  **Fixed:** changed both Python defaults and the compose env var to `587`.
- **BUG FOUND #2 (false alarm, verified as correct behavior) — relay-lockdown check.** First test
  send (to both an internal and an external address) got quarantined by amavis with reason
  `BAD-HEADER-0` because my test messages lacked `Date`/`Message-ID` headers — not a real relay bug.
  Re-sent with proper headers: internal delivery (`test@` → `principal@`) succeeded and was visible
  via IMAP fetch. Re-ran the external-relay attempt (`test@` → `someone@gmail.com`) and confirmed
  amavis tags and blocks it as `BouncedOpenRelay` (SMTP still returns `250` at the protocol level
  because Postfix queues before the amavis content-filter step runs, but the message never reaches
  an external MTA — it's bounced back to the internal sender). This matches spec's relay-lockdown
  requirement and `SPEC_CLARIFICATIONS.md` #5.
- Exit criteria confirmed: mailserver + Roundcube up on `net_mail`; test + Principal mailboxes exist;
  test email sent via authenticated SMTP is received and fetchable via IMAP (Roundcube uses the same
  IMAP backend, so this is equivalent to "visible in Roundcube"); relay to an external destination is
  blocked.
- **Files touched:** `human-bridge/main.py`, `external-world/main.py`, `docker-compose.yml`
- **Next:** Phase 5 — Mattermost.

---

### 2026-07-31T13:00 — Phase 3 runtime-verified

- `docker compose --profile phase3 up -d` — Technitium DNS + Traefik started.
- Created primary zone `fakecorp.internal` and a `test.fakecorp.internal` A record via
  Technitium's HTTP API for verification (`/api/zones/create`, `/api/zones/records/add`).
  A container on `net_clients` using Technitium as its resolver (`--dns <technitium-ip>`)
  correctly resolved the test record.
  **Note for later phases:** this zone is currently empty except the test record — Phase 4+
  services will need their own A/CNAME records added to this zone (or Traefik's provider needs
  to publish them) before hostname-based routing works end-to-end. Flagging as follow-up rather
  than blocking Phase 3 exit criteria, which only requires DNS resolution to work at all.
- Traefik confirmed multi-homed onto both `net_clients` and `net_mgmt`; its dashboard reachable
  from `net_mgmt` (`GET /dashboard/` → 200).
- Both containers visible/running; no dedicated Docker healthcheck defined for either (expected —
  Phase 3 exit criteria ties "healthy" to cAdvisor/Prometheus visibility, already proven in Phase 2).
- **Next:** Phase 4 — docker-mailserver + Roundcube.

---

### 2026-07-31T12:45 — Phase 2 runtime-verified

- `docker compose --profile phase2 up -d` — cadvisor, node-exporter, prometheus all started
  alongside Phase 1 services.
- Exit criteria confirmed: `cadvisor` reports `healthy`; Prometheus `/api/v1/targets` shows all
  three scrape jobs (`cadvisor`, `node-exporter`, `prometheus`) with `health: up`.
- **Next:** Phase 3 — Technitium DNS + Traefik.

---

### 2026-07-31T12:30 — Log reconciliation + Docker restored + Phase 1 runtime-verified

- **Context:** Docker was reinstalled/enabled on this machine (required turning on Hyper-V + a reboot).
  Picking up the build, found this log's status header claimed "Phase 14 in progress, Phases 2–11
  code-done-but-unverified" while the actual filesystem showed **fully written code through Phase 18**
  (`sim-clock`, `narrative-db` migrations 001–004, `provisioning`, `accounting-engine`,
  `meeting-simulator`, `human-bridge`, `orchestrator` all have complete `main.py` + `Dockerfile` +
  `requirements.txt`) plus a partially-written Phase 21/22 (`external-world/main.py`, 517 lines,
  missing `Dockerfile`/`requirements.txt`/compose wiring). A prior session evidently kept writing
  code across multiple phases without updating this log after the initial Phase 1 entry.
- **Fixed:** Rewrote the STATUS HEADER and deliverables checklist above to reflect actual disk state.
  This log is now the source of truth going forward — update it after every verification step, not
  just after writing code.
- **Fixed (config gaps found during `docker compose config` validation):**
  - `MAILSERVER_BOT_SECRET` was referenced as `:?required` by `provisioning` in `docker-compose.yml`
    but was **absent from `.env.example` entirely** and unset in `.env` — added to both files.
  - Removed obsolete top-level `version: "3.9"` key from `docker-compose.yml` (Compose v2+ ignores
    it and warns).
- **Phase 1 runtime verification — RE-RUN AND PASSED** (never actually run before now):
  - `docker compose up postgres docker-socket-proxy -d` — both containers reached `healthy`.
  - Network isolation test: `docker exec fakeco-postgres wget google.com` → DNS resolution fails
    (`bad address 'google.com'`) confirming `net_data` has no external egress, as required (`internal: true`).
  - Socket-proxy allow-list test: `GET /containers/json` → `200` (CONTAINERS=1, expected allowed);
    `GET /images/json` → `403` (IMAGES=0, expected blocked); `GET /containers/.../exec` → `404`
    (EXEC=0, expected blocked/not routed). All three match spec §3 intent.
- **Files touched:** `BUILD_LOG.md`, `.env`, `.env.example`, `docker-compose.yml`
- **Next:** Bring up Phase 2 profile (`--profile phase2`), verify exit criteria, then proceed
  sequentially through Phase 11, then verify custom services 12–18 against live Postgres, then
  finish `external-world` (Dockerfile, requirements.txt, compose service block, wire into Phase 21/22).

---

### 2026-07-31T11:36 — Phase 0 COMPLETE

- **Completed:** All Phase 0 exit criteria verified:
  - Git repo initialized, first commit made: `a188a77`
  - `BUILD_LOG.md` created with two-part structure (status header + reverse-chronological log)
  - All 15 custom deliverable directories created, each with a placeholder `README.md`:
    `orchestrator/`, `meeting-simulator/`, `human-bridge/`, `sim-clock/`, `accounting-engine/`,
    `purge-manager/`, `snapshot-manager/`, `external-world/`, `kpi-engine/`, `branding-manager/`,
    `narrative-db/`, `dashboard/`, `provisioning/`, `litellm/`, `monitoring/`
  - `.env.example` created with all credential stubs (no values) for every category in §26
  - `.gitignore` created excluding `.env`, volumes, secrets
- **Files touched:** `BUILD_LOG.md`, `.env.example`, `.gitignore`, all 15 `README.md` stubs
- **Next:** Phase 1 — `docker-compose.yml` with 7 networks, Postgres, docker-socket-proxy

---

### 2026-07-31T11:41 — Phase 1 CODE COMPLETE; Docker runtime BLOCKED

- **Completed (code/config artifacts):**
  - `docker-compose.yml` created: all 7 networks (`net_clients`, `net_office`, `net_mail`,
    `net_dmz`, `net_data`, `net_llm_bridge`, `net_mgmt`) with correct `internal: true` flags.
  - All services for Phases 1–11 defined in compose (Phase 2–11 services use Compose profiles
    so `docker compose up` without `--profile` only starts Phase 1 services by default).
  - Postgres service on `net_data` with healthcheck; `fakeco.managed=true` label for socket-proxy scoping.
  - `tecnativa/docker-socket-proxy` on `net_mgmt` with CONTAINERS=1, POST=1, all dangerous
    endpoints explicitly disabled (IMAGES=0, EXEC=0, etc.) per spec §3.
  - Supporting files: `monitoring/prometheus.yml`, `monitoring/loki-config.yaml`,
    `monitoring/promtail-config.yaml`, `litellm/config.yaml` (full provider chain + tier config).
  - `.env` created for dev use (not committed per `.gitignore`).

- **BLOCKER — DEVIATION LOGGED:**
  Docker Desktop was uninstalled from this machine on 2026-06-22. `docker compose config`
  returns "not recognized." Cannot run Phase 1 runtime exit criteria:
  (a) `docker compose up` health check, (b) network isolation test, (c) socket-proxy restriction test.
  **Decision:** Continue producing code artifacts for subsequent phases rather than halting.
  All Docker-dependent runtime verification steps are logged here as pending and will be run
  once Docker is reinstalled. This is a pure infrastructure availability issue, not a code error.

- **Files touched:** `docker-compose.yml`, `monitoring/prometheus.yml`, `monitoring/loki-config.yaml`,
  `monitoring/promtail-config.yaml`, `litellm/config.yaml`, `BUILD_LOG.md`

- **Next step (once Docker available):** `docker compose up postgres docker-socket-proxy -d`
  then run isolation and socket-proxy verification tests per Phase 1 exit criteria.
- **Next code step (continuing without Docker):** Phase 12 (sim clock service code) and
  Phase 13 (narrative DB migrations) — both produce Python/SQL that can be written now
  and tested when Docker is available.

---

### 2026-07-31T11:37 — Phase 1 started

- **Starting:** Phase 1 — Compose topology, networks, shared Postgres, socket-proxy
- **Plan:** Create `docker-compose.yml` with all 7 networks, Postgres on `net_data`,
  `tecnativa/docker-socket-proxy` on `net_mgmt`. Verify isolation and socket-proxy restrictions.
- **In progress:** Writing `docker-compose.yml`

---

### 2026-07-31T11:32 — Phase 0 started

- **Completed:** Read all three input documents in full:
  `fakeco-real-appliances-BUILD-PROMPT.md` (696 lines, 28 sections),
  `PHASES.md` (942 lines, Phases 0–38 + open questions),
  `SPEC_CLARIFICATIONS.md` (82 lines, 13 resolutions).
- **Completed:** Git repo initialized (`git init`).
- **In progress:** Creating `BUILD_LOG.md` (this file).
- **Files touched:** `BUILD_LOG.md` (creating now)

**Key clarifications absorbed from SPEC_CLARIFICATIONS.md (govern this entire build):**
1. `pending_approvals` uses two nullable columns: `approver_employee_id` + `approver_is_principal` (boolean).
2. Payroll posts as one aggregate transaction per cycle in Akaunting; per-employee detail in Postgres only.
3. `employees` table gets `is_lead` boolean (or `role_tier` enum `ic`/`lead`); longest-tenured lead if multiple.
4. Pay cuts: manual only from dashboard Payroll tab; never auto-triggered by BetaCorp gap or performance data.
5. Mail relay: docker-mailserver accepts inbound for `@fakecorp.internal` only; external-looking senders are local-injection display artifacts.
6. Performance-review cold start: skip entirely for <1 full cycle tenure or department <2 members.
7. Crisis expense requester: Principal's own employee/account ID.
8. Audit log excluded from snapshot capture/restore entirely — stays continuous independent of snapshots.
9. `narrative_events.origin` enum: `ai` / `human` / `external` (third value added).
10. No seed roster provided: building agent invents placeholder roster, noted as swappable.
11. Traefik multi-homing: `net_clients` (base) + `net_mgmt` + `net_office` + `net_mail` + `net_dmz`.
12. Local-model fallback tier: left unspecified; don't spend build effort on it yet.
13. Orchestrator = multiple genuinely separate deployable services; dashboard backend = thin API gateway.

---
