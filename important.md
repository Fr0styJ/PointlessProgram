# IMPORTANT — read this first if context was just compacted

This is a scratch memory file for an in-progress session building out the FakeCo "Real
Appliances" simulation (Docker Compose stack + ~13 custom microservices). Written 2026-07-31
right before a context compaction. If you're picking this up fresh, read this whole file first,
then `BUILD_LOG.md` (the authoritative build journal — reverse-chronological, newest entries at
top of "## LOG"), then `PLAN_REMAINING_PHASES.md` (the detailed plan for phases 19/20/23/29/30/
33-38 the user asked for).

## Current git state
- Branch: `master`, also force-pushed to `main` on GitHub (`https://github.com/Fr0styJ/PointlessProgram`).
- Latest commit: `9a15ed3` "Phase 19: PTO / out-of-office..." — everything through here is
  committed AND pushed to both `master` and `main` on origin.
- Working tree was clean as of the last check before this file was written.
- **If Phase 30 (branding) finished and got merged after this file was written, there will be a
  newer commit — check `git log --oneline -5` to see what's landed since.**

## What's been verified working (real, live docker testing, not just "container starts")
Phases 1-11 (full walking skeleton: postgres, socket-proxy, monitoring, DNS/Traefik, mail,
Mattermost, Zammad, Wiki.js, Nextcloud/WordPress, Akaunting, LiteLLM, Grafana), Phases 12-18
(sim-clock, narrative-db, provisioning, accounting-engine, meeting-simulator, human-bridge,
orchestrator), Phases 21/22 (external-world), and now Phases 19/20/23 (PTO, relationships, KPI
engine) — all built, live-tested against real appliance APIs, bugs found and fixed, logged in
BUILD_LOG.md.

## Background agents / worktrees in flight
- **Phase 30 (branding-manager)** is running as a background agent as of this writing, worktree
  at `C:\code\PointlessProgram\.claude\worktrees\agent-ae6054c39a23c87fb`. When it completes
  you'll get a task-notification. **To merge it**: `cd` into that worktree, `git add -A && git
  commit`, then `cd` back to `C:\code\PointlessProgram` (⚠️ Bash tool cwd persists across calls —
  always explicitly `cd /c/code/PointlessProgram` before merge commands, don't assume you're
  back in main after a `cd worktree && ...` one-liner), then `git cherry-pick --no-commit
  <that-commit-hash>`. **BUILD_LOG.md WILL conflict** — always resolve by keeping both sides'
  content, newest-timestamp entry first, remove `<<<<<<<`/`=======`/`>>>>>>>` markers manually via
  the Read/Edit tools (NOT a python script — a python re-write of the whole file mangled UTF-8
  em-dashes into garbage once already this session; if you must script it, be very careful with
  encoding, but prefer Edit tool string replacement). **docker-compose.yml may also conflict** on
  the trailing "PHASES 29+/30+/33+ placeholder comment" block near the end of the file — just
  remove whichever placeholder line corresponds to the phase that just landed, keep the rest.
  **narrative-db/migrations/ numbering**: multiple parallel phases may pick the same next-number
  migration filename (e.g. two branches both claiming `005_`) since they forked from slightly
  different bases — check `ls narrative-db/migrations/` after merging and renumber if a
  duplicate/gap exists (rename with `git mv`, then fix any BUILD_LOG.md references to the old
  filename with `sed -i 's/005_foo\.sql/006_foo.sql/g' BUILD_LOG.md`).
- Other worktrees present (`gracious-diffie-7ccb2b`, `lucid-elbakyan-7653f5`,
  `lucid-mcnulty-c5e7fa`, `magical-haibt-b151ee`) are from EARLIER user-launched background
  sessions (Akaunting payment-method fix, Wiki.js meeting-notes integration, human-bridge
  detection layer, customer-seed data) that already completed and merged — these are stale
  leftovers, probably safe to `git worktree remove --force` but not urgent, not mine to clean up
  without checking first.
- **Do NOT launch more than 3 concurrent background agents at once** — this was an explicit user
  constraint ("No more than 3").
- **When launching a new phase-building agent, ALWAYS instruct it explicitly: "do this work
  SYNCHRONOUSLY YOURSELF, do NOT spawn another background agent/sub-task."** Earlier this session,
  agents without that instruction would spawn a NESTED background task to do the actual work, and
  that nested task's own worktree assignment would get torn down before it could act, wasting an
  entire cycle. This happened 3+ times before the explicit instruction fixed it.

## Critical recurring bugs/gotchas found this session (don't rediscover these)
1. **Curl isn't installed** in any of this project's `python:3.12-slim`-based custom service
   images. Every Docker `HEALTHCHECK` must use:
   `test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"]`
   — NOT `curl -f ...`. This bug silently marked 5 services permanently unhealthy and specifically
   blocked `orchestrator` from ever starting (its `depends_on: sim-clock: condition:
   service_healthy` could never be satisfied).
2. **Akaunting needs TWO headers on every API call, not one:**
   - `X-Company: <company_id>` (NOT a `company` header, NOT just a `company_id` query/body param)
     — without it, Akaunting's module-enabled cache permanently caches "no company → no enabled
     modules" for that request context, breaking payment-method validation specifically.
   - `Host: accounting.fakecorp.internal` — Laravel's `TrustHosts` middleware rejects the bare
     service DNS name (`akaunting`) with a 500 "Untrusted Host" error. **This was a real
     regression discovered late in this session**: `accounting-engine`'s `AkauntingClient` had
     been missing this header since Phase 15 was first built, meaning it had likely NEVER
     successfully posted a transaction outside of manual curl tests (which always happened to
     include an explicit `Host` header). Both `accounting-engine/main.py` and `kpi-engine/main.py`
     now set this header on their httpx client construction. **If you build any NEW service that
     calls Akaunting, it needs both headers too.**
3. **Wiki.js quirks:**
   - The GraphQL API is disabled by default even with a valid API key — must call
     `authentication.setApiState(enabled: true)` once via a session JWT (not API key) after
     first boot. Already done on the main live stack; a fresh isolated test stack needs it redone.
   - `pages.list`'s item type (`PageListItem`) does NOT expose `authorId`/`creatorId` — those only
     exist on `pages.single(id)`. Need a per-page follow-up query for attribution.
   - `passwordRaw` is nullable in the create-user mutation's schema but required at runtime for
     the `local` auth provider.
   - Python's `dict.get(key, default)` does NOT protect against an explicit `null` value in a
     GraphQL JSON response (only protects against a missing key) — use `dict.get(key) or {}`
     instead. This bit multiple services independently before the pattern got fixed everywhere.
4. **Zammad ticket creation always requires `customer_id`** (accepts a `"guess:<email>"`
   shorthand that resolves-or-creates the customer) — every service that creates Zammad tickets
   needs this field or gets a 422.
5. **Mattermost:**
   - Bot accounts need `channel_id` membership before they can post — team membership (granted at
     provisioning time) does NOT imply channel membership. `POST /channels/{id}/members` first
     (idempotent, safe to call every time before posting).
   - Personal-access-token creation needs `MM_SERVICESETTINGS_ENABLEUSERACCESSTOKENS: "true"` set
     via compose env var (already set on the main stack).
   - Token revocation is `POST /users/tokens/revoke` with `{"token_id": ...}` in the body — NOT
     `DELETE /users/{id}/tokens/{token_id}`, which 404s. This was silently leaking impersonation
     tokens in `human-bridge/main.py` since Phase 17 until fixed during Phase 19's work.
6. **docker-mailserver:**
   - SMTP AUTH only works on port 587 (submission), not port 25 (inbound MX) — every service that
     sends authenticated mail needs `MAILSERVER_SMTP_PORT=587`.
   - `setup email restrict <add|del|list> <send|receive> <email>` is the real CLI syntax — a bare
     `setup email restrict <email>` silently no-ops (exits 0, does nothing).
   - No native Sieve-script subcommand in the `setup` CLI — use
     `docker exec fakeco-mailserver doveadm sieve put/activate/deactivate/delete` directly.
     `doveadm sieve deactivate` does NOT take a script-name argument (passing one silently no-ops).
   - Needs at least one mail account created within 120s of container start or it shuts itself down.
7. **Traefik**: routed services need an explicit `traefik.docker.network: "pointlessprogram_net_X"`
   label matching the actual network they're on — Traefik's global
   `providers.docker.network` setting doesn't work when different routed services live on
   different networks (net_office vs net_mail vs net_dmz).
8. **Docker Compose profiles**: this project gates almost every service behind
   `profiles: [phaseN]`. When bringing up a service, you often need MULTIPLE `--profile` flags
   together (e.g. `--profile phase13 --profile phase18` for orchestrator, since it depends on
   `narrative-db-migrate` which is itself gated to phase13). Check the exact profile a service
   needs with `grep -n "profiles:" -A2 docker-compose.yml`. Also: a service's `profiles:` list can
   get added/changed by a concurrent background session's edits (this happened to `sim-clock`
   mid-session) — if a previously-working `docker compose up` command suddenly fails with
   "undefined service", re-check whether a dependency's profile list changed.

## Known remaining gaps (flagged, not yet fixed — see BUILD_LOG.md for full detail)
- **Phase 18's orchestrator**: no real `pending_actions` retry-queue or reaction→approval→
  action-item→filler priority loop (spec §4.3/§13.1) — it's a fixed sequence of scheduled-job
  checks instead. Not yet assigned to anyone.
- **Phase 24** (pay negotiation / performance review meeting types) not started — needed to close
  Phase 15's pay-cut stub and consume kpi-engine's `underperforming` flag properly.
- Phases 27, 28, 31, 32 not planned at all yet (chaos/crisis events, observability pass 2, speed
  slider full integration) — several dashboard tabs (Phase 33-37) depend on these.
- **Phase 29 (purge & snapshots)**: NOT STARTED. Explicitly the highest-risk phase in the whole
  plan — spec itself calls it the highest-blast-radius work in the entire build. Real unresolved
  design conflict: the `docker-socket-proxy`'s `EXEC=0` restriction (deliberately locked down in
  Phase 1) blocks the natural way to `pg_dump`/`mysqldump` inside appliance containers via `docker
  exec`. Needs a real design decision (likely: sidecar containers with direct DB network access
  instead of exec) before implementation starts. **Do not build this without the user's explicit
  sign-off on the approach — user was told this and has not yet given it as of this writing.**
  Also: test purge/snapshot ONLY against a disposable/throwaway environment, never the primary
  dev environment which now has real accumulated state (30+ employees provisioned, real meetings,
  real Akaunting transactions, real Zammad tickets).
- Phases 33-38 (dashboard, 5 phases + hardening) — largest remaining scope, needs an up-front tech
  stack decision (spec is silent on framework), see PLAN_REMAINING_PHASES.md's cross-cutting risks
  section.

## User's stated build order preference
20 → 23 → 19 → 30 → 29 → then 33-38. (20, 23, 19 done. 30 in flight. 29 needs sign-off first.)

## Live docker environment
Main stack has ~35+ `fakeco-*` containers running via `docker compose` from
`C:\code\PointlessProgram` (no `-p` project flag = default project name `pointlessprogram`).
Real credentials/tokens for every appliance already live in `.env` (gitignored, not on GitHub) —
a fresh clone needs a real `.env` before anything works. `.env.example` documents the expected
keys but is not fully audited against every service (flagged as a Phase 38 task).

Real DeepSeek API key is configured and working (LiteLLM proxy on `net_llm_bridge`).

## Misc
- User's GitHub repo: `https://github.com/Fr0styJ/PointlessProgram` — both `main` and `master`
  branches are kept in sync by force-pushing `master` to `main` after each merge
  (`git push origin master:main --force`) per explicit user request ("main is the primary program
  now, overwrite it").
- User explicitly does not want any of the "old" pre-this-session program data/history treated as
  precious — this session's rewritten history is authoritative.
