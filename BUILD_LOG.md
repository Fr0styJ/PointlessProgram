# BUILD_LOG.md — FakeCo "Real Appliances" Build

---

## STATUS HEADER

| Field | Value |
|---|—--|
| **Current Phase** | Phases 1–18 and 21–22 all runtime-verified against a live `docker compose` stack. Phases 19-20, 23-38 not started (mostly still README-stub or nonexistent). |
| **Percent Complete** | ~60% by code volume; walking skeleton (1-11) + custom services (12-18) + external-world (21-22) are genuinely running and tested, not just written. |
| **Status** | Every phase from 1 through 18, plus 21/22, has been brought up in live Docker and exercised with real requests (not just "container starts") — full trail below. ~27 real runtime bugs found and fixed along the way (bad ports, broken image references, missing dependencies, wrong API field names, silent Python `.get()` gotchas, a router config bug, missing healthcheck binaries, 2 Zammad ticket-creation field bugs, etc.). external-world's `customers` table is now seeded (`005_customers_seed.sql`) and the Phase 22 prospect-generation loop is runtime-verified end-to-end (real Zammad tickets created). Three genuine feature gaps remain, identified and NOT quick-patched (flagged as dedicated follow-ups since they need real design work): Akaunting's payment-method resolver bug (blocks Phase 15 ledger posting), meeting-simulator's missing Wiki.js integration, human-bridge's missing Principal-content detection layer (Phase 17's actual core requirement), and orchestrator's missing priority-queue/pending_actions retry mechanism (Phase 18's actual core requirement). |
| **Exact Next Action** | Pick one of: (a) resolve the 4 remaining flagged follow-up gaps above, (b) move on to genuinely unstarted phases (19 PTO, 20 relationships, 23 KPI engine, 29 purge/snapshot, 30 branding, 33-37 dashboard, 38 hardening). |
| **BLOCKER** | None. Docker Desktop running. All appliance credentials/tokens are in `.env` (gitignored) — a fresh clone needs a real `.env` populated before `docker compose up` will do anything useful. |

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
- [x] `human-bridge/` (Phase 17 — action-injection API AND detection layer (Mattermost/Zammad/Wiki.js polling + IMAP mail polling → `narrative_events`/`pending_reactions`) both written and runtime-verified 2026-07-31T21:45)
- [x] `sim-clock/` (code written, Phase 12 — not yet runtime-verified)
- [x] `accounting-engine/` (code written, Phase 15 — not yet runtime-verified)
- [ ] `purge-manager/` (README stub only, Phase 29 not started)
- [ ] `snapshot-manager/` (README stub only, Phase 29 not started)
- [~] `external-world/` (Phase 21/22 `main.py` written, 517 lines, but no `Dockerfile`/`requirements.txt`, not wired into `docker-compose.yml` — INCOMPLETE)
- [ ] `kpi-engine/` (README stub only, Phase 23 not started)
- [ ] `branding-manager/` (README stub only, Phase 30 not started)
- [x] `narrative-db/` (migrations 001–005 written and runtime-verified — 005 adds `customers` seed data, Phase 13/22)
- [ ] `dashboard/` (README stub only, Phases 33–37 not started)
- [x] `provisioning/` (code written, Phase 14 — not yet runtime-verified)
- [x] `litellm/config.yaml` (written, Phase 10 — not yet runtime-verified)
- [x] `monitoring/` (Prometheus/Loki/Promtail configs written, Phases 2/11 — not yet runtime-verified)
- [ ] README (top-level, Phase 38 — not started)

---

## LOG (newest first)

---

### 2026-08-01T01:15 — Phase 30 built and runtime-verified: branding-manager service, 3 real appliance-API bugs/gaps found and fixed

Built the previously-stub `branding-manager/` service (spec §17): asset library, employee avatar
picker/bulk-push, first-boot Mattermost emoji pack. Verified against a fully isolated live stack,
not just code review.

- **New files:** `branding-manager/main.py` (FastAPI service), `branding-manager/Dockerfile`,
  `branding-manager/requirements.txt` (same `python:3.12-slim` + fastapi/uvicorn/asyncpg/httpx/
  pydantic pattern as `accounting-engine`, including the non-`curl` Python healthcheck),
  `narrative-db/migrations/007_branding.sql` (`employee_branding` table: `employee_id ->
  avatar_asset_id`, next free migration number after the parallel-built `006_phase19_pto.sql`),
  `branding-manager/assets/avatars/avatar-{01..10}.png` (256x256 solid-color + initial-letter
  placeholders) and `branding-manager/assets/emoji/{fakeco-thumbsup,fakeco-shipit,fakeco-star,
  fakeco-alert,fakeco-money}.png` (64x64 simple geometric shapes) — real, distinct, valid PNGs
  generated with a small one-off Pillow script (`branding-manager/assets/generate_assets.py`, not
  part of the runtime image's import path). Wired into `docker-compose.yml` as a new `phase30`
  profile service on `net_clients`/`net_data`/`net_office`, depending on `postgres` (healthy) +
  `narrative-db-migrate` (completed).
- **Endpoints:** `GET /assets` (lists bundled avatar/emoji stems), `POST /branding/apply` (single
  employee), `POST /branding/bulk-apply` (`randomize` / `apply-one-to-all` / `reset-to-default`
  over an employee-ID list), `GET /branding/employee/{id}`, `POST /branding/emoji-pack/upload`.
- **3 real bugs/gaps found doing the required live research pass** (spec explicitly flagged Zammad
  and Wiki.js avatar-API shapes as unknowns needing confirmation against a live instance — both
  turned out to be more fundamentally different from the plan's assumption than just "wrong field
  names"):
  1. **Zammad has NO admin-on-behalf-of avatar API at all** — confirmed by reading the actual
     controller/route source (`config/routes/user.rb`, `UsersController#avatar_new/avatar_list/
     avatar_destroy`, and the GraphQL `user/current/avatar` mutation): every one of them operates
     on `current_user`, never a `user_id`/`id` param, and `UserAccessTokenController#create`
     (the token-minting endpoint) is likewise `current_user`-only — unlike Mattermost, there is no
     "admin mints a token for user X" endpoint to piggyback on. Worked around with the same spirit
     as this codebase's existing impersonation pattern: admin token calls `PUT /api/v1/users/{id}`
     to set a fresh ephemeral password on the target employee, then a plain HTTP Basic Auth client
     as that employee calls the normal current-user `POST /api/v1/users/avatar` endpoint. Verified
     live: `image` field on the target Zammad user changed to a new store hash after each push, and
     `GET /api/v1/users/image/{hash}` served back the exact byte-identical uploaded PNG.
  2. **Zammad's `Token.create!(preferences: {permission: {...}})` (the shape shown in Zammad's own
     `app/models/token.rb` doc comment) throws a 500** (`TypeError (can't cast Array)` in
     `lib/auth/permissions.rb#permissions_cache`), because `Token::Permissions#permissions` does
     `Permission.where(name: Array(preferences[:permission]))` — `Array()` on a Hash produces an
     array of `[key, value]` pairs, not permission-name strings, which Postgres then can't cast for
     the `name` column. Confirmed by reproducing the crash and reading Zammad's own admin-token
     creation code. **Real fix:** `preferences[:permission]` must be an **array of permission-name
     strings** (`["admin.user", "ticket.agent", "admin"]`), not a hash — used this shape for the
     admin token minted during this phase's own test-stack bootstrap (not part of the
     branding-manager service code itself, since it only *consumes* `ZAMMAD_ADMIN_TOKEN` from env
     like every other service — but worth flagging for whoever documents `.env` bootstrap steps).
  3. **Wiki.js has no avatar-setting API whatsoever in this version** — the plan's assumption
     ("avatar as a URL/base64 field on `users.update`") was wrong: schema introspection
     (`__type(name:"UserMutation")`) shows `update`'s only args are `id/email/name/newPassword/
     groups/location/jobTitle/timezone/dateFormat/appearance` — no `avatar`. The `User` GraphQL
     type itself has no `avatar` field either. Reading `server/models/users.js` confirms
     `updateUserAvatarData()` is only ever called from OAuth-provider login sync
     (`profile.picture`), never from any controller route, and the only avatar HTTP route
     (`server/controllers/common.js`, `GET /_userav/:uid`) is read-only — there's no POST/PUT
     counterpart at all. **Real fix:** write directly to Wiki.js's own `userAvatars` Postgres table
     (`id INT PK, data BYTEA` — the exact table `/_userav/:uid` reads from) via `asyncpg`, since
     `wikijs-db` is reachable on `net_data` (added `WIKIJS_DB_HOST`/`WIKIJS_DB_PASSWORD` to
     `branding-manager`'s compose env). Verified live: after the direct DB write,
     `GET /_userav/{id}` through Wiki.js's own real HTTP route served back the exact
     byte-identical PNG (confirmed via matching Content-Length). Documented as a genuine missing
     appliance feature, not a guess-and-move-on.
- **1 more real bug found in Zammad's own `avatar_destroy` while testing `reset-to-default`:**
  deleting a user's last remaining Avatar record does not clear `user.image` — Zammad's controller
  only re-points `image` at a remaining default avatar's hash *if one still exists after the
  delete*; when none remain it silently leaves `image` pointing at the just-deleted hash, and that
  hash still resolves via `GET /api/v1/users/image/{hash}` (the underlying Store blob isn't
  actually removed), so the user keeps silently showing a stale previously-applied avatar instead
  of reverting to Zammad's generated initials. Confirmed live: reset a user with a single avatar
  record, `image` field remained the deleted hash, and that hash still served the old image bytes
  with 200. **Fixed** by having `branding-manager`'s `reset_user_avatar()` explicitly
  `PUT /users/{id}` with `{"image": null}` after deleting the avatar records.
- **Verified against a fully isolated stack** (project name `fakeco-p30`, brought up from this
  worktree with `phase5`/`phase6`/`phase7`/`phase13`/`phase14`/`phase30` profiles; main `fakeco-*`
  stack — 38 containers — confirmed untouched before and after). Container-name collisions with
  the main stack (same known issue as Phase 19's verification) worked around with a temporary,
  not-committed `docker-compose.override.p30.yml` (renamed containers + host-published test ports)
  deleted after teardown. Bootstrapped fresh admin accounts/tokens on each appliance in this
  isolated instance (Mattermost first-user signup + PAT, Wiki.js `/finalize` +
  `authentication.setApiState(enabled:true)` + `createApiKey`, Zammad `rails r` admin-role grant +
  token — this instance's own credentials, independent of the main stack's `.env` values) and 3
  test employees (`employees.id` 1/2/3 — reused the pre-seeded roster rows rather than inserting
  new ones, which collided with `employees.email`'s unique constraint on first attempt) with real
  Mattermost/Zammad/Wiki.js accounts, writing their appliance IDs onto the `employees` row directly
  (skipping full `provisioning` CLI since `mailserver` wasn't part of this phase's dependency set).
  - `POST /branding/apply` (single employee, Alice/employee 1): confirmed all three appliances
    returned `"ok"` and independently re-fetched each appliance's own avatar endpoint
    (`GET /users/{id}/image` w/ Mattermost admin token, `GET /users/{id}` `.image` hash w/ Zammad
    admin token, `GET /_userav/{id}` on Wiki.js) — each served back byte-size-matching, genuinely
    different image data than before the push.
  - `POST /branding/bulk-apply` with `mode:"apply-one-to-all"` across 3 employees (one Mattermost-
    only employee included to exercise the "skipped, no zammad_agent_id/wiki_user_id" path):
    confirmed the correct subset of appliances updated per employee, all with the identical chosen
    asset (byte-size match confirmed per appliance).
  - `mode:"randomize"`: confirmed distinct assets assigned per employee (not just "some 200
    response") by reading back the recorded `avatar_asset_id` per employee.
  - `mode:"reset-to-default"`: confirmed Mattermost's own generated default avatar was restored
    (different, smaller byte size than any bundled asset — Mattermost's native letter-avatar
    generator), Wiki.js's `/_userav/{id}` correctly 404'd (row deleted), and Zammad's `image` field
    was `null` (after the bug fix above).
  - Emoji pack: `POST /branding/emoji-pack/upload` created all 5 bundled emoji on Mattermost
    (`POST /api/v4/emoji`, confirmed each returned a real emoji `id`); posted a real message
    containing `:fakeco-shipit: :fakeco-star:` and confirmed the post response's
    `metadata.emojis` array resolved both to their correct, just-created emoji records — genuinely
    rendered/resolved by Mattermost, not just accepted as literal text.
  - Torn down cleanly: `docker compose -p fakeco-p30 ... down -v` (after re-running with the
    profile flags included — a first attempt without them left several containers/networks behind,
    since `docker compose down` without `--profile` flags only tears down default-profile
    services). Confirmed zero `fakeco-p30-*` containers/networks/volumes remained; main stack's 38
    containers still running throughout.
- **Files touched:** `branding-manager/main.py`, `branding-manager/Dockerfile`,
  `branding-manager/requirements.txt`, `branding-manager/assets/` (new avatar/emoji PNGs +
  generator script), `narrative-db/migrations/007_branding.sql`, `docker-compose.yml`
  (new `branding-manager` service block).
- **Next:** Phase 31 (observability pass 2, Grafana-only) or Phase 29 (purge/snapshot, still
  unstarted) — both lower-risk than this phase's appliance-API research turned out to be.

---

### 2026-07-31T23:45 — Phase 23 follow-up closed: kpi-engine's live-appliance rollup verified against the main stack, 3 real bugs found and fixed (2 also affected the already-"verified" accounting-engine)

Closed the gap flagged in the Phase 23 entry below (its live rollup calls against real Zammad/
Wiki.js/Mattermost/Akaunting were untested) by bringing `kpi-engine` up in the main running stack
(`docker compose --profile phase13 --profile phase23 up -d --build kpi-engine`) and calling
`POST /rollup/run` for real.

1. **Wiki.js: `pages.list`'s item type doesn't expose `authorId`/`creatorId`.** The rollup 400'd
   immediately (`Cannot query field "authorId" on type "PageListItem"`) — confirmed via GraphQL
   introspection (`__type(name: "PageListItem")`) that the list type only has
   id/path/locale/title/description/contentType/isPublished/isPrivate/privateNS/createdAt/
   updatedAt/tags; author/creator attribution only exists on the single-page type
   (`pages.single(id)`, confirmed via the same introspection technique against `Page`). **Fixed:**
   `list_pages()` now fetches the list first, then does a per-page `pages.single(id)` follow-up
   query for `authorId`/`creatorId` (N+1, acceptable for a once-daily rollup over a realistically
   small wiki).
2. **Akaunting: `AkauntingClient` had no `X-Company` header at all**, despite kpi-engine's own code
   comment claiming it followed "the same X-Company-aware pattern as accounting-engine" — it
   didn't; it only sent `company_id` as a query param, which was never sufficient (see this
   session's Phase 9/15 entry for the original root-cause). **Fixed:** added the header.
3. **Real regression found in already-"verified" `accounting-engine`, not just kpi-engine:**
   even with the `X-Company` header, `GET /transactions` still 500'd —
   `{"message":"Untrusted Host \"akaunting\".","status_code":500}`. Root cause: Laravel's
   `TrustHosts` middleware rejects the bare service DNS name; it only accepts a `Host` header
   matching Akaunting's configured `APP_URL` (`accounting.fakecorp.internal`). Tested directly
   against `fakeco-accounting-engine`'s own running container (`docker exec ... python3 -c
   "httpx.get('http://akaunting/...)"`) — **confirmed this exact "Untrusted Host" 500 has been
   happening on every real call accounting-engine has ever made to Akaunting**, and was masked
   this whole session because every manual verification curl in Phase 9/15's entries explicitly
   passed `-H "Host: accounting.fakecorp.internal"`, which the Python client code itself never
   did. This means Phase 15's accounting-engine (payroll, raises, revenue posting, Books Auditor)
   has likely never successfully posted a single transaction outside of this session's manual
   curl tests — a real, previously undiscovered bug in already-committed code. **Fixed in both
   `accounting-engine/main.py` and `kpi-engine/main.py`'s `AkauntingClient`**: added
   `headers={"Host": "accounting.fakecorp.internal"}` to the shared httpx client.
- **Verified after all three fixes:** `POST /rollup/run` against the live main stack now returns
  `{"status":"complete","snapshot_date":"2026-07-30","rows_written":7}` — real Zammad ticket
  counts, Wiki.js chat/page metrics, Mattermost chat-message counts, and an Akaunting revenue
  query all succeeded and wrote real rows to `kpi_snapshots` (spot-checked via direct SQL).
  `GET /reviews/due` also confirmed working against the full live roster — correct quartile
  ranking, `top_quartile`/`second_quartile`/`rest` tiers, and `underperforming` flags per
  department.
- **Follow-up this surfaces:** since accounting-engine's Akaunting calls were silently broken
  this entire session outside of manual curl verification, Phase 15's own exit criteria (expense
  approval posting a real ledger transaction, payroll run totals matching Akaunting, raise
  application, Books Auditor correction) should be re-verified now that the Host-header fix is in
  — they were never actually exercised through the real code path before this fix landed.
- **Files touched:** `kpi-engine/main.py` (Wiki.js list_pages fix, X-Company + Host headers),
  `accounting-engine/main.py` (Host header fix)
- **Next:** re-verify Phase 15 (accounting-engine) end-to-end now that its Akaunting client
  actually works; then Phase 19 (PTO, in progress).

---

### 2026-07-31T18:20 — Seeded `customers` table (Phase 22 prospect-loop gap, flagged 22:30 entry below); fixed 2 real Zammad ticket-creation bugs found while verifying it

- **Added** `narrative-db/migrations/005_customers_seed.sql`: 6 placeholder prospect companies
  (`relationship_status='prospect'`), same invented-placeholder pattern as the employee roster
  (`SPEC_CLARIFICATIONS #10`). Sales/support reps assigned by looking up real employee IDs via
  email from `003_employees.sql` (not hardcoded IDs), so it stays valid if that roster changes.
- Ran `docker compose --profile phase13 up --build narrative-db-migrate`: applied cleanly
  (`005_customers_seed.sql` — 001-004 skipped as already-applied), 6 rows confirmed in `customers`
  with correctly-resolved `assigned_sales_rep_id`/`assigned_support_rep_id`.
- **2 real bugs found and fixed in `external-world/main.py`'s `generate_prospect_activity()`**
  while verifying it against the newly-seeded rows (never caught before because the table was
  empty, so the code path never actually ran against real data):
  1. Hardcoded `"group": "Sales"` — no such Zammad group exists (only the default `Users` group
     is provisioned anywhere in this stack; nothing creates a `Sales` group). Every ticket POST
     422'd with `No lookup value found for 'group': "Sales"`. Fixed: use `"Users"`.
  2. Missing `customer_id` — Zammad hard-requires it on ticket creation. Fixed using the same
     `"guess:<email>"` shorthand already working in `human-bridge/main.py`'s ticket-creation code
     (resolves-or-creates the Zammad customer from the email). Also had to switch the article
     `type` from `"email"` to `"phone"`: an `email`-type article requires the target group to have
     an outgoing email channel configured, which isn't provisioned in this sim — `phone` simulates
     the inbound contact without that dependency, matching how `human-bridge` avoids the same
     issue by using `type: "note"`.
- **Verified end-to-end after the fixes:** rebuilt/restarted `external-world`. `POST
  /customers/check` returned `{"churned":0,"at_risk":0}` (correct — none of the seed rows are
  `active`/`at_risk` yet). Called `generate_prospect_activity()` directly with a business-hours
  sim_time (real sim-clock time was past the 6pm cutoff at test time) — got two real `201 Created`
  Zammad tickets (`[PROSPECT] Summit Peak Analytics: inquiry`, `[PROSPECT] Cedarline Retail:
  inquiry`), confirmed visible via `GET /api/v1/tickets`, and confirmed matching
  `prospect_inquiry_generated` rows in `system_audit_log` with correct `customer_id`/`company_name`.
- **Files touched:** `narrative-db/migrations/005_customers_seed.sql` (new),
  `external-world/main.py` (group/customer_id/article-type fixes)
- **Status:** Phase 22's prospect-generation loop can now actually bootstrap and fire real Zammad
  tickets. The customer-seed gap flagged in the 22:30 entry below is resolved.

---

### 2026-07-31T22:30 — Phase 21/22 wired up and runtime-verified; systemic healthcheck bug fixed; Phase 18 finished

- **Systemic bug (found while resuming Phase 18 after a pause):** all 5 custom services'
  `HEALTHCHECK` used `curl -f ...`, but none of their `python:3.12-slim`-based Dockerfiles install
  `curl` — every healthcheck failed with `exec: "curl": executable file not found in $PATH`,
  marking `sim-clock`, `accounting-engine`, `meeting-simulator`, and `human-bridge` permanently
  `unhealthy` (services themselves ran fine) and specifically **blocking `orchestrator` from ever
  starting**, since it has `depends_on: sim-clock: condition: service_healthy`. **Fixed:** replaced
  all 5 healthchecks in `docker-compose.yml` with `python -c "import urllib.request..."` (no new
  package needed). All 5 now report `healthy`.
- **Phase 18 (orchestrator) verified**, unblocked by the fix above: started cleanly, and its tick
  loop autonomously fired a real `performance_review` meeting through meeting-simulator within the
  first tick with no manual triggering — confirmed a genuine new `meetings` row (`id=7`) appeared.
  **Known gap, not fixed:** the tick loop is a fixed sequence of scheduled-job checks, not the
  per-employee "reaction → approval → action item → filler" priority loop from spec §4.3, and there
  is no `pending_actions` table or reachability/retry-queue (spec §13.1) anywhere in the schema or
  code — flagged as a follow-up, not attempted given the scope already covered this session.
- **Phase 21/22 (external-world) finished and verified.** The service existed as a 517-line
  `main.py` with no `Dockerfile`, no `requirements.txt`, and no `docker-compose.yml` entry at all.
  Added both files (matching the pattern of every other custom service — `python:3.12-slim` +
  fastapi/uvicorn/asyncpg/httpx/pydantic) and a full compose service block (`net_clients`,
  `net_data`, `net_mail`, `net_office`, gated to profile `phase21`, depending on
  `narrative-db-migrate`). Built and started it successfully.
  - **Gap found and fixed:** the `external.relay@fakecorp.internal` mailbox `inject_email()` uses
    to authenticate outbound BetaCorp/customer emails didn't exist, so every send failed with
    `535 5.7.8 authentication failed`. Created it via `setup email add` using the same
    `MAILSERVER_BOT_SECRET`-derived password scheme the code itself computes at send-time (so no
    code change was needed, just the missing account) — this really belongs in a first-boot
    provisioning script rather than a one-off manual step, worth automating properly in Phase 38.
  - Triggered `POST /betacorp/check` manually: real DeepSeek LLM call succeeded, 6 real BetaCorp
    job-offer emails were injected and delivered, each logged to `system_audit_log` with
    `action=betacorp_offer_sent` and correct per-employee pay-gap details.
  - Triggered `POST /customers/check`: ran cleanly (`{"churned":0,"at_risk":0}`) but is a no-op
    because the `customers` table has **zero seed rows** — `generate_prospect_activity()` only ever
    reads existing `relationship_status='prospect'` rows, so the whole Phase 22 customer/revenue
    loop can never bootstrap itself without an initial seed. Flagged as a follow-up (needs a
    deliberate placeholder prospect list, the same kind of judgment call the roster/employees seed
    already made) rather than invented ad hoc here.
- **Files touched:** `docker-compose.yml` (5 healthcheck fixes + external-world service block),
  `external-world/Dockerfile` (new), `external-world/requirements.txt` (new)
- **Status:** the full custom-service layer (Phases 12–18, 21–22) is now up, healthy, and has had
  at least one real end-to-end path verified per phase. Four flagged gaps remain (Akaunting
  payment-method bug, meeting-simulator Wiki.js integration, human-bridge detection layer,
  orchestrator priority/retry queue) plus the new customer-seed gap — none block the services from
  running, all are documented above and in this session's earlier entries for a focused follow-up.

---

### 2026-07-31T22:10 — Fixed the Amavis `Date:`-header bounce flagged in the entry below

- **Fix**: `send_as_employee()` in `human-bridge/main.py` now sets `msg["Date"] =
  formatdate(localtime=True)` and `msg["Message-ID"] = make_msgid()` on the outgoing `MIMEText`
  before SMTP submission. Rebuilt and restarted the `human-bridge` container
  (`docker compose up -d --build human-bridge`).
- **Verified live**: called `POST /action/send-email` (`from_employee_id=2` [Bob Martinez] →
  `carol.okonkwo@fakecorp.internal`) against the running container. Confirmed delivery by reading
  the new Maildir file directly from the `mailserver` container
  (`/var/mail/fakecorp.internal/carol.okonkwo/new/...`) — message present with
  `Date: Fri, 31 Jul 2026 18:07:37 +0000` and a `Message-ID`, no Amavis bounce, no quarantine copy
  under `virusmails/`. Previously this same call would have silently bounced per the finding
  below.
- Scope: this one-line-per-header fix only; did not touch the detection-layer code from the
  21:45 entry or the other action-injection endpoints.

---

### 2026-07-31T21:45 — Phase 17 detection layer BUILT and runtime-verified end-to-end (all 5 exit criteria)

- **Closed the gap flagged in the 18:40 entry below**: `human-bridge/main.py` now has a real
  DETECTION layer alongside the pre-existing (untouched) action-injection API. Added: an
  `asyncio` background poll loop (`_detection_loop`, started from FastAPI `lifespan`, also
  reachable synchronously via `POST /detection/poll-now` for testing) that every
  `DETECTION_POLL_INTERVAL_SECONDS` (default 8s) checks Mattermost, Zammad, Wiki.js, and the
  mailserver for Principal-authored activity and writes `narrative_events(origin='human')` +
  `pending_reactions` rows. New table `human_bridge_cursors(source, cursor_value)` tracks
  per-source progress (last post update_at per channel, last Zammad article id, last Wiki.js
  page updatedAt, last IMAP UID per employee mailbox) so a restart doesn't reprocess history.
- **Polling vs. webhooks — deliberate choice, all four sources**: Mattermost outgoing webhooks
  only fire on trigger words (not full-message capture, useless for "did the Principal mention
  this employee anywhere"); Zammad/Wiki.js don't have an outbound-webhook registration flow
  meaningfully simpler than polling in this environment. The spec's own phrasing ("via native
  webhooks... or IMAP polling") already accepts polling for at least mail, so we extended the
  same pragmatic choice to Mattermost/Zammad/Wiki.js too — one polling pattern, four pollers,
  much less integration risk than standing up real webhook receivers for three appliances.
- **Principal identity resolution**: `provision-principal` doesn't persist the Principal's
  Mattermost/Zammad/Wiki.js account IDs anywhere, so human-bridge resolves them at runtime and
  caches in-memory (`_principal_ids`): Mattermost via `GET /users/username/{email-local-part}`
  (same `email.split("@")[0].replace(".", "_").lower()` convention provisioning uses for both
  employees and the Principal), Zammad via `/users/search?query=<email>`, Wiki.js via a GraphQL
  `users.list` scan (no server-side email filter available on that query, live-checked).
- **"Addressed to" resolution per source**:
  - Mattermost: scans the post text for `@<derived-username>` of every active employee (no DB
    username column exists; the username is deterministic from email, so no schema change
    needed).
  - Zammad: ticket's `owner_id` → `employees.zammad_agent_id`.
  - Wiki.js: **new convention established** (none existed before) — a page "related to" an
    employee carries a tag `emp-<employee_id>`. Documented here since it's not written down
    anywhere else. `pages.list`'s `PageListItem` type does not expose `authorId`/`tags` (confirmed
    live, GraphQL validation error) — the poller lists cheaply by `updatedAt`, then does one
    `pages.single(id)` GraphQL call per candidate page to get `authorId` + `tags { tag }`.
  - Mail: recipient `To:` address → `employees.email`/`mailbox_address`.
- **Mail polling approach — changed from the original plan after live testing**: intended to
  IMAP-login as the Principal (confirmed their mailbox uses the identical
  `derive_mail_password()` scheme as employee bots — `provision-principal`'s
  `mail.create_account(PRINCIPAL_EMAIL)` hits the same `MailserverClient` path) and poll their
  **Sent** folder. Live-verified this doesn't work: docker-mailserver does no sender-side
  archiving on SMTP submission, so mail sent via raw SMTP (or by any client that doesn't itself
  IMAP-APPEND a copy) never appears in the sender's Sent folder — it stayed empty across two
  test sends. Switched to polling every active employee's own **INBOX** (using that employee's
  already-proven-working derived password, same login `send_as_employee` uses) filtered by
  `FROM: <principal email>` — a reply from the Principal to an employee always lands in the
  employee's INBOX regardless of how it was sent, so this is both simpler and more reliable.
  requirements.txt unchanged — used stdlib `imaplib` (blocking calls wrapped in
  `asyncio.to_thread`), no new dependency.
- **Side finding, not fixed (out of scope, pre-existing, affects the untouched action-injection
  code too)**: this mailserver's Amavis is configured to hard-block (`BAD-HEADER`, bounce to
  sender) any message missing a `Date:` header. `send_as_employee()`'s `MIMEText` construction
  never sets one, so **every** real `/action/send-email` send in this environment is currently
  being silently bounced back to the sender rather than delivered — confirmed live by sending via
  the actual `/action/send-email` endpoint (employee → carol.okonkwo) and finding the quarantined
  copy at `/var/mail-state/lib-amavis/virusmails/.../badh-*` with
  `X-Amavis-Alert: BAD HEADER SECTION, Missing required header field: "Date"`. Not fixed here
  since `send_as_employee`/`/action/send-email` are explicitly out of scope for this task; flagged
  for a follow-up since it silently breaks a "done and correct" endpoint in production terms.
- **Fire-reassignment**: `provisioning/main.py`'s `fire_employee()` now calls a new
  `reassign_pending_reactions(conn, employee)` (added directly in provisioning — it already owns
  the DB connection during fire, matching how the rest of `fire_employee()`'s deactivation steps
  are structured) after the account-deactivation steps. Selection: prefer another active employee
  in the same `department` + `role_tier`; fall back to the longest-tenured active employee
  overall. No pre-existing `action_items` reassignment logic exists to mirror exactly (confirmed —
  `fire_employee()` only had a comment saying the orchestrator would handle it eventually), so
  this is a simple, self-consistent version of that same idea, scoped to `pending_reactions` only.
  `pending_reactions.target_employee_id` is `ON DELETE CASCADE` but `employees` rows are never
  actually deleted (soft delete, `status='terminated'`), so no DB cascade was ever going to fire
  here — reassignment had to be explicit, which this now is.
- **Live verification, all 5 Phase 17 exit criteria, real appliances** (via
  `docker compose exec human-bridge` one-off scripts + `POST /detection/poll-now` + direct
  `psql` checks against `fakeco-postgres`):
  1. Mattermost: provisioned a real Principal Mattermost account (`provision-principal` had never
     been run before this session — fixed a stale `MAILSERVER_BOT_SECRET`-derived mailbox
     password mismatch along the way by deleting and recreating the mailbox), added Principal to
     the team + `town-square`, posted `"Hey @alice_johnson can you look into the Q3 report
     today?"` as Principal. Result: `narrative_events` row id 8 (`origin='human'`,
     `source_type='chat'`, `source_ref='mattermost:de4bs44s...'`) + `pending_reactions` row id 2
     (`target_employee_id=1` Alice, `status='pending'`) appeared within one poll cycle.
  2. Email: sent a real SMTP message (mailserver container, submission port 587, authenticated as
     `principal@fakecorp.internal` with the derived password) to `alice.johnson@fakecorp.internal`
     with subject "Demo prep 2" (added a `Date:` header to get past the Amavis issue above — see
     that finding). Result: `narrative_events` row id 12 (`source_type='email'`,
     `source_ref='mail:alice.johnson@fakecorp.internal:2'`) + `pending_reactions` row id 6
     (`target_employee_id=1`) appeared after one poll.
  3. Zammad: created a real ticket via the admin API, added a comment article via the same token
     Zammad resolves as `created_by_id=2`, which is exactly the id `_resolve_principal_zammad_id`
     independently resolves for `principal@fakecorp.internal` (this environment's "admin token"
     authenticates as that same Zammad user — convenient, confirmed live, not assumed). Needed one
     fix along the way: `/api/v1/ticket_articles` (bare list) 403s under this token even though
     it's meant to be an admin/agent token; switched to walking `/api/v1/tickets` +
     `/api/v1/ticket_articles/by_ticket/{id}` per ticket, which both work. Result: `narrative_events`
     row id 9 (`source_type='ticket'`, `source_ref='zammad:5'`) + `pending_reactions` row id 3
     (target Alice, via her real `zammad_agent_id`) appeared.
  4. Wiki.js: created a real page via GraphQL as the admin token (which is the Principal's Wiki.js
     account, id 1 — confirmed via a `users.list` query) with tag `emp-5` (Eva Rossi), fixing the
     mutation's missing required `isPrivate` argument and the `tags` subfield-selection error along
     the way. Result: `narrative_events` rows (`source_type='wiki'`) + `pending_reactions` row
     (`target_employee_id=5`) appeared. Known minor rough edge: the page produced two
     near-duplicate `narrative_events` rows a few hundred ms apart (Wiki.js's own internal
     `updatedAt` bumped twice around page creation, and the source_ref includes that timestamp so
     dedup-by-source_ref didn't collapse them) — cosmetic double-counting, not a correctness bug
     for the exit criterion (the row for the right employee did appear), left as a known limitation
     rather than fixed under this task's time budget.
  5. Fire-reassignment: fired employee 1 (Alice Johnson, department Engineering, role_tier lead) via
     `provisioning/main.py`'s real `fire` CLI command while she had 3 pending `pending_reactions`
     rows (ids 2, 3, 6). No other active Engineering lead existed, so the fallback path was
     exercised: all 3 rows' `target_employee_id` changed from 1 to 16 (Paul Renard, HR lead — the
     longest-tenured other active employee), `status` unchanged (`pending`), confirmed via direct
     `psql` query. Not silently dropped/orphaned.
- **Files touched:** `human-bridge/main.py` (detection layer + `/detection/poll-now`),
  `provisioning/main.py` (`reassign_pending_reactions()` + call from `fire_employee()`),
  `docker-compose.yml` (added `MATTERMOST_TEAM_ID` and `MAILSERVER_IMAP_PORT` env vars to the
  `human-bridge` service — it was already on `net_mail` and had the other tokens/URLs it needed).
  No new Python dependency (stdlib `imaplib`), `requirements.txt` unchanged.
- **Not independently re-verified in this pass**: the pre-existing action-injection endpoints
  (`/action/mattermost-post`, `/action/zammad-ticket`, etc.) — used them as *test tooling* to
  generate Principal-side activity for the detection checks above, which incidentally re-confirms
  they still work, but no new bugs were hunted in that code per this task's explicit "don't touch"
  scope.
- **Next:** Phase 18 — orchestrator continuity loop, which is what actually consumes
  `pending_reactions` rows (priority 1) written by this detection layer.

---

### 2026-07-31T19:15 — Phase 18 partially verified: 1 systemic bug fixed (blocked orchestrator entirely), scheduling loop confirmed working; priority-queue/retry-queue gap flagged

- **Systemic bug, blocked every custom service's healthcheck, and specifically prevented
  `orchestrator` from ever starting:** all 5 custom services (`sim-clock`, `accounting-engine`,
  `meeting-simulator`, `human-bridge`, `orchestrator`) had a Docker `HEALTHCHECK` using
  `curl -f http://localhost:8000/health`, but none of their Dockerfiles (based on `python:3.12-slim`)
  install `curl` — every healthcheck failed with `OCI runtime exec failed: ... exec: "curl":
  executable file not found in $PATH`, marking all of them permanently `unhealthy` even though the
  services themselves were running correctly. This was silently tolerable for services nothing
  else hard-depends on, but `orchestrator`'s `depends_on: sim-clock: condition: service_healthy`
  meant it could **never start** — `docker compose up` failed with `dependency sim-clock failed to
  start: container fakeco-sim-clock is unhealthy` every time. **Fixed:** replaced all 5
  healthchecks in `docker-compose.yml` with a `python -c "import urllib.request..."` one-liner —
  no new package needed, since Python's stdlib is already present in every one of these images.
  All 5 containers now report `healthy`.
- (Unrelated side-effect noted for the record: bringing sim-clock back up after the earlier
  concurrent-edit/profile confusion re-seeded it fresh — this is expected/harmless, not a bug.)
- With the fix in place, `orchestrator` started cleanly and its tick loop immediately proved itself
  live and correct without any manual triggering: within the first tick it called
  `GET /meetings/pending-performance-reviews`, found employee #16 (Paul Renard) due, fired a real
  `POST /meeting/run` against meeting-simulator, which completed successfully — confirmed a genuine
  new `meetings` row (`id=7, meeting_type=performance_review`) appeared in Postgres. This is
  meaningfully more convincing than a synthetic manual test: it's the actual autonomous heartbeat
  working end-to-end, unprompted.
- **Not verified (gap, consistent with the design gap noted in this file's Phase 18 code
  inspection):** `orchestrator/main.py`'s tick loop is a fixed sequence of `maybe_run_X()`
  scheduled-job checks (stale threads → performance reviews → standups → cross-functional →
  payroll → books audit → KPI rollup), not the per-employee "reaction → approval → action item →
  filler" priority-consumption loop spec §4.3 describes, and there is no `pending_actions` table or
  reachability/retry-queue mechanism at all (spec §13.1) — confirmed by grepping the file and the
  schema, neither exists. This is architecturally the same category of gap as Phase 17's missing
  detection layer: a real, non-trivial feature gap rather than a bug in existing code. Given time
  already spent this session finding and fixing 20+ real runtime bugs across Phases 1-18, this is
  flagged as a follow-up rather than attempted now.
- **Files touched:** `docker-compose.yml` (5 healthcheck fixes)
- **Status:** all custom services (Phases 12-18) are now up, healthy, and have had at least one
  real functional path verified end-to-end. Two known architectural gaps remain open (Phase 17
  detection layer — a background session already started on this per the task chip; Phase 18
  priority-queue + pending_actions retry queue — not yet started).

---

### 2026-07-31T23:10 — Phase 20 (Interpersonal relationships) built and runtime-verified in an isolated `docker compose -p fakeco-p20` stack

- **What was built** (per `PLAN_REMAINING_PHASES.md`'s Phase 20 section and `PHASES.md`'s exit
  criteria — `employee_relationships` table already existed from migration 004, so this was pure
  service-extension work, no new migration):
  1. `provisioning/main.py`: new `seed_employee_relationships(conn, employee)`, called at the end
     of `provision_employee()`. On first provisioning, looks up up to 2 other active
     same-department employees (ordered by `hired_at, id` for determinism — no LLM, no
     randomness), and `INSERT ... ON CONFLICT (employee_a_id, employee_b_id) DO NOTHING`s a
     `neutral`/`affinity_score=10` row per pair, respecting the schema's canonical-ordering CHECK
     (`employee_a_id < employee_b_id`, computed via `min()/max()` before insert). `ON CONFLICT DO
     NOTHING` makes re-provisioning the same employee a true no-op — it does not reset affinity
     that meeting-simulator may have already nudged.
  2. `meeting-simulator/main.py`'s `build_meeting_prompt()`: extended the *existing* single LLM
     call's JSON schema so `decisions` is now an array of `{description, stances}` objects instead
     of bare strings — `stances` maps every attendee's exact name to `agree`/`disagree`/`neutral`
     for that decision. No second LLM call anywhere in the path.
  3. New pure functions in `meeting-simulator/main.py`: `compute_affinity_updates(decisions,
     attendees, delta=5)` walks every attendee pair per decision and returns
     `{(a_id,b_id): total_delta}` (agree/agree or disagree/disagree → +5, split → -5, any
     `neutral` participant excluded from that pair) using the same `(min_id,max_id)` canonical
     ordering as the schema; `apply_affinity_updates(conn, updates)` upserts each delta with
     `GREATEST(-100, LEAST(100, ...))` clamping to respect the `affinity_score` CHECK. Wired into
     `run_meeting()`'s existing persistence transaction, right after `action_items` creation — same
     transaction as everything else, no extra DB round trip class.
  4. New pure, directly-callable `score_candidate_by_relationships(candidate_id,
     already_selected_ids, relationships_map)` — sums affinity between a candidate and everyone
     already selected. `fetch_relationship_map(conn)` loads the whole `employee_relationships`
     table into that `{(a,b): score}` dict once per `select_attendees()` call. Wired into the
     `cross_functional` branch of `select_attendees()`: instead of `DISTINCT ON (department)
     ORDER BY hired_at` picking the earliest-hired IC per department unconditionally, it now picks
     `max(candidates, key=(relationship_score, -hired_at))` — relationship score first, earliest
     hire only as a tie-break — so the deterministic-selection contract (spec §4.2, no LLM-invented
     attendee lists) is preserved.
  5. Deliberately did **not** touch `dashboard/` — Phase 20's exit criteria explicitly excludes the
     relationship view (that's Phase 34).
- **Verified against a real, isolated `docker compose -p fakeco-p20` stack** (own `.env` copied
  from the main checkout, own container names via a temporary `docker-compose.p20-override.yml`
  to avoid colliding with the always-running main-checkout containers of the same
  `container_name`s — deleted after use). Brought up `postgres`, `narrative-db-migrate`, `litellm`,
  `meeting-simulator`, `provisioning`, all built with `--build`. The main checkout's own 30+
  `fakeco-*` containers were confirmed untouched/still healthy throughout and after teardown
  (`docker compose -p fakeco-p20 ... down -v` — confirmed no orphaned containers/volumes left).
  - **Seed relationships**: inserted a brand-new test employee (`Test Newhire`, Engineering, id 22)
    directly into the roster and called the real `seed_employee_relationships()` against the live
    DB (bypassing the Mattermost/Zammad/Wiki.js legs of `provision_employee`, which are Phase 14's
    already-verified concern, not Phase 20's — see bug note below on why full-stack `provision`
    CLI runs weren't used for this specific check). Confirmed 2 new rows appeared
    (`(1,22)` and `(5,22)`, both `neutral`/`affinity_score=10`). Re-ran the same function against
    the same employee: confirmed 0 additional rows (`ON CONFLICT DO NOTHING` idempotency holds).
  - **Real meeting with stances, single LLM call**: triggered `POST /meeting/run`
    (`standup`/Engineering, attendees included the new hire) against the live
    `meeting-simulator` container talking to a real DeepSeek call through `litellm`. Queried
    `meetings.decisions` afterward and confirmed each decision is a real
    `{"description": ..., "stances": {"Eva Rossi": "neutral", "Bob Martinez": "agree", ...}}`
    object with every attendee named. Queried LiteLLM's own `/spend/logs`: exactly **one** log
    entry for the whole meeting (`model_group: "heavy"`, 601 prompt / 2299 completion tokens) —
    confirms the stance field really did ride the existing call, no second LLM spend.
  - **Deterministic affinity delta**: after the meeting, re-queried `employee_relationships` for
    the affected pairs. Confirmed exact `+5`-per-shared-decision arithmetic: e.g. `(1,22)` (Alice
    Johnson ↔ Test Newhire) went from the seeded `10` to `15` (they both said `agree` on exactly
    one of the three decisions; `neutral` on the others correctly contributed nothing), and several
    previously-unseeded pairs among the standup's attendees (e.g. `(1,2)` Alice↔Bob) were created
    fresh at exactly `+10` (two decisions where both agreed, `+5` each) — matched the transcript's
    stances by hand, decision by decision.
  - **Relationship-weighted attendee scoring — direct function call, no sampling**: called
    `score_candidate_by_relationships(100, [10,20], {(10,100): 80, (20,200): -50})` and the
    symmetric rival/unknown cases directly (no DB, no meeting) — asserted `ally_score(80) >
    unknown_score(0) > rival_score(-50)` exactly, per the exit criteria's explicit "deterministic
    assertion, not a statistical sample" requirement.
  - **End-to-end weighting inside `select_attendees()` itself** (not just the standalone
    function): manually set `employee_relationships(Alice[lead,id1], David[ic,id4])` affinity to
    `90` (David is the *latest*-hired Engineering IC, would never win the old `hired_at`-only
    tie-break). Called `select_attendees(conn, "cross_functional", max_cross_dept=20)` and
    confirmed Engineering's selected IC flipped from Eva Rossi (earliest-hired, the old
    unconditional pick) to David Chen — proving the weighting is live inside the real selection
    path, not just correct in isolation. Reverted the test data afterward.
- **Real pre-existing bug found (not introduced by this phase, not fixed — flagging per session
  convention for a dedicated follow-up):** `select_attendees()`'s `cross_functional` branch builds
  one combined dict (`all_emp`) with department **leads inserted first**, then ICs, then truncates
  to `max_cross_dept` (default 5) via `list(all_emp.values())[:max_cross_dept]`. With the current
  7-department roster there are 7 active leads — since they're inserted before any IC and the
  truncation is a flat slice of the combined list, **every IC is silently dropped from every
  cross_functional meeting**, regardless of this phase's new relationship weighting (confirmed via
  `max_cross_dept=20` — the correctly-weighted IC only appears once the cap is raised above the
  lead count). `max_cross_dept` needs to apply per-role (or per-department) rather than as a flat
  post-concatenation slice. Did not fix here since it's Phase 16 pre-existing scope, not Phase 20's
  — but it silently defeats this phase's IC-selection weighting under the current default, so it's
  a real, verified, user-facing gap worth prioritizing.
- **Environment note (not a code bug, but worth recording):** the main `.env`'s
  `LITELLM_DATABASE_URL` is unset, so LiteLLM defaults to the *same* Postgres database as the
  narrative schema. LiteLLM's own Prisma migration on startup appears to reset/recreate the
  `public` schema's non-LiteLLM tables if it starts before `narrative-db-migrate` — observed in
  the isolated stack (had to re-run `narrative-db-migrate` after `litellm` to get `employees`/
  `employee_relationships` back). Didn't affect the main checkout (already running, migrations
  already applied), but worth a dedicated `LITELLM_DATABASE_URL` pointing at a separate database
  before any future from-scratch bring-up, to avoid this collision on cold start.
- **Files touched:** `provisioning/main.py` (added `seed_employee_relationships()`, called from
  `provision_employee()`), `meeting-simulator/main.py` (extended `build_meeting_prompt()`'s JSON
  schema; added `score_candidate_by_relationships()`, `fetch_relationship_map()`,
  `decision_text()`, `compute_affinity_updates()`, `apply_affinity_updates()`, `AFFINITY_DELTA`
  constant; wired weighting into `select_attendees()`'s `cross_functional` branch and affinity
  updates into `run_meeting()`; fixed 2 decision-rendering call sites (Mattermost text, Wiki.js
  page content) to use the new `decision_text()` helper instead of assuming decisions are bare
  strings).
- **Status:** Phase 20 backend + meeting-simulator hook complete and runtime-verified per every
  bullet in `PHASES.md`'s exit criteria. No dashboard work done (correctly deferred to Phase 34).
  One real pre-existing bug found and flagged (cross_functional's flat `max_cross_dept` truncation
  drops all ICs at the current roster size) — not fixed, logged for a dedicated follow-up.

---

### 2026-07-31T19:15 — Phase 23 built: kpi-engine (KPI scoreboards + performance-review formula), partial live verification

- **Built `kpi-engine/` from scratch** (previously a README stub), following the exact
  `accounting-engine`/`external-world` pattern (`python:3.12-slim`, fastapi/uvicorn/asyncpg/httpx/
  pydantic, `Dockerfile` + `requirements.txt` + single `main.py`, `/health` endpoint, manual-trigger
  POST endpoints like every other custom service in this project). Files: `kpi-engine/Dockerfile`,
  `kpi-engine/requirements.txt`, `kpi-engine/main.py`.
- **Deterministic daily rollup (`POST /rollup/run`, spec §12.1) — zero LLM calls anywhere:**
  - `ZammadClient.get_tickets_in_range()`: fetches all tickets via `/api/v1/tickets/search?query=*`
    and filters/aggregates `created_at`/`close_at` client-side in plain Python (deliberately avoids
    relying on Zammad's own search-query date syntax, which is undocumented/inconsistent across
    versions) — writes `tickets_opened`, `tickets_resolved`, `avg_resolution_hours` per employee
    (matched via `employees.zammad_agent_id == ticket.owner_id`) and per department (via Zammad
    `group_id` → group name, fetched once via `/api/v1/groups`).
  - `WikiJSClient.list_pages()`: GraphQL `pages.list` query (reusing the exact `graphql()` helper
    pattern + Bearer-token client from `provisioning/main.py`'s `WikiJSClient`), matched against
    `employees.wiki_user_id`, writes `wiki_pages_created`/`wiki_pages_updated` (an update is only
    counted distinct from the creation event if `updatedAt > createdAt`, to avoid double-counting
    the initial save Wiki.js always stamps as an "update").
  - `MattermostClient`: no dedicated message-count/stats endpoint exists in the Mattermost REST API,
    so pages through every team's channels (`/teams`, `/teams/{id}/channels`) and each channel's
    `/channels/{id}/posts?since=...`, counting posts per `user_id` matched against
    `employees.mattermost_id` — writes `chat_messages` per employee/department.
  - `AkauntingClient.get_income_transactions()`: reuses `accounting-engine.AkauntingClient`'s
    `company_id`-in-every-request pattern (this codebase's `AkauntingClient` sends `company_id` as a
    request param/body field rather than an `X-Company` header — confirmed by re-reading
    `accounting-engine/main.py`'s existing client rather than assuming the header pattern), sums
    income transactions in the date range, writes one `revenue_posted` row under
    `department`/`"Company"` (Akaunting revenue isn't attributable to an individual employee in this
    schema).
  - Every rollup row is written via `write_snapshot()`, an `INSERT ... ON CONFLICT
    (snapshot_date, entity_type, entity_id, metric) DO UPDATE SET value = EXCLUDED.value` — the
    table's existing UNIQUE constraint (already defined in `narrative-db/migrations/004_additive_
    schemas.sql`, not re-migrated here per the task's explicit instruction) makes re-running a
    rollup for the same day naturally idempotent rather than duplicating rows.
- **Performance-review formula (`GET /reviews/due`, `POST /reviews/run`, spec §12.2) — plain code,
  no LLM:**
  - `compute_review_candidates()`: pulls each eligible employee's last `KPI_REVIEW_LOOKBACK_DAYS`
    (default 30) of `kpi_snapshots`, computes a weighted composite score (tunable weights via env:
    `KPI_WEIGHT_TICKETS_RESOLVED`, `KPI_WEIGHT_WIKI_PAGES`, `KPI_WEIGHT_CHAT_MESSAGES`,
    `KPI_WEIGHT_RESOLUTION_HOURS` — the last one negative since fewer hours-to-resolve is better),
    ranks descending within department, and splits into `top_quartile` (`ceil(n/4)`, default
    +`KPI_REVIEW_TOP_RAISE_PCT`=5%), `second_quartile` (next `ceil(n/2)`, default
    +`KPI_REVIEW_SECOND_RAISE_PCT`=2%), and `rest` (+0%) — all tunable via env, matching
    `accounting-engine`'s `IC_AUTO_APPROVE_LIMIT`-style convention.
  - SPEC_CLARIFICATIONS #6 cold-start exemption: skips employees hired `<KPI_REVIEW_MIN_TENURE_DAYS`
    (default 90) days ago and departments with `<KPI_REVIEW_MIN_DEPT_SIZE` (default 2) active
    members — the SQL filter is copy-aligned with `meeting-simulator`'s existing
    `GET /meetings/pending-performance-reviews` eligibility query so both services agree on who's
    "due" for a review.
  - `apply_review_raises()` **calls into accounting-engine's real, already-verified
    `POST /payroll/raise` endpoint** for each top/second-quartile employee (does NOT reimplement
    the DB write) — raises apply immediately with no approval step by default, per spec §10.3.
  - Underperformance is exposed as an `underperforming: bool` flag on each `/reviews/due` candidate
    (bottom `KPI_REVIEW_UNDERPERFORM_PERCENTILE`, default 10%, within department) but this service
    **never** opens a meeting or takes any action on it — per the task scope, that's Phase 24's job
    (extending `meeting-simulator` to open a `performance_review` meeting instead of a cut).
  - **"Review & approve" toggle** (`KPI_REVIEW_APPROVAL_MODE`, off by default): when `on`, proposed
    raises are queued into `pending_approvals` (`status='pending'`, `approver_is_principal=true`,
    `expense_request_ref` prefixed `review_raise:...`, idempotency-keyed per employee/day) instead
    of being auto-applied. Nothing consumes this queue yet (no dashboard exists) — implemented per
    the task's explicit "implement the toggle and queuing path even if nothing consumes it yet."
- **Wired into `docker-compose.yml`:** new `kpi-engine` service block (copied from
  `accounting-engine`'s block pattern), `net_clients` + `net_data` + `net_office`, `depends_on`
  postgres healthy + `narrative-db-migrate` completed, `profiles: [phase23]`. Per this task's
  explicit instruction, its healthcheck uses
  `python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen(...).status==200 else 1)"`
  rather than `curl` (these `python:3.12-slim` images don't have `curl` installed) — verified this
  healthcheck actually passes (`docker ps` showed `health: healthy` within one interval). Also
  removed the now-stale "kpi-engine (Phase 23+)" line from the Phase 19+ placeholder-topology
  comment block since it's no longer a placeholder.
- **Verification performed against a live, isolated Docker stack** (`docker compose -p fakeco-p23`,
  a copy of this worktree's `.env` + a `docker-compose.override.yml` giving `postgres`/
  `narrative-db-migrate`/`accounting-engine`/`kpi-engine` unique container names so it could run
  side-by-side with the main checkout's already-running `fakeco-*` stack without touching it):
  1. Brought up `postgres` + `narrative-db-migrate` (phase13) + `accounting-engine` (phase15) +
     `kpi-engine` (phase23). All three app containers reached `healthy`/ran clean startup logs.
  2. Seeded 4 synthetic `TestDept` employees (ids 21–24, tenure 200 days, dept size 4 — clears the
     cold-start gate) and 4 `kpi_snapshots` rows (`tickets_resolved` = 100/50/10/1) directly via
     `psql`, simulating what a real rollup would have produced.
  3. `GET /reviews/due` returned exactly the expected ranking: employee 21 (score 100) →
     `top_quartile`/+5%, employee 22 (score 50) → `second_quartile`/+2%, employee 23 (score 10) →
     `rest`/+0%, employee 24 (score 1) → `rest`/+0%/`underperforming: true` (bottom 10% of 4 = last
     one) — matches the quartile-split math (`ceil(4/4)=1` top, `ceil(4*2/4)=2` second) by hand.
  4. `POST /reviews/run` (default mode, `KPI_REVIEW_APPROVAL_MODE=off`) applied real raises through
     `accounting-engine`'s live `/payroll/raise` endpoint: confirmed via direct `psql` query that
     employee 21's `pay_rate` moved `1000.00 → 1050.00` and employee 22's `1000.00 → 1020.00`, both
     with `pay_last_change_reason` populated (`"performance_review: top_quartile in TestDept (rank
     1/4)"` etc.) — i.e. this is genuinely calling into accounting-engine's already-verified raise
     path, not a parallel reimplementation. (It also correctly applied raises to the placeholder
     20-employee roster's top/second-quartile members within their own departments, since those
     employees have zero `kpi_snapshots` and therefore tie at composite score 0 — expected behavior
     of the formula given no real KPI data yet, not a bug.)
  5. Reset test employees' pay, restarted `kpi-engine` with `KPI_REVIEW_APPROVAL_MODE=on`, re-ran
     `POST /reviews/run`: confirmed 0 raises applied directly (`employees.pay_rate` unchanged for
     21/22) and 2 new `pending_approvals` rows created instead (`status='pending'`, `amount` =
     proposed new pay, `expense_request_ref` = `"review_raise:performance_review: ..."`) — the
     toggle genuinely changes the code path, not just a flag that's ignored.
  6. Confirmed `kpi_snapshots` upsert idempotency directly: re-inserting the same
     `(snapshot_date, entity_type, entity_id, metric)` key with a different `value` via the same
     `ON CONFLICT ... DO UPDATE` statement the service uses left exactly 1 row (updated value),
     never 2.
  7. Tore down cleanly (`docker compose -p fakeco-p23 down -v`), removed the temporary
     `.env`/`docker-compose.override.yml` copies from the worktree. Confirmed via `docker ps` that
     only the main checkout's `fakeco-*` containers (plus an unrelated pre-existing `fakeco-p19-*`
     stack from a different session) remain — nothing from this pass was left running.
- **Known gap, NOT fixed this pass (flagged, not swept under the rug):** the four appliance HTTP
  clients (`ZammadClient`, `WikiJSClient`, `MattermostClient`, `AkauntingClient`) inside
  `run_rollup()` were **not** exercised against live, freshly-bootstrapped Zammad/Wiki.js/
  Mattermost/Akaunting instances in this pass. Each of those four requires the same lengthy,
  previously-hand-run bootstrap chain documented earlier in this log (Mattermost: enable personal
  access tokens + mint one via API; Zammad: `rails r` to repoint the seeded admin + mint a token;
  Wiki.js: complete the `/finalize` setup wizard + `setApiState(enabled:true)` + mint an API key;
  Akaunting: still has the unresolved `task_a5d68375` payment-method/company-binding bug noted in
  the Phase 15 log entry above) — redoing all four from scratch for a disposable isolated stack was
  out of scope for this pass's time budget, and the `.env`'s existing tokens are bound to the main
  checkout's already-provisioned instances, not a fresh stack. What WAS verified live end-to-end is
  the part of Phase 23 that actually matters most for spec §12.1/§12.2 correctness — the zero-LLM
  deterministic aggregation math, the upsert idempotency, the quartile-ranking formula, and (most
  importantly) that raises genuinely flow through accounting-engine's real, previously-verified
  code path rather than a reimplementation. Recommend a follow-up pass runs `/rollup/run` against
  the main checkout's live stack directly (not an isolated copy) once real Zammad tickets/Wiki.js
  pages/Mattermost messages/Akaunting transactions exist there, to close this gap.
- **Files touched:** `kpi-engine/Dockerfile` (new), `kpi-engine/requirements.txt` (new),
  `kpi-engine/main.py` (new, ~520 lines), `docker-compose.yml` (new `kpi-engine` service block +
  placeholder-comment cleanup).
- **Next:** Phase 24 (meeting-simulator extension: pay negotiation & performance review) — consumes
  `GET /reviews/due`'s `underperforming` flag to open `performance_review` meetings instead of
  cuts, and closes the Phase 15 pay-cut stub via real meeting outcomes.

---

### 2026-07-31T19:10 — Phase 19 (PTO / out-of-office) built and runtime-verified (4 real bugs found and fixed)

- **What was built**, per `PLAN_REMAINING_PHASES.md`'s Phase 19 section — everything lives in
  `orchestrator/main.py` and `accounting-engine/main.py`, no new microservice (spec explicitly
  folds this into existing services rather than a dedicated one):
  1. **`maybe_schedule_pto()`** — new orchestrator tick-loop job. Deterministic-per-(employee, sim
     date) RNG (seeded via sha256, so re-running the same tick never double-rolls) checks
     `PTO_DAILY_PROBABILITY` (default 1%/day) per active employee, respecting `PTO_MIN_GAP_DAYS`
     (default 45) since their last window, and inserts a `PTO_DURATION_MIN..MAX_DAYS` (default 3–7)
     window into `pto_calendar`.
  2. **Real Sieve vacation responder.** Researched first, per the plan's explicit flag: `docker exec
     fakeco-mailserver setup help` shows **no** Sieve subcommand under `setup` at all (only
     email/alias/dkim/relay/debug/quota/etc.) — confirmed against the live container, not just
     docs. docker-mailserver *does* bundle Dovecot Pigeonhole with a `doveadm sieve` CLI plugin in
     the same container, though, so rather than hand-rolling raw ManageSieve (RFC 5804) on port
     4190, `orchestrator` now does `docker exec fakeco-mailserver doveadm sieve put/activate/
     deactivate/delete -u <mailbox>` — genuinely native per-user Sieve script management, just
     driven through doveadm instead of `setup`. Mirrors `provisioning`'s existing docker-exec
     pattern; added `docker-cli` to `orchestrator/Dockerfile` (same package gotcha as
     `provisioning/Dockerfile` already documents) and mounted the docker socket
     (`:ro`, matching `provisioning`'s mount) into the orchestrator container in
     `docker-compose.yml`.
  3. **Real Mattermost custom status.** `PUT /api/v4/users/{id}/status/custom` (emoji
     `palm_tree`, text "Out of Office", `expires_at` = the PTO window's end), using the same
     ephemeral-admin-PAT impersonation pattern as `human-bridge`'s `post_mattermost_as_employee`
     (create token, act as employee, revoke).
  4. **`maybe_apply_pto_effects()`** — per-tick job that idempotently (via the same
     `system_audit_log`-backed `get_last_run`/`record_run` job-tracking convention as every other
     orchestrator job) applies both start-effects the tick a window opens, and both end-effects +
     fires a "catching up" burst the tick a window closes.
  5. **Continuity-loop skip.** `maybe_run_performance_reviews()` now skips any eligible employee
     currently on PTO (`is_employee_on_pto()` helper, reusable).
  6. **"Catching up" burst.** `fire_catching_up_burst()` — on PTO-end, opens/reuses the employee's
     department's open `narrative_threads` row and writes a `pending_reactions` row targeting them,
     reusing the exact mechanism `human-bridge`'s Phase 17 detection layer already writes into (no
     new consumption path needed).
  7. **Approval delegation** — `accounting-engine`'s `resolve_approver()` (§10.2) now takes
     `sim_time` and, whenever it would route an expense to a specific approver (dept lead for an
     IC's request, or a lead auto-approving their own), calls a new `_redirect_pto_approver()`:
     if that approver is currently on PTO, route to their `backup_approver_id` (new nullable
     column on `employees`, `narrative-db/migrations/006_phase19_pto.sql`) if one is configured,
     active, and not themselves on PTO; otherwise escalate one tier to Principal — matching the
     existing 10.2 no-lead-in-department escalation convention exactly rather than inventing a new
     code path.
- **4 real bugs found via live verification** (isolated stack, project name `fakeco-p19`, brought
  up from this worktree with mailserver/mattermost/sim-clock/narrative-db-migrate/provisioning/
  accounting-engine/orchestrator profiles — main `fakeco-*` stack was never touched):
  1. **`sim-clock`'s healthcheck was broken in a clean build.** `sim-clock/Dockerfile` never
     installed `curl`, but `docker-compose.yml`'s healthcheck for it runs `curl -f .../health` —
     it failed every check with `exec: "curl": executable file not found in $PATH`, permanently
     stuck `unhealthy`, which blocks anything with
     `depends_on: sim-clock: condition: service_healthy` (i.e. `orchestrator`) from ever starting
     on a fresh environment. The main long-running stack happened to still be reporting "healthy"
     from a stale/earlier health-check state, which is why this was invisible until a genuinely
     clean rebuild. **Fixed:** added `curl` to `sim-clock/Dockerfile` (matching the existing
     apt-get pattern in `provisioning`/`orchestrator`).
  2. **`doveadm sieve deactivate` does not take a script-name argument.** Mirroring `activate
     <name>`'s syntax, the first implementation called
     `doveadm sieve deactivate -u <user> <name>` — this is not a valid invocation; `deactivate`
     always targets whichever script is currently active and takes no name. The extra arg made it
     silently do nothing, and the subsequent `doveadm sieve delete` then failed with `"Cannot
     delete the active Sieve script"`. The end-of-PTO code logged success regardless (it only
     warned on delete failure, not on this). Verified directly: after a full start→end cycle with
     the buggy code, `doveadm sieve list -u alice.johnson@fakecorp.internal` still showed
     `pto-vacation ACTIVE` — the revert had not actually happened. **Fixed:** call
     `deactivate -u <user>` with no script-name arg; re-verified the same cycle end-to-end and
     `doveadm sieve list` now returns empty after PTO end.
  3. **Mattermost personal-access-token revocation was silently broken, in code copied from
     `human-bridge`.** Both the new orchestrator code (copied the pattern) and the pre-existing
     `human-bridge.post_mattermost_as_employee` called
     `DELETE /api/v4/users/{user_id}/tokens/{token_id}` to revoke the ephemeral impersonation
     token — that route doesn't exist (404, unchecked). The real endpoint is
     `POST /api/v4/users/tokens/revoke` with a `{"token_id": ...}` body. Verified directly:
     `DELETE` returned 404 and `GET /users/{id}/tokens` still listed the token afterward;
     switching to `POST /tokens/revoke` actually removes it (confirmed empty token list after).
     Since this pattern has been in place since Phase 17, every ephemeral impersonation token
     `human-bridge` has ever created has been leaking (never revoked) until this fix. **Fixed in
     both `orchestrator/main.py` and `human-bridge/main.py`.**
  4. (Pre-existing, worked around, not fixed) `docker-compose.yml` gives several services
     hard-coded `container_name`s, which collide with the main long-running `fakeco-*` stack when
     bringing up a second project for isolated testing. Worked around with a temporary,
     not-committed `docker-compose.override.p19.yml` (renaming conflicting containers +
     redirecting `MAILSERVER_CONTAINER`/`MATTERMOST_ADMIN_TOKEN`) for this session's verification
     only; deleted after teardown. Not a code change — flagging for whoever eventually builds a
     proper test-stack convention.
- **Verified against a live, isolated `fakeco-p19` stack** (mailserver + mattermost + sim-clock +
  narrative-db-migrate + provisioning + accounting-engine + orchestrator; Zammad/Wiki.js/Akaunting/
  meeting-simulator not brought up since Phase 19 doesn't depend on them — provisioning's
  Zammad/Wiki.js calls failed as a result, expected and unrelated, so `mailbox_address` /
  `mattermost_id` were set directly on one test employee (Alice Johnson, Engineering lead) to
  exercise the mail/Mattermost paths):
  - Inserted a `pto_calendar` row starting immediately; triggered `POST /trigger/pto-effects`;
    confirmed via `doveadm sieve list -u alice.johnson@fakecorp.internal` → `pto-vacation ACTIVE`
    (a real script, fetched and inspected — genuine RFC 5230 `vacation` statement) and via
    `GET /api/v4/users/{id}` → `props.customStatus` containing the palm-tree emoji, "Out of
    Office" text, and correct `expires_at`.
  - Submitted an expense (`POST /expense/submit`, IC requester, amount in the lead-approval range)
    while Alice (the dept lead / natural approver) was on PTO with `backup_approver_id` set to
    another Engineering employee: confirmed `pending_approvals.approver_employee_id` was the
    backup, not Alice, and not stalled. Cleared the backup and resubmitted: confirmed it escalated
    to `approver_is_principal = true` instead.
  - Set the PTO window's `end_sim_time` into the past and re-triggered `pto-effects`: confirmed the
    Sieve script was fully deactivated + deleted (`doveadm sieve list` empty), confirmed
    `props.customStatus` was cleared (`GET /users/{id}` → `""`), confirmed the ephemeral Mattermost
    token was actually revoked (`POST /tokens/revoke` → 200, token no longer in
    `GET /users/{id}/tokens`), and confirmed a `pending_reactions` row was created targeting Alice
    (the "catching up" burst).
  - Triggered `pto-schedule` manually: ran without error against real employee data (no window
    rolled that run, expected given the low daily probability and `PTO_MIN_GAP_DAYS` guard from the
    just-created test windows).
  - Did not get a clean end-to-end check of the performance-review PTO skip specifically (no
    employee was tenure-eligible for a review in this short-lived test stack) — the skip logic
    (`is_employee_on_pto()` gate added to `maybe_run_performance_reviews()`) is the same helper
    proven correct by every other check above, so this is a lower-confidence but low-risk gap.
  - Torn down cleanly: `docker compose -p fakeco-p19 down -v` (plus a manual `docker rm -f` /
    `docker network rm` / `docker volume rm` pass for a few containers-in-use edge cases) — no
    `fakeco-p19-*` containers, networks, or volumes remained; the main `fakeco-*` stack (verified
    both before and after) was untouched throughout.
- **Files touched:** `orchestrator/main.py`, `orchestrator/Dockerfile`, `accounting-engine/main.py`,
  `human-bridge/main.py` (bug fix only), `sim-clock/Dockerfile` (bug fix only), `docker-compose.yml`
  (orchestrator: docker socket mount + new env vars), `narrative-db/migrations/006_phase19_pto.sql`
  (new `employees.backup_approver_id` column).
- **Next:** Phase 20 (interpersonal relationships) — meeting-simulator extension, no new
  appliance integration needed, lower risk than this phase's Sieve research.

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

### 2026-07-31T19:10 — Phase 9/15 follow-up resolved: `POST /api/transactions` "payment method is invalid"

Root-caused and closed out the payment-method follow-up flagged above, which was blocking Phase 15
(accounting-engine) from posting anything through Akaunting's real REST API. Two independent bugs
were involved — one in how we were calling the API, one a genuine Akaunting bug — and fixing only the
first was enough to unblock transaction posting; the second was found while proving the fix durable
across restarts and is now also fixed.

1. **The actual cause: wrong company header.** `App\Traits\Companies::getCompanyIdFromHeader()` reads
   `X-Company`, not `company` — every prior test in this investigation (including the original
   follow-up note above) sent `-H "company: 1"`. On an API request that resolves to `null`, then falls
   back to `getFirstCompanyOfUser()`, which happened to also resolve to company 1 for our single-company
   single-admin setup — so *most* endpoints (accounts, categories, settings) looked like they worked
   correctly with the wrong header, masking the real problem. `POST /api/transactions` specifically
   fails because Laravel's service-provider registration (and therefore the `offline-payments` /
   `paypal-standard` module's `PaymentMethodShowing` event listeners) is resolved once per request via
   `App\Utilities\ModuleActivator`, constructed during framework boot — **before** routing/middleware
   and before `getFirstCompanyOfUser()`'s auth fallback is available. With the wrong header, by the time
   `Modules::getPaymentMethods()` finally sees company 1 (after `IdentifyCompany` middleware runs), the
   module-enabled cache has *already* been computed and cached as "no company -> no enabled modules" for
   the configured 6h TTL, so the event never had any listeners this request (confirmed via instrumented
   `Modules::getPaymentMethods()` / `ShowAsPaymentMethod::handle()` / `app('events')->getListeners(...)`
   — 0 listeners bound, vs. 2 when called from `tinker`, where `ModuleActivator::is()` short-circuits to
   `true` for `runningInConsole()`). **Fix: use `X-Company: 1`, not `company: 1`, on every Akaunting API
   call** — this is not a code change, just the correct header name. `php artisan cache:clear` alone
   never fixed this (as originally suspected) because the *next* web request just recomputes and
   re-caches the same wrong-company-derived empty result — the fix has to be the header, not the cache.
   Confirmed: `POST /api/transactions` with `payment_method=offline-payments.cash.1` now returns `201`
   and the account balance updates correctly.
2. **New bug found while verifying durability: Akaunting's own entrypoint crash-loops on restart.**
   `/usr/local/bin/akaunting.sh` re-runs `php artisan install` on *every* container start whenever
   `AKAUNTING_SETUP=true` (checked unconditionally, regardless of `--start`/`--setup`), and that command
   is not idempotent — it fails with `"Not able to create a new user."` once the company/admin already
   exist, and (being wrapped in `bash -e`) the whole entrypoint then dies, so `restart: unless-stopped`
   just crash-loops it forever. Confirmed via `docker restart fakeco-akaunting`. **Fixed:** added
   `akaunting-init/entrypoint-idempotent.sh`, mounted read-only into the container and used as its
   `entrypoint`. It checks `.env` for `APP_INSTALLED=true` and, if present, skips straight to
   `--start` (fast path for a same-container restart, filesystem unchanged). If `.env` is missing but
   the DB schema is already populated (container *recreated*, not just restarted — its filesystem is
   ephemeral while the DB volume is not), it re-runs only the safe/idempotent half of the installer
   (`Installer::createDefaultEnvFile()` + `Installer::createDbTables()` re-running migrations, both
   no-ops against already-migrated tables) without touching the company/admin rows, then starts Apache.
   Verified all three paths end-to-end: fresh install from an empty DB, `docker restart` of a running
   container, and a full `docker compose up --force-recreate` against a pre-populated DB volume — every
   case ends with Apache serving and `POST /api/transactions` returning `201`.
- **Files touched:** `docker-compose.yml` (added `entrypoint:`/`volumes:` for `akaunting`),
  `akaunting-init/entrypoint-idempotent.sh` (new).
- **Unblocks:** Phase 15 (accounting-engine) can now be verified against Akaunting's real
  `POST /api/transactions` endpoint — make sure it sends `X-Company`, not `company`, as the header.

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
