# Phase 29 — Purge & Snapshots: Design Document (Planning Only)

Status: **SIGNED OFF 2026-07-31 — cleared for implementation.** See "User sign-off decisions"
below for the answers to §4's open questions. This document itself is still planning only;
implementation happens in follow-up work per the phased plan in §5.

## User sign-off decisions (2026-07-31)

1. **Mandatory snapshot-before-purge**: YES. Every purge operation (scoped or full) must
   automatically trigger a snapshot save first, before any destructive step runs. Purge is
   never allowed to proceed if the pre-purge snapshot save fails. This is stricter than "just
   a confirmation phrase" — the confirmation phrase gate stays too, as a second layer, but
   the mandatory snapshot is the real safety net that makes purge always undoable.
2. **Disposable test environment**: ONE-TIME THROWAWAY, not a standing reusable harness.
   Stand it up for the Phase 29 build/test cycle (29.1-29.6), tear it down once Phase 29 is
   verified and wired into the primary stack (29.7). Do not invest in making it a persistent,
   reusable fixture.
3. **Mailserver Maildir access mechanism**: user deferred to implementer judgment.
   Decision: use a **read-only** shared volume mount into `snapshot-manager` for the save/
   snapshot path (tar the Maildir out, no write access needed or granted for that path).
   For restore, do NOT give the sidecar a live read-write mount of a running mailserver's
   Maildir — instead: stop `fakeco-mailserver` (via the already-allowed socket-proxy
   start/stop capability), mount the volume read-write only for the duration of the restore
   (untar into it while the container is stopped, so there's no live-mutation-during-restore
   risk), then restart mailserver. This keeps the sidecar's write access scoped to
   "mailserver is stopped" windows only, never during normal operation.

Sources reviewed: `important.md`, `PLAN_REMAINING_PHASES.md` (Phase 29 section),
`BUILD_LOG.md` (socket-proxy / EXEC=0 / purge / snapshot references), `docker-compose.yml`
(authoritative service list, `docker-socket-proxy` env, network topology).

---

## 1. Stateful appliance inventory (from `docker-compose.yml`, not memory)

| Appliance | Engine | Container(s) | Data location | Network(s) | Notes |
|---|---|---|---|---|---|
| Narrative DB (shared) | Postgres 16 | `fakeco-postgres` | `postgres` volume; DB `${POSTGRES_DB:-fakeco}` | `net_data` | Also hosts LiteLLM's own tracking DB in the same instance (different DB name) — dump must be schema/DB-scoped, not instance-wide, or LiteLLM spend history gets swept in unintentionally. |
| Mattermost | Postgres 16 | `fakeco-mattermost-db` (+ `fakeco-mattermost` app) | dedicated DB `mattermost` | `net_data` (db), `net_office` (app) | Separate Postgres instance from narrative DB — not the same container. |
| Zammad | Postgres 16 + Redis + Elasticsearch | `fakeco-zammad-db`, `fakeco-zammad-redis`, `fakeco-zammad-es`, plus railsserver/scheduler/websocket/nginx/init | DB `zammad`; ES index; Redis cache | `net_data` (db), `net_office` (app tier) | Multi-container appliance — restore ordering matters (db → es reindex → railsserver/scheduler/websocket → nginx). Redis/ES are caches/derived state, not source of truth, but ES needs a reindex trigger after a Postgres restore or search will be stale/wrong. |
| Wiki.js | Postgres 16 | `fakeco-wikijs-db` (+ `fakeco-wikijs` app) | DB `wikijs` | `net_data` (db), `net_office` (app) | Page content lives in Postgres, no separate file volume. |
| Nextcloud | Postgres 16 | `fakeco-nextcloud-db` (+ `fakeco-nextcloud` app) | DB `nextcloud` + Nextcloud's own data volume (uploaded files) | `net_data` (db), `net_office` (app) | Needs BOTH a DB dump and a file-volume tar — two artifacts per snapshot for this one appliance. |
| WordPress | MariaDB 11 | `fakeco-wordpress-db` (+ `fakeco-wordpress` app) | DB `wordpress` | `net_dmz` only (both containers) | Isolated on `net_dmz`, no `net_data` presence — a purge/snapshot sidecar for this one must be dual-homed onto `net_dmz`, which is `internal: true`. |
| Akaunting | MariaDB 11 | `fakeco-akaunting-db` (+ `fakeco-akaunting` app) | DB `akaunting` | `net_dmz` (db, deliberately separated from `net_data` per existing compose comment), `net_office` (app) | Same dual-homing problem as WordPress — the akaunting-db lives on `net_dmz`, not `net_data`. |
| docker-mailserver | N/A (Maildir on disk, no DB) | `fakeco-mailserver` | Maildir volume | `net_mail` (internal) | No DB dump path at all — this is a raw filesystem tar/restore problem, and `net_mail` is a third isolated internal network. |
| Roundcube | N/A (webmail client, uses mailserver's IMAP; own Postgres for prefs only) | `fakeco-roundcube` | uses shared `postgres`/`net_data` for its own small DB per `ROUNDCUBEMAIL_DB_*` | `net_mail`, `net_data` | Minor — prefs only, low priority to restore precisely. |
| Sim-clock / provisioning / accounting-engine / kpi-engine / (future purge-manager, snapshot-manager) | Postgres (shared narrative DB) | various `fakeco-*` app containers | same `fakeco` DB as narrative DB, different tables | `net_clients`/`net_office`, `net_data` | Covered by the narrative-DB dump above — not a separate dump target. |

**Key topology fact that shapes the whole design:** stateful appliances are NOT all on
one network. They span `net_data` (narrative Postgres, Mattermost/Zammad/Wiki.js/Nextcloud
DBs), `net_dmz` (WordPress DB, Akaunting DB — deliberately kept off `net_data`), and
`net_mail` (mailserver Maildir, no DB at all). All three are `internal: true` bridge
networks with no route between them except through a service explicitly multi-homed onto
more than one. **Any backup mechanism needs multi-homing onto at least `net_data` +
`net_dmz` + `net_mail` simultaneously**, which is itself a small but real security-posture
change worth calling out for sign-off (see §4).

---

## 2. Architecture options (avoiding `docker exec`)

The constraint: `docker-socket-proxy` has `EXEC: 0` explicitly set (Phase 1, deliberate,
`docker-compose.yml` lines ~209), alongside `IMAGES: 0`, `VOLUMES: 0`, `NETWORKS: 0`,
`SYSTEM: 0`, etc. Only `CONTAINERS` (list/inspect) and `POST` (start/stop/restart, per the
comment "Restricts to START/STOP/RESTART on labeled containers only") are enabled. This
document does **not** propose reverting that — it is treated as a hard constraint.

### Option A — Dedicated backup/restore sidecar(s) with direct DB network access (recommended)

One new long-lived service, e.g. `snapshot-manager` (already stubbed), multi-homed onto
`net_data`, `net_dmz`, and `net_mail`, that:
- Talks to each Postgres instance over the network using `pg_dump`/`pg_restore`
  (either shelling out to the `pg_dump` binary bundled in the sidecar's own image, or a
  pure-Python client like `psycopg2`/`asyncpg` streaming rows — see trade-off below) —
  authenticating with the same DB credentials each appliance's own compose service already
  uses (`POSTGRES_PASSWORD`, `MATTERMOST_DB_PASSWORD`, `ZAMMAD_DB_PASSWORD`,
  `WIKIJS_DB_PASSWORD`, `NEXTCLOUD_DB_PASSWORD` — all already in `.env`).
- Talks to each MariaDB instance the same way (`mysqldump`/`mysql` client or a Python MySQL
  client) using `WORDPRESS_DB_PASSWORD` / `AKAUNTING_DB_PASSWORD`.
- Talks to `docker-mailserver`'s Maildir the only way possible without `docker exec`: a
  **shared read/write Docker named volume** mounted into both `fakeco-mailserver` and the
  sidecar (mailserver already writes to a volume; mounting that same volume read-only or
  read-write into the sidecar for tar/untar is a compose-level volume share, not an exec
  call). This is the one piece that isn't "just a network connection" — flagged as an open
  question in §4.
- For **start/stop during restore** (e.g. stopping Zammad's railsserver while its DB is
  being restored), uses the **existing, already-allowed** `docker-socket-proxy`
  `CONTAINERS`+`POST` capability (start/stop/restart), which Phase 1 already verified
  works and is explicitly not blocked. No exec needed for this part at all — restart
  orchestration was never actually blocked, only in-container command execution was.

Trade-offs:
- **Blast radius if compromised:** the sidecar needs real DB passwords for every appliance
  DB, i.e. it is effectively as privileged as directly connecting to any appliance's
  database. This is a smaller blast radius than an unrestricted `docker exec` (which would
  also grant arbitrary command execution inside any container's filesystem/process space,
  not just its DB), but it is *not* small — a compromised sidecar can read/write/drop any
  appliance's entire dataset. This is the same level of access the app containers
  themselves already have (Mattermost's own container already holds `MATTERMOST_DB_PASSWORD`
  and full read/write to its own DB), so it is not a net-new privilege class, just a new
  *holder* of it.
- **Complexity:** moderate — one service, several DB client libraries (Postgres client +
  MySQL client + volume-based file tar), reusing the credential set already in `.env`.
- **Consistency guarantees:** `pg_dump`/`mysqldump` run against a live database give a
  transactionally consistent snapshot of that one database (standard tool behavior), but
  give **no cross-database consistency** — e.g. narrative DB and Akaunting DB are dumped at
  slightly different wall-clock instants, so a restore could show a narrative event
  referencing an Akaunting transaction that technically didn't "exist yet" at the
  narrative DB's dump instant. This is why sim-clock pause (§3) matters — pausing the sim
  loop during the whole multi-appliance dump/restore window is the practical way to get
  "consistent enough" snapshots without building real distributed-transaction tooling.
- **Restore ordering across dependent services:** DB restore must happen before dependent
  app containers reconnect (stop app container → restore its DB → restart app container),
  and Zammad specifically needs its Elasticsearch index rebuilt after a DB restore (ES is
  derived state, not source of truth) — this is an extra step unique to Zammad among the
  appliances inventoried in §1.

### Option B — Application-level bulk-delete/export APIs where they exist, direct DB access only as fallback

For **purge** specifically (not snapshot), several appliances already expose (or the plan
in `PLAN_REMAINING_PHASES.md` already identifies) native bulk-operation APIs: Mattermost's
`EnableAPIPostDeletion`/`EnableAPIChannelDeletion` settings, Zammad's ticket bulk-delete
API, Wiki.js's `pages.delete` GraphQL mutation. Using these instead of raw table truncation
where they exist avoids leaving each appliance's own internal caches/search indexes/
derived state stale (e.g. Wiki.js's own search index, Zammad's Elasticsearch), which a raw
`TRUNCATE` would otherwise silently corrupt from that appliance's point of view.

Trade-off vs. Option A: this only solves **purge**, not **snapshot/restore** — there is no
appliance-native "export everything as a single file, then re-import it" API for any of
these appliances that would substitute for `pg_dump`/`mysqldump`. So Option B is not a
substitute for Option A, it is a **complement**: use appliance bulk-APIs for purge where
they exist (falls back to direct-DB truncate only where no API exists, per the scope table
already sketched in `PLAN_REMAINING_PHASES.md`), and use Option A's direct-DB sidecar
specifically for snapshot/restore, which has no API-level equivalent.

### Option C — Narrow, reviewed, logged exception: re-enable `EXEC=1` only for backup-tooling containers, scoped by label

`docker-socket-proxy` supports per-container scoping via labels (this project already uses
`fakeco.managed: "true"` for the Phase 1 scope). In principle `EXEC` could be turned back
on but restricted to only containers labeled e.g. `fakeco.backup-target: "true"`, letting a
backup service `docker exec` `pg_dump` inside each DB container using its own image's
bundled `pg_dump` binary (avoiding the need to install every DB client library in one
sidecar image).

Trade-off: **not recommended.** `docker-socket-proxy`'s label-based scoping (per its own
docs) filters by container name/image, not by "which command was run" — turning `EXEC` on
for a labeled container does not mean "only pg_dump can run," it means "any command can run
inside that container," including a shell. This reopens exactly the class of risk Phase 1's
`EXEC=0` decision was made to close, for a marginal convenience gain over Option A (skip
installing DB client libraries). Listed here only for completeness/rejection, not as a
live proposal — flagged explicitly so the user can override this recommendation if they
disagree.

**Recommendation: Option A (dedicated sidecar with direct DB network access) for
snapshot/restore, combined with Option B (appliance-native bulk-delete APIs, falling back
to direct truncate) for purge.** Reasoning: Option A doesn't touch the Phase 1 security
decision at all, reuses credentials that already exist in `.env`, and the "sidecar holds DB
passwords" risk is not a new privilege class since the app containers already hold the same
passwords.

---

## 3. Purge / snapshot / restore workflow

### Trigger mechanism
- Manual only for v1, matching the pattern every other custom service in this repo already
  uses (`POST /rollup/run` on kpi-engine, etc.): `purge-manager` exposes one endpoint per
  scope (see table in `PLAN_REMAINING_PHASES.md` §Phase 29, item 1) plus one
  `POST /purge/full`; `snapshot-manager` exposes `POST /snapshot/save` and
  `POST /snapshot/restore`.
- Scheduled/automatic snapshotting (e.g. nightly) is explicitly **out of scope for v1** —
  flagged as a future enhancement once the manual path is proven safe, not something to
  build now.
- Both full-purge and restore require a typed-confirmation phrase in the request body
  (e.g. `{"confirm": "PURGE EVERYTHING"}`), checked server-side before any destructive call
  fires — this is the same gate `PLAN_REMAINING_PHASES.md` already specifies, called out
  again here because it's the only thing standing between an accidental API call and
  irreversible data loss.

### Snapshot storage location/format
- New named Docker volume, e.g. `snapshot_storage`, mounted into `snapshot-manager` only
  (the compose file's `net_data` comment already anticipates this: "Shared PostgreSQL
  (incl. Akaunting's own DB, snapshot storage)" — though Akaunting's DB is actually on
  `net_dmz`, not `net_data`, so that comment is slightly inaccurate and worth fixing
  whenever this volume is actually added).
- Format: one directory per snapshot, named `<sim-time-tag>_<wall-clock-timestamp>/`,
  containing: `narrative.sql` (pg_dump of the shared Postgres `fakeco` DB, custom format
  `-Fc` for faster selective restore), `mattermost.sql`, `zammad.sql`, `wikijs.sql`,
  `nextcloud.sql` + `nextcloud_files.tar`, `wordpress.sql`, `akaunting.sql`,
  `mailserver_maildir.tar`, plus a `manifest.json` recording sim-clock state at capture
  time, the snapshot trigger's wall-clock time, and a checksum per file.
- Retention: no automatic pruning in v1 — manual deletion only, since automatic deletion of
  backups is itself a data-loss risk surface not worth automating before the manual path is
  proven trustworthy. Disk usage monitoring/alerting for this volume is a fair follow-up
  item, not a v1 requirement.

### What "purge" resets to
Two distinct operations, not to be conflated:
- **Scoped/full purge** resets to an **empty or hardcoded-seed state** — e.g. roster resets
  to migration 003's original seed set, company_directives resets to a hardcoded default row
  — this is a "wipe and reseed," not a restore-from-snapshot.
- **Restore** loads a **previously captured snapshot** — a different, separate operation
  from purge, sharing only the "stop containers, mutate state, restart containers" shape.
`PLAN_REMAINING_PHASES.md` already treats these as separate concerns (purge-manager vs.
snapshot-manager, two services); this document keeps that split.

### Orchestrator / sim-clock pause during purge/restore
- Before any purge or restore operation begins, `purge-manager`/`snapshot-manager` calls
  sim-clock's existing `/set_speed` (or a dedicated `/pause`) endpoint (already verified
  working per `important.md`) to bring sim time to a full stop.
- `orchestrator`'s tick loop must check a "sim is paused for maintenance" flag (new, small)
  before firing any scheduled job — this prevents a mid-purge orchestrator tick from, e.g.,
  trying to post a Mattermost message for an employee whose relationship rows were just
  truncated, or attempting to write a narrative event to a Postgres table mid-restore.
  Recommend a narrow, explicit flag (`system_maintenance_mode` row/table or reuse
  `company_directives`) rather than relying on sim-clock speed=0 alone, since orchestrator's
  tick loop and sim-clock's speed setting are logically separate concerns today.
- After purge/restore completes, unpause sim-clock and clear the maintenance flag.
- **Container stop/start ordering during restore** (per §1's per-appliance dependency
  notes): stop app-tier containers (Zammad railsserver/scheduler/websocket/nginx, Wiki.js,
  Nextcloud, WordPress, Akaunting, Mattermost) before their DB restore begins, restore the
  DB, then restart the app tier — using the already-allowed socket-proxy START/STOP/RESTART
  capability, not `docker exec`. Zammad additionally needs its Elasticsearch index rebuilt
  after restore (a Zammad-specific API call, not a generic DB step).

---

## 4. Open risks and questions requiring explicit user sign-off

1. **Irreversible data loss is the core risk of this entire phase, by design.** Purge and
   restore are both, definitionally, operations that destroy the current state. There is no
   way to build this phase without that risk existing. Sign-off needed on: is the typed-
   confirmation-phrase gate sufficient, or does the user want a second factor (e.g. a
   mandatory automatic snapshot-before-purge, so a purge is always undoable)? This document
   does not assume an answer — recommend the user decide before implementation.
2. **Testing must never run against the live dev stack.** This environment currently has
   20+ provisioned employees, real Akaunting transactions, real Zammad tickets, real
   meetings/narrative history accumulated this session. Any test of scoped purge, full
   purge, or restore **must** run against a disposable environment — either a separate
   Docker Compose project name (`docker compose -p fakeco-test ...`, with its own `.env`
   using different DB passwords/volume names so it cannot accidentally share volumes with
   the primary stack) or an isolated git worktree. Sign-off needed: does the user want this
   disposable environment built as a one-time throwaway, or as a standing, reusable
   "phase-29 test harness" that persists across the build/test/iterate cycle? The latter is
   more setup work up front but avoids rebuilding it for every test iteration.
3. **Mailserver Maildir access requires a shared volume mount, not a network connection**
   — this is architecturally different from every other appliance in §1 (which are all
   solved by a network-reachable DB). Sign-off needed: is a read/write shared Docker volume
   between `fakeco-mailserver` and `snapshot-manager` an acceptable pattern, or does the
   user want a narrower mechanism (e.g. read-only mount for snapshot, and restore goes
   through mailserver's own `setup` CLI restart-with-restored-volume-swap instead of a
   live read/write share)?
2b. **Multi-homing the sidecar onto `net_data` + `net_dmz` + `net_mail` simultaneously** is
   itself a topology change worth flagging — today no single service crosses all three of
   those internal networks. This doesn't violate any stated security rule but is a new
   shape in this compose file and should be called out explicitly rather than silently
   introduced when Phase 29 is actually implemented.
4. **Credential/permission assumptions:** the sidecar needs every appliance DB password
   already in `.env` (`POSTGRES_PASSWORD`, `MATTERMOST_DB_PASSWORD`, `ZAMMAD_DB_PASSWORD`,
   `WIKIJS_DB_PASSWORD`, `NEXTCLOUD_DB_PASSWORD`, `WORDPRESS_DB_PASSWORD`,
   `AKAUNTING_DB_PASSWORD`). No new appliance accounts are assumed to be needed — this
   reuses existing DB-level credentials, not appliance API tokens. Confirm this assumption
   is acceptable (i.e., the user is fine with one service holding every appliance's raw DB
   password, rather than, e.g., per-appliance read-only backup DB users being created as a
   narrower-privilege alternative — that would be extra setup work but reduces blast radius
   further; flagging as an option, not a recommendation, since it adds meaningful scope).
5. **Roster purge ordering** (already flagged in `PLAN_REMAINING_PHASES.md` as "the
   trickiest scope"): de-provisioning appliance accounts must happen *before* truncating
   the `employees` row that names them, across potentially 6+ appliances per employee.
   Confirm whether partial failure mid-deprovision (e.g. Zammad succeeds, Mattermost times
   out) should roll back the whole roster purge, retry, or proceed and report a partial-
   failure summary — this needs a decision, not just an implementation.
6. **`system_audit_log` exclusion** from both purge and snapshot/restore is already agreed
   in the plan (BUILD_LOG.md line ~1450 confirms "Audit log excluded from snapshot capture/
   restore entirely — stays continuous independent of snapshots") — carried forward here as
   a confirmed constraint, not an open question, so it isn't lost when this doc is used as
   the implementation reference.

---

## 5. Phased build + test plan

1. **Phase 29.0 — Sign-off.** Get explicit user answers to all six items in §4 before
   writing any code. Do not proceed past this step without them.
2. **Phase 29.1 — Disposable test environment.** Stand up the isolated Compose
   project/worktree agreed in §4 item 2, with its own `.env` (different DB passwords,
   different volume/project name so it cannot collide with the primary stack's volumes).
   Verify it boots cleanly and independently before any purge/snapshot code exists.
3. **Phase 29.2 — Snapshot-manager save path only.** Build just the dump side (Postgres +
   MariaDB dumps + mailserver Maildir tar via shared volume) against the disposable
   environment. Verify each dump file is valid/non-empty and manifest.json is correct.
   No restore, no purge yet.
4. **Phase 29.3 — Snapshot-manager restore path, round-trip test.** Save a snapshot,
   deliberately mutate data significantly (add/delete rows across several appliances),
   restore, then diff every appliance's state against the pre-mutation baseline for each
   appliance in §1. This is the single most important test in the whole phase — a restore
   that silently loses or corrupts data is worse than no restore capability at all.
5. **Phase 29.4 — Purge-manager, scoped purge, one scope at a time.** Build and test each
   scope from `PLAN_REMAINING_PHASES.md`'s checkbox list independently against the
   disposable environment, confirming each scope is isolated from the others (purging
   "Tickets" must not touch "Chat," etc.) before moving to the next scope.
6. **Phase 29.5 — Full purge + typed confirmation gate.** Build the full-purge endpoint
   that composes the already-verified scoped purges, plus the confirmation-phrase check.
7. **Phase 29.6 — Sim-clock/orchestrator pause integration.** Wire the maintenance-mode
   flag and sim-clock pause/resume calls described in §3, test that a mid-purge orchestrator
   tick genuinely no-ops rather than erroring or writing partial state.
8. **Phase 29.7 — Only after 29.1-29.6 all pass against the disposable environment** does
   this get wired into the primary dev environment's `docker-compose.yml` (new services
   added, profile gating per existing convention) and exercised there — read-only /
   dry-run verification first (e.g. confirm a snapshot save works and produces a valid
   manifest) before ever running a real purge or restore against the primary environment's
   accumulated state.

---

*End of Phase 29 design document. No implementation code, compose changes, or service
directories were created as part of producing this document.*
