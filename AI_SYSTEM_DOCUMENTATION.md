# AI_DOC_ROOT

**DICT**
[FC]=FakeCo Real Appliances simulation
[CP]=Docker Compose topology/control plane
[DB]=narrative PostgreSQL state
[AP]=self-hosted business appliance
[SV]=custom FastAPI service
[OR]=orchestrator continuity/chaos scheduler
[HB]=human-bridge + reaction/deliverable worker
[SC]=simulation clock/time
[LLM]=LiteLLM tier/fallback gateway
[EM]=employee roster/personality identity
[NW]=isolated Docker network boundary
[MG]=migration/schema evolution
[UI]=React/FastAPI control dashboard
[OB]=Prometheus/Loki/Grafana observability
[PR]=Principal human operator

## File: /.env.example
**Deps:** [CP],[AP],[SV],[LLM],[UI],[PR]
**State:** declarative secret/config template; real `.env` prohibited

`contract -> PRINCIPAL_EMAIL,PRINCIPAL_NAME; DEEPSEEK_API_KEY,ANTHROPIC_API_KEY,OPENAI_API_KEY,LOCAL_LLM_BASE_URL,LOCAL_LLM_MODEL; POSTGRES_HOST,POSTGRES_PORT,POSTGRES_DB,POSTGRES_USER,POSTGRES_PASSWORD; MAILSERVER_DOMAIN,MAILSERVER_HOSTNAME,POSTMASTER_EMAIL; ROUNDCUBE_DB_PASSWORD,ROUNDCUBE_DES_KEY; MATTERMOST_DB_PASSWORD,MATTERMOST_ADMIN_USER,MATTERMOST_ADMIN_PASSWORD,MATTERMOST_ADMIN_EMAIL,MATTERMOST_SITE_URL; ZAMMAD_DB_PASSWORD,ZAMMAD_ADMIN_USER,ZAMMAD_ADMIN_PASSWORD,ZAMMAD_ADMIN_EMAIL; WIKIJS_DB_PASSWORD,WIKIJS_ADMIN_EMAIL,WIKIJS_ADMIN_PASSWORD; AKAUNTING_DB_PASSWORD,AKAUNTING_ADMIN_EMAIL,AKAUNTING_ADMIN_PASSWORD,AKAUNTING_COMPANY_NAME,AKAUNTING_STARTING_CASH_BALANCE,AKAUNTING_COMPANY_ID,AKAUNTING_PUBLIC_URL; NEXTCLOUD_ADMIN_USER,NEXTCLOUD_ADMIN_PASSWORD,NEXTCLOUD_DB_PASSWORD; WORDPRESS_DB_PASSWORD,WORDPRESS_ADMIN_USER,WORDPRESS_ADMIN_PASSWORD,WORDPRESS_ADMIN_EMAIL; TECHNITIUM_ADMIN_PASSWORD; LITELLM_MASTER_KEY,LITELLM_DATABASE_URL; GRAFANA_ADMIN_USER,GRAFANA_ADMIN_PASSWORD; SPEED_MULTIPLIER; TRAEFIK_DASHBOARD_PASSWORD; MAILSERVER_BOT_SECRET; FAKECORP_DOMAIN; DASHBOARD_AUTH_USER,DASHBOARD_AUTH_PASSWORD`
`defaults -> POSTGRES_HOST=postgres;POSTGRES_PORT=5432;POSTGRES_DB=fakeco;MAILSERVER_DOMAIN=fakecorp.internal;MAILSERVER_HOSTNAME=mail.fakecorp.internal;MATTERMOST_SITE_URL=http://mattermost.fakecorp.internal;AKAUNTING_COMPANY_NAME=FakeCo;SPEED_MULTIPLIER=1.0;FAKECORP_DOMAIN=fakecorp.internal;AKAUNTING_COMPANY_ID=1;AKAUNTING_PUBLIC_URL=http://accounting.fakecorp.internal`

**RATIONALE**
^R1: Empty secret stubs prevent credential publication; Compose required-variable syntax supplies fail-closed startup for critical values. Template historically lagged service contracts; Phase 38 requires systematic audit.

## File: /.gitignore
**Deps:** [CP]
**State:** declarative exclusion policy

`ignore -> .env,*.env.local,*.env.production,volumes/,data/,secrets/,keys/certs,snapshots/,OS/editor/Python/Node artifacts,logs/,tmp/,temp/,dashboard/static/`

**RATIONALE**
^R1: Persistent appliance state, snapshots, credentials, generated frontend, and local runtime products remain outside Git; `.env.example` remains tracked contract.

## File: /BUILD_LOG.md
**Deps:** [FC],[CP],[DB],[AP],[SV],[OR],[HB],[SC],[LLM],[EM],[NW],[MG],[UI],[OB],[PR]
**State:** authoritative reverse-chronological verification/fix journal; status header current through reaction adapters

`status -> phases 1..23+27..37 built/runtime-verified; phase24 absent; phase32 deferred; phase38 incomplete`
`history -> phase0 scaffold;1 topology/security;2+11+31 [OB];3 DNS/router;4 mail;5 chat;6 tickets;7 wiki;8 Nextcloud/WordPress;9 accounting;10 [LLM];12 [SC];13 [DB];14 [EM] provisioning;15 accounting engine;16 meetings;17 [HB];18 [OR];19 PTO;20 relationships;21 rival;22 customers;23 KPI;27 outage/retry;28 crises;29 purge/snapshot;30 branding;33..37 [UI]`
`post-phase fixes -> healthchecks curl/urllib mismatch; mail Date header; Zammad customer_id/login/fqdn/websocket/init; Wiki.js GraphQL required fields+locale cloud loss; Akaunting Host+X-Company+payment_method+duplicate admin; Mattermost membership/token revoke; Roundcube DB init; LLM JSON truncation retry; pg_restore rc classification; structured ASGI errors; narrative deliverables validation/WebDAV parent creation/backoff; 50 personas; chat/email/Zammad/Wiki reactions+retry`
`truth precedence -> executable code/schema/current entries > stale earlier entries/header snapshots`

**RATIONALE**
^R1: Every phase demanded live appliance/API verification; container health alone insufficient. Entries preserve failed assumptions and workarounds for future regression diagnosis.
^R2: Timestamps are non-monotonic in places due parallel worktree merges; section ordering remains newest-first intent, not strict chronology.
^R3: Historical “stub/incomplete/blocked” entries describe state at that timestamp; later entries supersede without deleting evidence.

## File: /Future_Plans.md
**Deps:** [SC],[UI],[OR],[HB]
**State:** deferred design

`phase32 -> [UI] 0.1x..10x slider + presets => [SC].set_speed; cadence audit across [OR]/meeting/[HB]/external-world; 1x behavior regression baseline; cost projection; worker-scale removed`
`current -> [SC] API exists; [UI] slider disabled+Coming Soon`

**RATIONALE**
^R1: User explicitly deferred speed integration; accelerating simulated time must not multiply behavior/LLM call rates. Wall-time retry/backoff and sim-time narrative cadence require separate treatment.

## File: /PHASE29_PLAN.md
**Deps:** [CP],[DB],[AP],[NW],[OR],[SC],[PR]
**State:** planning record; implementation supersedes options

`decision -> mandatory pre-purge snapshot; one-time disposable verification environment; snapshot-manager direct DB TCP sidecar; Maildir/shared-volume archive; no docker exec; socket-proxy container start/stop only; full/scoped typed confirmations`
`snapshot -> PG custom dumps(narrative schema excluding immutable audit,LiteLLM excluded,Mattermost,Zammad,Wiki.js,Nextcloud)+MySQL dumps(WordPress,Akaunting)+Maildir/Nextcloud files tar+manifest SHA256`
`restore -> maintenance=true => stop apps => restore => restart => maintenance=false`

**RATIONALE**
^R1: `EXEC=1` cannot be command-scoped and violates socket lockdown; direct DB clients avoid broad remote execution.
^R2: Maildir has no DB; shared volume is the narrow practical exception.
^R3: Mandatory snapshot converts purge into recoverable action; live stack never used for destructive verification.

## File: /PHASES.md
**Deps:** [FC],[CP],[DB],[AP],[SV],[UI]
**State:** canonical phased plan; completion claims require BUILD_LOG corroboration

`phases -> 0 scaffold;1 topology;2 [OB] slice;3 DNS/Traefik;4 mail;5 Mattermost;6 Zammad;7 Wiki.js;8 Nextcloud+WordPress;9 Akaunting;10 [LLM];11 [OB];12 [SC];13 [DB];14 roster;15 accounting;16 meetings;17 [HB];18 [OR];19 PTO;20 relationships;21 rival;22 customers;23 KPI;24 pay negotiation/performance;25 digest;26 ambient;27 outages;28 crises;29 purge/snapshot;30 branding;31 [OB];32 speed;33..37 [UI];38 hardening`
`completion -> 1..23,27..31,33..37 done;24 absent;25/26 behavior partially distributed/not independently evidenced;32 deferred;38 incomplete`

**RATIONALE**
^R1: Build order isolates infrastructure and deterministic accounting before LLM narrative complexity; each phase has exit criteria and logging discipline.
^R2: Open questions section superseded by SPEC_CLARIFICATIONS.md.

## File: /PLAN_PHASES_27_28_31_32.md
**Deps:** [OR],[CP],[OB],[SC],[UI]
**State:** signed plan; 27/28/31 implemented,32 deferred

`phase27 -> all outbound action types idempotent pending_actions; socket-proxy allowlist; sim-time success narrative+wall-time retries`
`phase28 -> trigger scenario/custom crisis => priority thread+forced crisis_response meeting+optional expense approval`
`phase31 -> reuse admin datasource credentials; Grafana dashboards for business/system/LLM state`
`phase32 -> Future_Plans.md`

**RATIONALE**
^R1: Idempotency spans all actions, not only money, preventing duplicate side effects after outages.
^R2: Crisis QOL favors externally forced relevant attendee list over generic selection.

## File: /PLAN_PHASES_33_38_DASHBOARD.md
**Deps:** [UI],[SV],[DB],[AP],[OB],[PR]
**State:** signed dashboard architecture; 33..37 implemented;38 pending

`shape -> React+Vite+TS SPA + thin FastAPI BFF; aggregation/proxy only; SSE live feeds; Basic Auth whole SPA/API except /health`
`tabs -> Simulation+LLM+Narrative;HR+Payroll+Accounting;External+KPI+Direction;Chaos+Data+Branding;Settings; /tv;Errors;DeepLinks;log-tail`
`purgeUX -> Settings danger-zone+nuclear styling+last snapshot+4-step confirmation`
`disabled -> pay cuts until phase24;speed slider Coming Soon;worker-scale omitted`
`phase38 -> README,first-boot,error-state/env hardening`

**RATIONALE**
^R1: SPA selected for graphs/live feeds; heavier framework unnecessary; BFF prevents browser coupling to heterogeneous appliance APIs.
^R2: Basic Auth is intentionally minimal but prevents unauthenticated destructive controls on host-published management UI.

## File: /PLAN_REMAINING_PHASES.md
**Deps:** [FC],[SV],[UI]
**State:** historical expansion; phases19,20,23,29,30,33..37 now complete;38 pending

`plan -> PTO;relationships;KPI;purge/snapshot;branding;dashboard;hardening`
`conflicts -> “to build/not started” language stale; BUILD_LOG+code supersede`

**RATIONALE**
^R1: Preserved implementation/verification intent and risks despite completion-state staleness.

## File: /SPEC_CLARIFICATIONS.md
**Deps:** [FC],[DB],[AP],[OR],[SV]
**State:** authoritative amendments

`decisions -> approvals:{approver_employee_id?,approver_is_principal}; payroll:Akaunting aggregate+per-employee [DB]; lead:role_tier/is_lead deterministic tenure fallback [PR]; pay-cut:manual only; mail:closed relay+local external-sender spoof; review:cold-start skip; crisis requester:[PR] employee; audit:excluded snapshots/restores/purges; narrative origin:+external; roster:invented placeholder; Traefik:[NW] clients+office+mail+dmz+mgmt; local [LLM]:unspecified fallback; managers:independent [SV],dashboard thin gateway`

**RATIONALE**
^R1: Resolves all 13 PHASES open questions; must not be reopened as ambiguity.

## File: /bugs.md
**Deps:** [HB],[LLM],[UI]
**State:** open-gap tracker; no confirmed current bug recorded

`fixed -> chat/email/Zammad/Wiki Principal reactions; bounded retries; Nextcloud MKCOL; artifact validation; deliverable backoff`
`gaps -> phase24;phase32;phase38`
`invariant -> artifact generation iff action_items.deliverable_type non-null`

**RATIONALE**
^R1: Fixed defects migrate to BUILD_LOG; this file remains concise current-state queue.

## File: /docker-compose.yml
**Deps:** [CP],[AP],[SV],[NW],[DB],[LLM],[OB],[UI]
**State:** stateful deployment graph

`[NW] -> net_clients,net_office,net_mail,net_dmz,net_data,net_llm_bridge,net_mgmt; internal isolation by network; Traefik multi-homed; [LLM] sole intended internet egress bridge ^R1`
`volumes -> postgres_data,snapshot_storage,mailserver_{data,config,state,logs},roundcube_db,mattermost_{config,data,logs,plugins,client_plugins,db},zammad_{storage,db,es},wikijs_db,nextcloud_{data,db},wordpress_db,akaunting_db,technitium_data,traefik_data,prometheus_data,grafana_data,loki_data,litellm_db,sim_clock_data`
`core -> postgres;docker-socket-proxy(GET=1,POST=1,CONTAINERS=1,EXEC=0,NETWORKS=0 safety); cadvisor;node-exporter;prometheus;Technitium:5380;Traefik:80,8080`
`[AP] -> mailserver+Roundcube;Mattermost+DB;Zammad DB/memcached/redis/ES/init/rails/scheduler/websocket/nginx;Wiki.js+DB;Nextcloud+DB;WordPress+DB;Akaunting+DB`
`platform -> [LLM]+litellm_db;Loki+Promtail+Grafana:3000;[SC];narrative-db-migrate;provisioning;accounting-engine;kpi-engine;branding-manager;meeting-simulator;[HB];[OR];external-world;snapshot-manager;purge-manager;[UI]:8090`
`profiles -> staged phase gates; service may carry prerequisite+feature profiles; explicit profiles required for startup`
`health -> DB-native probes; [SV] HTTP /health via Python urllib where slim image lacks curl; dependency conditions order migrations/readiness`
`routing -> fakecorp.internal host rules; host access through Traefik; [UI] direct host port 8090`

**RATIONALE**
^R1: Business appliances lack general internet access; only [LLM] may reach providers. Network membership expresses least privilege, while host exposure does not grant outbound egress.
^R2: Socket proxy prevents mounting Docker socket into custom services; EXEC disabled because labels cannot restrict commands.
^R3: Fixed container names simplify appliance integrations/chaos but require disposable-project overrides to avoid collision.
^R4: Compose contains exact secrets/env bindings; `.env` intentionally uninspected and undocumented.

## File: /fakeco-real-appliances-BUILD-PROMPT.md
**Deps:** [FC],[CP],[DB],[AP],[SV],[OR],[HB],[SC],[LLM],[EM],[NW],[UI],[OB],[PR]
**State:** foundational product/build specification

`principle -> real OSS [AP] own business data/UI/API; custom code coordinates,never recreates substitute CRUD apps`
`memory -> [DB] threads/events/meetings/actions/reactions/approvals/audit/directives; origin separation ai|human|external`
`continuity priority -> [PR] reactions > approvals > meetings/actions > ambient; durable idempotent retries`
`simulation -> relationships,meetings,direction,hire/fire,accounting/payroll,external rival/customers,KPI/reviews/digest,chaos,purge/snapshot,PTO,flavor,branding,/tv,speed`
`LLM -> centralized tier aliases+fallbacks+cost logging+token efficiency; deterministic logic outside [LLM]`
`network -> segmented [NW],DNS+Traefik routing,socket proxy,no uncontrolled egress`
`deployment -> single Compose,healthchecks,persistence,env template,observability,build log,phased verification`

**RATIONALE**
^R1: “Real Appliances” avoids fake UI/data duplication; simulation value comes from agents operating actual tools.
^R2: [PR] actions dominate autonomous work to preserve responsiveness and human control.
^R3: Simulated time controls narrative chronology; rates/cost require separate calibration.

## File: /important.md
**Deps:** [FC],[CP]
**State:** stale compaction handoff dated 2026-07-31; operational gotcha archive

`preserve -> worktree merge conflict discipline; BUILD_LOG newest-first+UTF-8 safety; migration-number collision checks; max3 agents historical user constraint; healthcheck/Akaunting/Wiki/Zammad/Mattermost/mail/Traefik/profile gotchas`
`stale -> commit/worktree/phase30-in-flight/current-state claims superseded by Git+BUILD_LOG`

**RATIONALE**
^R1: Valuable failure memory remains despite obsolete operational snapshot; never treat commit hash or in-flight list as current.

## File: /narrative-db/Dockerfile
**Deps:** [DB],[MG]
**State:** stateless migration image

`python:3.12-slim + requirements.txt + migrate.py + migrations/ -> CMD python migrate.py`

## File: /narrative-db/README.md
**Deps:** [DB],[MG]
**State:** partially stale directory guide

`intent -> persistent narrative/time/roster/additive schema; migration runner; additive numbered SQL`
`conflict -> early migration inventory/count superseded by 001..015`

**RATIONALE**
^R1: README began as phase scaffold; actual migration directory is authoritative.

## File: /narrative-db/migrate.py
**Deps:** [DB],[MG],asyncpg
**State:** stateful one-shot migrator

`database_url() -> DATABASE_URL || POSTGRES_* composition`
`wait_for_db(url:str,retries=30,delay=2) -> Connection || RuntimeError`
`ensure_migrations_table(conn) => +schema_migrations(filename PK,checksum,applied_at)`
`sha256(path) -> hex`
`run_migrations() -> 0 => sorted *.sql transaction execution+checksum ledger || 1`
`existing filename+same checksum -> skip; existing+different checksum -> abort`

**RATIONALE**
^R1: Immutable checksums prevent silent mutation of applied history; additive follow-up migration required for any correction.
^R2: Per-file transaction prevents partial schema application; lexical zero-padded filenames define order.

## File: /narrative-db/migrations/001_sim_clock.sql
**Deps:** [DB],[SC],[MG]
**State:** singleton schema

`sim_clock(id=1 PK,sim_time timestamptz,last_wall_checkpoint float8,speed_multiplier float8 CHECK 0.1..10); seed id=1`

## File: /narrative-db/migrations/002_narrative_core.sql
**Deps:** [DB],[MG],[PR],[EM]
**State:** core narrative schema

`narrative_threads(id,title,department,status open|resolved|archived,summary,created_at,updated_at)`
`narrative_events(id,thread_id FK SET NULL,employee_id deferred FK,source_type chat|email|ticket|wiki|meeting|system,source_ref,origin ai|human|external,content,created_at)`
`meetings(id,thread_id FK SET NULL,meeting_type standup|cross_functional|pay_negotiation|performance_review|crisis_response,attendee_ids int[],transcript jsonb,decisions jsonb,created_at)`
`action_items(id,thread_id/meeting_id FK SET NULL,owner_employee_id deferred FK,description,due_at,status open|done|overdue|orphaned,created_at,completed_at)`
`pending_reactions(id,event_id FK CASCADE,target_employee_id deferred FK,reaction_type,status pending|done,created_at,processed_at)`
`pending_approvals(id,request_type,requester_employee_id deferred FK,approver_employee_id?,approver_is_principal,amount,payload,status pending|approved|rejected,created_at,resolved_at; XOR approver constraint)`
`system_audit_log(id,actor,action,target_type,target_id,details jsonb,created_at)`
`company_directives(id,content,version,is_current,created_by,created_at); seed default`

**RATIONALE**
^R1: Employee FKs added after roster table avoids migration cycle.
^R2: Audit is intentionally independent/immutable across purge/snapshot.

## File: /narrative-db/migrations/003_employees.sql
**Deps:** [DB],[EM],[MG]
**State:** roster+benchmark schema/placeholder seed

`employees(id,first_name,last_name,display_name,email UNIQUE,department,job_title,role_tier ic|lead,is_principal,status active|on_pto|terminated,personality_summary,base_pay_cents>=0,hire_date,terminated_at,mattermost_user_id,zammad_user_id,wikijs_user_id,nextcloud_user_id,wordpress_user_id,created_at,updated_at)`
`+ deferred FKs narrative_events/action_items/pending_reactions/pending_approvals -> employees`
`seed -> 21 placeholder [EM],7 departments,exact lead intent,[PR] included`
`market_benchmark(department,role_tier,benchmark_pay_cents,updated_at,UNIQUE department+role_tier); seed`

**RATIONALE**
^R1: Placeholder roster explicitly authorized; stable IDs support appliance mapping and narrative references.
^R2: Pay stored integer cents; appliance payroll remains aggregate.

## File: /narrative-db/migrations/004_additive_schemas.sql
**Deps:** [DB],[EM],[MG]
**State:** additive subsystem schema

`pto_calendar(id,employee_id FK CASCADE,start_sim_time,end_sim_time,reason,created_at,CHECK end>start)`
`employee_relationships(id,a,b FK CASCADE,relationship_type ally|rival|mentor|neutral,affinity -100..100,notes,updated_at,UNIQUE unordered intent,CHECK a<b)`
`customers(id,company_name,contact_name,email UNIQUE,status prospect|active|churned,assigned_sales_rep_id/support_rep_id FK SET NULL,monthly_value_cents>=0,akaunting_transaction_id,created_at,updated_at)`
`kpi_snapshots(id,snapshot_date,entity_type employee|department,entity_id,metric,value,details jsonb,created_at,UNIQUE date/entity/metric)`

## File: /narrative-db/migrations/005_customers_seed.sql
**Deps:** [DB],[MG]
**State:** idempotent placeholder data

`seed -> 6 prospects with fake external identities/value; ON CONFLICT(email) DO NOTHING`

## File: /narrative-db/migrations/006_phase19_pto.sql
**Deps:** [DB],[EM],[MG]
**State:** additive

`employees + backup_approver_id FK employees SET NULL; partial index non-null`

## File: /narrative-db/migrations/007_branding.sql
**Deps:** [DB],[EM],[MG]
**State:** additive

`employee_branding(id,employee_id UNIQUE FK CASCADE,avatar_asset_id,updated_at)`

## File: /narrative-db/migrations/008_phase29_purge_snapshots.sql
**Deps:** [DB],[MG]
**State:** maintenance/audit schema

`system_maintenance_mode(id=1,enabled,reason,started_at); seed false`
`snapshot_purge_log(id,operation snapshot|restore|purge,scope,name,status started|completed|failed,details jsonb,started_at,completed_at)`

**RATIONALE**
^R1: Global maintenance singleton makes [OR] no-op during destructive cross-appliance operations.

## File: /narrative-db/migrations/009_phase27_pending_actions.sql
**Deps:** [DB],[OR],[MG]
**State:** durable retry schema+constraint widening

`pending_actions(id,action_type,payload jsonb,idempotency_key UNIQUE,status pending|processing|done|failed,attempts,next_retry_at,last_error,created_at,updated_at,completed_at)`
`narrative_events.source_type + outage;origin + system`

**RATIONALE**
^R1: Unique idempotency covers all outbound action classes; wall-clock retry scheduling avoids sim-speed retry storms.

## File: /narrative-db/migrations/010_phase28_crisis.sql
**Deps:** [DB],[MG]
**State:** additive+defensive constraint repair

`narrative_threads + priority smallint default0; index DESC`
`narrative_events constraint accepts outage/system regardless prior migration state`

## File: /narrative-db/migrations/011_kpi_engine_config.sql
**Deps:** [DB],[MG]
**State:** singleton runtime config

`kpi_engine_config(id=1,review_approval_mode bool,updated_at,updated_by); seed false`

**RATIONALE**
^R1: Replaces restart-only env toggle with live dashboard control; env remains first-boot default contract.

## File: /narrative-db/migrations/012_deliverable_action_items.sql
**Deps:** [DB],[HB],[MG]
**State:** additive artifact contract

`action_items + deliverable_type wordpress_post|nextcloud_file?,deliverable_url?,deliverable_fulfilled_at?; partial index`

**RATIONALE**
^R1: Non-null type is sole generation trigger; prohibits random/periodic filler and ties every artifact to narrative work.

## File: /narrative-db/migrations/013_deliverable_retry_state.sql
**Deps:** [DB],[HB],[MG]
**State:** bounded retry extension

`action_items + deliverable_attempts default0,next_retry_at,last_error,failed_at; status + failed; retry partial index`

**RATIONALE**
^R1: Persistent exponential backoff survives restart and prevents repeated paid calls; provider downtime does not consume attempts.

## File: /narrative-db/migrations/014_personality_profiles.sql
**Deps:** [DB],[EM],[MG]
**State:** reusable persona schema

`personality_profiles(id PK,short_label,profile jsonb,created_at,updated_at)`
`employees + personality_profile_id FK SET NULL; index`

**RATIONALE**
^R1: Stable randomly balanced assignment gives existing/future hires reusable detailed identity without embedding profile blobs per employee.

## File: /narrative-db/migrations/015_reaction_retry_state.sql
**Deps:** [DB],[HB],[MG]
**State:** bounded reaction retry extension

`pending_reactions + attempts default0,next_retry_at,last_error,failed_at; status pending|done|failed; retry partial index`

**RATIONALE**
^R1: Delivery marked done only after appliance success; retries bounded/idempotent; PTO/provider pause does not burn attempts.

## File: /narrative-db/requirements.txt
**Deps:** [DB]
**State:** dependency pin floor

`asyncpg>=0.29.0`

## File: /sim-clock/Dockerfile
**Deps:** [SC]
**State:** runtime image

`python:3.12-slim + curl + pip requirements + main.py -> uvicorn :8000`

**RATIONALE**
^R1: curl added after Compose healthcheck blocked dependents on slim image; current cross-service convention often uses urllib instead, but this image retains curl compatibility.

## File: /sim-clock/README.md
**Deps:** [SC],[DB]
**State:** concise service guide

`formula -> sim_time += wall_elapsed*speed_multiplier; API set_speed 0.1..10; all time-aware decisions read [SC]; business-hours policy belongs consumers`

## File: /sim-clock/main.py
**Deps:** [SC],[DB],FastAPI,asyncpg
**State:** singleton persistent clock+background ticker

`get_pool() -> asyncpg.Pool || RuntimeError`
`init_schema(pool) => CREATE/seed sim_clock id=1`
`tick(pool) => sim_time += max(0,wall_now-last_wall_checkpoint)*speed_multiplier; checkpoint=wall_now`
`ticker_loop(pool) => tick every TICK_INTERVAL_SECONDS; log+continue on error`
`lifespan(app) => pool(min2,max5)+schema+ticker; shutdown cancel+close`
`GET /health -> {status,service}`
`GET /clock -> ClockState(sim_time,last_wall_checkpoint,speed_multiplier,wall_time_utc) || 500`
`POST /set_speed(speed_multiplier:float[0.1,10]) -> previous/new/sim_time/message => flush elapsed @ old speed transactionally,set new speed`
`GET /sim_time -> {sim_time ISO,speed_multiplier} || 500`
`Exception handler -> JSON ERROR log+500 JSON; HTTPException unaffected`
`config -> DATABASE_URL || POSTGRES_*;TICK_INTERVAL_SECONDS=1;SPEED_MULTIPLIER=1;MIN=.1;MAX=10`

**RATIONALE**
^R1: Flush-before-switch prevents lost/double-counted interval at speed boundary.
^R2: Negative wall elapsed becomes zero to tolerate host clock skew.
^R3: DB singleton is cross-service time authority; wall time appears only checkpoint/retry/diagnostic contexts.
^R4: JSON exception re-log makes uncaught failures queryable by Loki `level=ERROR`; uvicorn may also emit plaintext traceback.

## File: /sim-clock/requirements.txt
**Deps:** [SC]
**State:** dependency floors

`fastapi>=0.115.0;uvicorn[standard]>=0.30.0;asyncpg>=0.29.0;pydantic>=2.0.0`

## File: /orchestrator/Dockerfile
**Deps:** python:3.12-slim, docker-cli, curl, `/orchestrator/requirements.txt`
**State:** immutable image; runtime-stateful [SV]

`build() -> uvicorn(main:app@0.0.0.0:8000)`
`apt(docker-cli,curl) => [OR] Docker-CLI Sieve control + diagnostics ^R1`
`HEALTHCHECK -> absent@image || [CP]-level healthcheck`

**RATIONALE**
^R1: [OR] PTO Sieve path requires `docker exec fakeco-mailserver doveadm sieve`; docker-mailserver setup CLI lacks Sieve mutation; Debian package must be `docker-cli`, not heavyweight/incorrect `docker.io`. Direct socket mount remains broader than Phase-27 socket-proxy lockdown; inherited Phase-19 compromise.

## File: /orchestrator/README.md
**Deps:** [SC], [DB], [EM], [HB], accounting-engine, meeting-simulator, external-world, kpi-engine
**State:** descriptive; partially stale

`declared([OR]) -> priority continuity + roster/[SC]/PTO/relationships + reachability + pending_actions + deterministic jobs`
`actual([OR]) -> fixed tick job sequence + reactive/scheduled dispatch + chaos APIs; no strict per-[EM] reaction>approval>action-item>filler consumer ^R1`
`boundary -> independently deployable [SV]; not manager monolith`

**RATIONALE**
^R1: README/spec claim exceeds implementation. BUILD_LOG records Phase-18 gap: [HB] consumes reactions separately; [OR] sequentially schedules jobs. Phase-27 later added `pending_actions`; old `important.md` statements declaring it absent are stale.

## File: /orchestrator/main.py
**Deps:** FastAPI, asyncpg, httpx, Docker Engine API, docker CLI, [DB], [SC], meeting-simulator, accounting-engine, kpi-engine, external-world, Mattermost, docker-mailserver
**State:** stateful singleton loop + [DB]-persisted audit/retry/PTO state + process-local pause state

`cfg -> DATABASE_URL|POSTGRES_{USER,PASSWORD,HOST,PORT,DB}; SIM_CLOCK_URL; MEETING_SIM_URL; ACCOUNTING_ENGINE_URL; KPI_ENGINE_URL; EXTERNAL_WORLD_URL; DOCKER_SOCKET_PROXY_URL; PENDING_ACTIONS_RETRY_SECONDS=60; PENDING_ACTIONS_MAX_ATTEMPTS=20; ORCHESTRATOR_TICK_INTERVAL=60; STANDUP_SIM_HOUR=9; CROSS_DEPT_INTERVAL_DAYS=14; PERF_REVIEW_INTERVAL_DAYS=30; PAYROLL_INTERVAL_DAYS=14; STALE_THREAD_DAYS=2; APPROVAL_REMINDER_DAYS=1; PTO_DAILY_PROBABILITY=.01; PTO_MIN_GAP_DAYS=45; PTO_DURATION_MIN_DAYS=3; PTO_DURATION_MAX_DAYS=7; MAILSERVER_CONTAINER=fakeco-mailserver; MAILSERVER_DOMAIN=fakecorp.internal; MATTERMOST_URL; MATTERMOST_ADMIN_TOKEN`
`CHAOS_ALLOWED_CONTAINERS -> {fakeco-mattermost,fakeco-zammad-nginx,fakeco-wikijs,fakeco-akaunting,fakeco-nextcloud,fakeco-wordpress} ^R1`
`get_sim_time() -> ISO datetime@[SC] || wall UTC ^R2`
`SocketProxyClient._post_action(name,action) -> {container,action,status_code} || HTTP error; accept 200|204`
`SocketProxyClient.{start,stop,restart}(name) -> Docker POST /containers/{name}/{action}`
`SocketProxyClient.list_containers(allowlist) -> client-filtered states@GET /containers/json?all=true`
`get_last_run(conn,job) -> system_audit_log.detail.sim_time|null`
`record_run(conn,job,sim_time,detail) => system_audit_log(action=orchestrator_job_ran)`
`_is_connection_error(exc) -> bool(httpx connect/connect-timeout/read-timeout/pool/network only) ^R3`
`_make_idempotency_key(type,target,payload) -> SHA256(canonical JSON)`
`queue_pending_action(conn,type,target,method,url,json,error,key?) => pending_actions UPSERT(key); attempts++; pending|retrying; wall next_retry_at`
`handle_outbound_failure(...) => queue(connection fault) || ERROR-log(application fault)`
`process_pending_actions(conn,sim_time) => due wall-time retries; GET|POST; attempts<=20; done|retrying|failed; success + narrative_events(origin=system,source_type=outage,success-time [SC]) ^R4`
`is_employee_on_pto(conn,employee_id,sim_time) -> bool@pto_calendar`
`_doveadm_sieve(email,action,script?) -> docker exec ${MAILSERVER_CONTAINER} doveadm sieve ... || failure`
`_build_vacation_sieve(emp,window) -> Sieve vacation script`
`_set_mattermost_pto_status(emp,end) => custom_status(emoji=palm_tree,text=Out of Office,expires_at=end)`
`_clear_mattermost_pto_status(emp) => custom_status clear`
`maybe_schedule_pto(conn,sim_time) => once/sim-day deterministic per-[EM] RNG; active [EM]; last-window gap>=45d; duration random[3,7]d; p=.01; +pto_calendar`
`maybe_apply_pto_effects(conn,sim_time) => idempotent start Sieve+Mattermost; end deactivate/delete Sieve+clear status+fire_catching_up_burst ^R5`
`fire_catching_up_burst(conn,emp,sim_time) => open/reuse narrative thread + action items/events for post-PTO backlog`
`maybe_run_standups(conn,sim_time) => weekday + hour>=9 + once/dept/day + POST meeting/run(type=standup,department)`
`maybe_run_cross_functional(conn,sim_time) => elapsed>=14 sim-days + POST meeting/run(type=cross_functional)`
`maybe_run_performance_reviews(conn,sim_time) => elapsed>=30 sim-days; GET pending eligibility; skip [EM]@PTO; POST meeting/run(type=performance_review,target)`
`maybe_run_payroll(conn,sim_time) => elapsed>=14 sim-days + POST accounting-engine/payroll/run`
`maybe_run_books_audit(conn,sim_time) => once/sim-day + POST accounting-engine/audit/run`
`maybe_run_kpi_rollup(conn,sim_time) => once/sim-day + POST kpi-engine/rollup/run(range previous sim-day)`
`maybe_run_external_world(conn,sim_time) => POST external-world/betacorp/check + customers/check`
`maybe_handle_stale_threads(conn,sim_time) => open/in_progress inactive>=2 sim-days + POST meeting/run(type=crisis_response,thread_id,context)`
`maybe_remind_pending_approvals(conn,sim_time) => old pending approvals + reminder side effect/audit`
`tick_once() => maintenance-mode no-op || get [SC] => process retries -> PTO schedule/effects -> meetings -> payroll/audit/KPI/external/stale/reminders ^R6`
`tick_loop() -> every ORCHESTRATOR_TICK_INTERVAL wall-seconds; process-local pause skip; exception isolation`
`lifespan() => +asyncpg pool +httpx client +SocketProxyClient +background tick task; shutdown cancel/close`
`ExceptionHandler(Exception) -> JSON 500 + structured ERROR traceback ^R7`
`GET /health -> {status:ok,service:orchestrator}`
`GET /tick/status -> paused,last_tick_at,paused_since`
`POST /tick/pause -> process-local paused=true`
`POST /tick/resume -> paused=false`
`POST /trigger/{job_name} -> standup-all|cross-functional|payroll|books-audit|crisis-check|performance-reviews|pto-schedule|pto-effects || unknown_job`
`_validate_chaos_container(name) -> canonical allowlisted fakeco-*|""`
`GET /chaos/appliances/status -> allowlisted Docker state || 502`
`GET /chaos/outages?limit=50 -> narrative_events(source_type=outage)`
`POST /chaos/appliances/{name}/{stop|start|restart} -> Docker action || 400 allowlist || 502 proxy`
`CRISIS_SCENARIOS -> data_breach(cost=15000,depts=Engineering|Support|HR); surprise_audit(real audit,depts=Finance); viral_complaint(cost=2500,depts=Support|Marketing); custom(free text,all leads)`
`_resolve_crisis_attendees(conn,depts?) -> active relevant leads || all active leads`
`POST /chaos/trigger-event({scenario,custom_text?}) -> +priority=100 crisis thread/event => forced crisis_response meeting => optional normal expense(idempotency_key=crisis-expense:{thread}) => audit run metadata ^R8`
`GET /chaos/pending-actions -> latest 50 retry rows`

**RATIONALE**
^R1: Core infra excluded to bound blast radius; application allowlist + socket-proxy `CONTAINERS=1,POST=1,EXEC=0` defense-in-depth. Zammad nginx name corrects stale prior `fakeco-zammad` bug.
^R2: Wall-time fallback preserves scheduler liveness during [SC] outage but weakens deterministic sim semantics; logged warning.
^R3: Reachable 4xx/5xx indicates logic/data defect, not outage; queueing it would create useless retries.
^R4: Appliance outage physical duration uses wall clock; narrative records fresh success [SC]. Idempotency applies ALL action types per user decision. Retry transport supports only GET/POST stored payloads.
^R5: docker-mailserver has no setup Sieve command; `doveadm sieve put/activate/deactivate/delete` required. `deactivate` accepts no script argument; passing one silently no-ops—verified bugfix. Mattermost ephemeral-token revocation uses `POST /users/tokens/revoke`, not nonexistent DELETE route. End effects keyed through audit state for repeat safety.
^R6: `system_maintenance_mode` protects purge/restore from concurrent mutation. Loop remains fixed sequence, not original strict per-employee continuity priority queue; README/spec conflict retained as open gap.
^R7: Uvicorn/Starlette bare exceptions otherwise emit plaintext, invisible to Loki `level=ERROR`; duplicate plaintext server traceback remains expected middleware behavior.
^R8: Crisis costs reuse normal approval path; surprise audit narrates actual accounting response, never invented values. Current code chooses first forced attendee as expense requester, conflicting SPEC_CLARIFICATIONS #7 requiring [PR] employee/account ID—verified design conflict.

## File: /orchestrator/requirements.txt
**Deps:** PyPI
**State:** declarative

`runtime -> fastapi>=0.115; uvicorn[standard]>=0.30; asyncpg>=0.29; httpx>=0.27; pydantic>=2`

**RATIONALE**

## File: /meeting-simulator/Dockerfile
**Deps:** python:3.12-slim, `/meeting-simulator/requirements.txt`
**State:** immutable image; runtime-stateful [SV]

`build() -> uvicorn(main:app@0.0.0.0:8000)`
`HEALTHCHECK -> absent@image || [CP]-level healthcheck`

**RATIONALE**

## File: /meeting-simulator/README.md
**Deps:** [LLM], [DB], Mattermost, Wiki.js, [EM]
**State:** descriptive; materially stale

`declared_types -> standup|cross_functional|pay_negotiation|performance_review|crisis_response`
`implemented_generation -> generic schema all named types; specialized selection standup|cross_functional|pay_negotiation|performance_review|crisis_response`
`privacy_claim(pay_negotiation,performance_review) -> not implemented; current run publishes every meeting to Mattermost+Wiki.js ^R1`
`Phase24_claim -> stale; Phase24 not built; performance-review outcome pay wiring logged stub`
`static_prefix_cache_claim -> [LLM] cache enabled, prompt assembled each call; byte-identical static-prefix guarantee not explicit`

**RATIONALE**
^R1: README says HR-private exclusion; `run_meeting()` unconditionally publishes all types. Future implementation must suppress external minutes for HR-sensitive types.

## File: /meeting-simulator/main.py
**Deps:** FastAPI, asyncpg, httpx, [DB], [SC], [LLM], Mattermost API v4, Wiki.js GraphQL
**State:** stateful clients/pool; transactional meeting persistence

`cfg -> DATABASE_URL|POSTGRES_*; LITELLM_URL=http://litellm:4000; LITELLM_MASTER_KEY; MATTERMOST_URL; MATTERMOST_BOT_TOKEN; MATTERMOST_TEAM_ID; SIM_CLOCK_URL; ACCOUNTING_ENGINE_URL; WIKIJS_URL; WIKIJS_ADMIN_TOKEN`
`LLMClient.chat(messages,model=heavy,max_tokens=2500) -> POST /chat/completions temperature=.7 -> content`
`MattermostClient.get_or_create_channel(name,display,purpose) -> existing team channel || +public channel`
`MattermostClient.post_message(channel,text,props?) -> post_id`
`WikiJSClient.graphql(query,vars?) -> data || HTTP/GraphQL error`
`WikiJSClient.create_page(path,title,content,description,tags) -> pages.create(locale=en,editor=markdown,isPublished=true,isPrivate=false) ^R1`
`get_sim_time(http) -> [SC] ISO || wall UTC`
`select_attendees(conn,type,department?,target?,forced?) -> active non-PTO [EM][] ^R2`
`select(standup) -> department lead + up to 5 earliest-hired ICs`
`select(cross_functional) -> each department lead + relationship-weighted IC candidate pool; flat max truncation behavior ^R3`
`select(pay_negotiation) -> target + department lead || [PR]-proxy lead selection`
`select(performance_review) -> target + department lead`
`select(crisis_response,forced) -> exact active/non-PTO forced IDs; otherwise all leads + sampled ICs`
`score_candidate_by_relationships(candidate,selected,relmap) -> affinity sum + relation-type weights`
`fetch_relationship_map(conn) -> {(employee_id,related_employee_id):affinity}`
`decision_text(decision:any) -> str(text|decision|JSON)`
`compute_affinity_updates(decisions,attendees) -> pair delta map; same stance +5; opposing -5; bounded application`
`apply_affinity_updates(conn,updates) => employee_relationships symmetric upsert/clamp[-100,100]`
`build_meeting_prompt(conn,type,attendees,thread,sim_time,extra) -> messages(system static policy/personas/company directive/JSON schema + compact dynamic context) ^R4`
`LLM output schema -> transcript_summary; decisions[{text,stances:{attendee:agree|disagree|neutral}}]; action_items[{assignee_name,description,due_in_days,deliverable_type?:wordpress_post|nextcloud_file|null}]; outcome; short_summary`
`run_meeting(...) -> select -> [LLM] heavy/2500 -> parse JSON/fence-strip || one retry heavy/4000+concise repair || degraded parse_error object ^R5`
`run_meeting.persist => +thread if absent +meeting +action_items +relationship updates +narrative_event(origin=ai,source_type=meeting) +thread summary @transaction`
`action_item.assignee -> ILIKE name || first attendee; due=sim_time+due_in_days; deliverable_type allowlist only`
`run_meeting.publish => Mattermost channel meetings-{dept?}-{type}, 64-char cap + minutes; Wiki.js meeting-notes/{dept|cross-team}/{date}-{meeting_id} ^R6`
`performance_review.raise_recommended => log only; Phase24 pay outcome stub`
`lifespan() => pool[2..10] + [LLM]/Mattermost/Wiki clients; close all`
`ExceptionHandler(Exception) -> structured ERROR + JSON500`
`POST /meeting/run(RunMeetingRequest) -> MeetingResult || 503 clients-not-ready`
`GET /meetings/pending-performance-reviews -> active [EM], hired<wall NOW-90d, dept size>=2 ^R7`

**RATIONALE**
^R1: Wiki.js `pages.create` requires undocumented non-null `isPrivate`; omission produced GraphQL failure. API/token calls internal only.
^R2: PTO filter enforces no proactive attendance. Forced crisis list still revalidated against active/PTO state.
^R3: Phase-20 relationship weighting reuses the existing meeting [LLM] call by adding stances; zero extra spend. Known historical bug: leads+ICs flat truncation can drop every IC when department leads fill cap; confirm current cap logic before modifying.
^R4: Company direction inserted into every prompt; compact thread summary/recent context avoids full-history token growth. Persona/background data grounds each voice.
^R5: Real long crisis output truncated JSON at 2500 tokens; single 4000-token concise retry verified. Double failure persists usable degraded meeting rather than losing event.
^R6: Publish failures are warnings after DB commit; meeting remains canonical in [DB]. Contrary README, HR-private meeting suppression absent.
^R7: Eligibility uses wall `NOW()` while scheduler uses [SC], creating potential accelerated-time mismatch. Cold-start exemption required by SPEC_CLARIFICATIONS #6.

## File: /meeting-simulator/requirements.txt
**Deps:** PyPI
**State:** declarative

`runtime -> fastapi>=0.115; uvicorn[standard]>=0.30; asyncpg>=0.29; httpx>=0.27; pydantic>=2`

**RATIONALE**

## File: /external-world/Dockerfile
**Deps:** python:3.12-slim, `/external-world/requirements.txt`
**State:** immutable image; runtime-stateful [SV]

`build() -> uvicorn(main:app@0.0.0.0:8000)`

**RATIONALE**

## File: /external-world/README.md
**Deps:** [DB], [LLM], mailserver, Zammad, accounting-engine, [EM]
**State:** descriptive; mixed implemented/planned claims

`BetaCorp -> deterministic pay-gap risk + local cosmetic-external mail + resignation + [PR] flag`
`customers -> prospects/tickets + SLA churn + revenue posting`
`origin -> external`
`flavor_news claim -> absent@main.py ^R1`

**RATIONALE**
^R1: No Wiki.js/Mattermost rival-flavor generator exists in assigned source; README describes intended scope beyond current endpoints.

## File: /external-world/main.py
**Deps:** FastAPI, asyncpg, httpx, smtplib, [DB], [SC], [LLM], docker-mailserver SMTP, Zammad, accounting-engine
**State:** autonomous wall-loop + deterministic per-[SC] decision state

`cfg -> DATABASE_URL|POSTGRES_*; LITELLM_URL; LITELLM_MASTER_KEY; MAILSERVER_HOST; MAILSERVER_SMTP_PORT=587; MAILSERVER_DOMAIN; ACCOUNTING_ENGINE_URL; ZAMMAD_URL=http://zammad-nginx:8080; ZAMMAD_ADMIN_TOKEN; SIM_CLOCK_URL; BETACORP_DOMAIN=betacorp.com; BETACORP_RECRUITER_NAME=Alex Rivera; BETACORP_RECRUITER_EMAIL; JOB_OFFER_BASE_PROBABILITY=.3; JOB_OFFER_MAX_GAP_PCT=.25; RESIGNATION_GAP_PCT=.20; RESIGNATION_GRACE_SIM_DAYS=14; SUPPORT_SLA_CHURN_HOURS=48; MAILSERVER_BOT_SECRET; EXTERNAL_WORLD_TICK_INTERVAL=300`
`derive_mail_password(email) -> SHA256(MAILSERVER_BOT_SECRET+":"+email)[0:24]`
`LLMClient.chat(messages,model=cheap) -> content(max_tokens=500,temp=.9)`
`inject_email(to,display_name,display_email,subject,body,relay_email) => authenticated SMTP587 STARTTLS-if-available; cosmetic From/Reply-To; X-Sim-Origin=external-world ^R1`
`get_sim_time() -> [SC] || wall UTC`
`audit_log(conn,actor,action,detail) => system_audit_log`
`compute_offer_probability(pay,benchmark) -> 0 if gap<=0; base-linear-to-1 by .25 gap`
`run_betacorp_check(pool,llm,sim_time) -> {offers_sent,resignations,flags_raised}`
`BetaCorp RNG -> Random(int(sim_time.timestamp())); active [EM]+market_benchmark; ignore <=1% gap`
`offer => [LLM] cheap recruiting body || deterministic fallback body => local SMTP => audit betacorp_offer_sent`
`resign => gap>=20% + offer age>=14 sim-days + no raise/pay-cut audit after offer => employees.status=resigned,terminated_at=sim_time + audit`
`near_miss => gap>=10% + probability>=.5 + no pending target reaction => +pay-gap thread +pending_reactions +audit`
`run_customer_check(pool,llm,sim_time) -> active customers + Zammad open-ticket search note:{company}; age>SLA => at_risk/churn state + audit ^R2`
`generate_prospect_activity(pool,llm,sim_time) => select prospect + assigned sales/support + cheap narrative content => real Zammad ticket/customer linkage and/or local email; audit`
`revenue path -> pre-recorded customer/deal amount => POST accounting-engine/revenue; never [LLM]-invent amount`
`external_world_tick_loop() -> sleep interval => [SC] => run_betacorp_check + run_customer_check + generate_prospect_activity; exception isolation`
`lifespan() => pool + [LLM] client + background loop; shutdown cancel/close`
`ExceptionHandler(Exception) -> structured ERROR + JSON500`
`GET /health -> ok`
`POST /betacorp/check -> manual current-[SC] run`
`POST /customers/check -> customer check + prospect activity`

**RATIONALE**
^R1: Closed mail network cannot receive real internet senders; authenticated internal relay writes external-looking headers only. Port 25 auth failed historically; submission port 587 required. Appliances except [LLM] remain no-egress.
^R2: Zammad ticket POST requires `customer_id` (`guess:<email>` accepted), valid group resolution, and article type; earlier omissions prevented prospect traffic. Search-by-note/company is heuristic coupling, not customer foreign key.

## File: /external-world/requirements.txt
**Deps:** PyPI
**State:** declarative

`runtime -> fastapi>=0.115; uvicorn[standard]>=0.30; asyncpg>=0.29; httpx>=0.27; pydantic>=2`

**RATIONALE**

## File: /kpi-engine/Dockerfile
**Deps:** python:3.12-slim, `/kpi-engine/requirements.txt`
**State:** immutable image; runtime-stateful [SV]

`build() -> uvicorn(main:app@0.0.0.0:8000)`

**RATIONALE**

## File: /kpi-engine/README.md
**Deps:** Zammad, Wiki.js, Mattermost, Akaunting, accounting-engine, [DB]
**State:** descriptive; Phase25/weekly-digest stale claim

`implemented -> deterministic daily KPI rollup + deterministic review ranking/raises + live approval-mode toggle`
`not_implemented -> weekly digest selection/LLM/publish ^R1`
`Phase24 wording -> stale; formula exists, pay-negotiation/full underperformance meeting path absent`

**RATIONALE**
^R1: No weekly-digest function/endpoint exists in `main.py`; dashboard TV explicitly skipped digest because Phase25 absent.

## File: /kpi-engine/main.py
**Deps:** FastAPI, asyncpg, httpx, [DB], Zammad REST, Wiki.js GraphQL, Mattermost REST, Akaunting REST, accounting-engine
**State:** request-driven deterministic aggregator; [DB]-persisted snapshots/config/audit

`cfg -> DATABASE_URL|POSTGRES_*; ZAMMAD_URL; ZAMMAD_ADMIN_TOKEN; WIKIJS_URL; WIKIJS_ADMIN_TOKEN; MATTERMOST_URL; MATTERMOST_ADMIN_TOKEN; AKAUNTING_URL; AKAUNTING_ADMIN_EMAIL; AKAUNTING_ADMIN_PASSWORD; AKAUNTING_COMPANY_ID=1; ACCOUNTING_ENGINE_URL; KPI_REVIEW_TOP_RAISE_PCT=.05; KPI_REVIEW_SECOND_RAISE_PCT=.02; KPI_REVIEW_MIN_TENURE_DAYS=90; KPI_REVIEW_MIN_DEPT_SIZE=2; KPI_REVIEW_LOOKBACK_DAYS=30; KPI_REVIEW_UNDERPERFORM_PERCENTILE=.10; KPI_REVIEW_APPROVAL_MODE default env; KPI_WEIGHT_TICKETS_RESOLVED=1; KPI_WEIGHT_WIKI_PAGES=1; KPI_WEIGHT_CHAT_MESSAGES=.1; KPI_WEIGHT_RESOLUTION_HOURS=-.05`
`ZammadClient.get_groups() -> {group_id:name}`
`ZammadClient.get_tickets_in_range(start,end) -> paged/search tickets + articles/details as needed`
`WikiJSClient.graphql(q,v) -> data || errors`
`WikiJSClient.list_pages() -> pages.list summaries => per-id pages.single(authorId,creatorId,createdAt,updatedAt) ^R1`
`MattermostClient.get_teams() -> teams`
`MattermostClient.get_channels_for_team(team) -> channels`
`MattermostClient.get_posts_in_range(channel,start,end) -> paged posts filtered timestamps`
`AkauntingClient.__init__() -> Basic auth + Host:accounting.fakecorp.internal + X-Company:{id} ^R2`
`AkauntingClient.get_income_transactions(start,end) -> income transactions filtered dates/company`
`audit_log(...) => system_audit_log`
`get_review_approval_mode(pool) -> kpi_engine_config value || env default`
`set_review_approval_mode(pool,enabled,actor) => UPSERT config + audit`
`write_snapshot(conn,date,entity_type,entity_id,metric,value) => UPSERT kpi_snapshots unique key`
`run_rollup(pool,clients,start,end,snapshot_date?) -> deterministic rows_written`
`rollup employees -> external IDs map: zammad_user_id|wikijs_user_id|mattermost_user_id`
`rollup Zammad -> employee/department tickets_created,tickets_resolved,avg_resolution_hours`
`rollup Wiki.js -> employee/department wiki_pages_created,wiki_pages_updated; initial save not double-counted as update`
`rollup Mattermost -> employee/department chat_messages; dedupe channels across teams`
`rollup Akaunting -> Company/revenue_posted`
`rollup => audit rollup_complete`
`compute_review_candidates(pool,as_of=wallUTC) -> eligible active tenure>=90 wall-days + dept>=2 + 30d snapshots -> weighted composite -> per-dept rank ^R3`
`tier -> top ceil(n/4):+5%; next through ceil(n/2):+2%; rest:0; underperform bottom max(1,int(n*.10))`
`apply_review_raises(pool,http,as_of?) -> candidates; approval_mode=false => POST accounting-engine/payroll/raise(new_pay,reason); true => idempotent pending_approvals(review-raise:{emp}:{date}); no cuts`
`lifespan() => pool[2..10]`
`ExceptionHandler(Exception) -> structured ERROR + JSON500`
`POST /rollup/run({start?,end?,snapshot_date?}) -> rollup; default previous wall-day; client close finally`
`GET /config/review-mode -> bool`
`POST /config/review-mode({enabled,actor=principal}) => runtime DB config`
`GET /reviews/due -> ranked candidates`
`POST /reviews/run({as_of?}) -> applied|queued|skipped|candidates`

**RATIONALE**
^R1: Wiki.js `PageListItem` lacks `authorId`/`creatorId`; direct list query returned GraphQL 400. N+1 `pages.single` workaround preserves attribution correctness.
^R2: Akaunting Laravel rejects service-DNS Host as untrusted and requires company context. Both `Host` and `X-Company` are mandatory; missing headers caused historical 500/invisible transactions.
^R3: Dollar/KPI/review tiers remain code-derived; no [LLM] judgment. Negative resolution-hours weight rewards faster resolution. Wall-time SQL tenure/lookback may diverge from accelerated [SC]. Underperformance only flags; automatic cuts forbidden; Phase24 meeting path remains unbuilt.

## File: /kpi-engine/requirements.txt
**Deps:** PyPI
**State:** declarative

`runtime -> fastapi>=0.115; uvicorn[standard]>=0.30; asyncpg>=0.29; httpx>=0.27; pydantic>=2`

**RATIONALE**

## File: /litellm/README.md
**Deps:** [LLM], [NW], provider APIs, [CP]
**State:** descriptive; local fallback deferred

`gateway -> single AI generation ingress + cost/usage tracking`
`tiers -> cheap:routine/external flavor; mid:weekly digest; heavy:meetings/[PR] reactions`
`chain -> DeepSeek => Anthropic => OpenAI; local unspecified/deferred`
`token policy -> cache static prefix + small dynamic tail + compact memory`
`network -> net_llm_bridge only external route ^R1`

**RATIONALE**
^R1: Business [AP]/[SV] must not access internet; [LLM] proxy is intentional sole egress bridge. Stopping [LLM] halts paid generation while deterministic services may continue/defer.

## File: /litellm/config.yaml
**Deps:** LiteLLM Proxy, DEEPSEEK_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, LITELLM_MASTER_KEY, LITELLM_DATABASE_URL
**State:** declarative router + local process cache + usage DB

`model cheap -> cheap-deepseek(deepseek/deepseek-v4-flash) || cheap-anthropic(claude-haiku-20240307) || cheap-openai(gpt-4o-mini)`
`model mid -> mid-deepseek(deepseek/deepseek-v4-flash) || mid-anthropic(claude-3-5-haiku-20241022) || mid-openai(gpt-4o-mini)`
`model heavy -> heavy-deepseek(deepseek/deepseek-v4-pro,reasoning_effort=high,cache_control=true) || heavy-anthropic(claude-sonnet-4-5,cache_control=true) || heavy-openai(gpt-4o)`
`router.model_group_alias -> cheap:cheap-deepseek; mid:mid-deepseek; heavy:heavy-deepseek`
`router.fallbacks -> explicit ordered provider chains; num_retries=3; retry_after=5 ^R1`
`litellm.cache -> true,type=local`
`litellm.drop_params -> true ^R2`
`callbacks -> success=[]; failure=[]`
`general.master_key -> os.environ/LITELLM_MASTER_KEY`
`general.database_url -> os.environ/LITELLM_DATABASE_URL`
`general.store_model_in_db -> true`
`keys -> environment references only; no literal secrets`

**RATIONALE**
^R1: Same tier-name deployments + latency routing load-balanced across providers; missing Anthropic/OpenAI keys caused intermittent 401 instead of fallback. Distinct deployment names + alias-to-DeepSeek + explicit fallbacks enforce deterministic primary. Legacy `deepseek-chat`/`deepseek-reasoner` retired 2026-07-24; migrated to V4 Flash/Pro. Config change requires proxy restart.
^R2: Provider-specific unsupported parameters must not break cross-provider fallback. Local cache is process-local/non-durable; Redis deferred.

## File: /human-bridge/Dockerfile
**Deps:** [HB],python:3.12-slim,requirements.txt,reaction_{chat,email,wikijs,zammad}.py
**State:** image-build

`build() + /app => pip --no-cache-dir => COPY main+4 adapters => EXPOSE 8000 => uvicorn main:app 0.0.0.0:8000/info`

**RATIONALE**
^R1: adapters copied explicitly; import-time isolation retained; no browser/runtime asset layer.

## File: /human-bridge/README.md
**Deps:** [HB],[AP],[DB]
**State:** stale-partial

`scope -> [PR] activity detection@IMAP+Mattermost+Zammad+Wiki.js => narrative_events(origin=human)+pending_reactions`
`declaredDeps -> phases 4,5,6,7,13,14`
`conflict -> README phase-17 future tense; implementation additionally direct actions, 4 reaction deliveries, deliverables, directive sync, dashboard API ^R1`

**RATIONALE**
^R1: preserve stale-doc warning; source+BUILD_LOG supersede placeholder-era README.

## File: /human-bridge/requirements.txt
**Deps:** fastapi>=0.115.0,uvicorn[standard]>=0.30.0,asyncpg>=0.29.0,httpx>=0.27.0,pydantic>=2.0.0
**State:** runtime-deps

`stdlib -> SMTP+IMAP+MIME+hashing`; `external -> [SV]+[DB]+HTTP`

## File: /human-bridge/main.py
**Deps:** [HB],[DB],[EM],[SC],[LLM],[AP],asyncpg,httpx,FastAPI,SMTP,IMAP,reaction_* adapters
**State:** stateful; pool+cached principal IDs+3 background loops

`ENV -> DATABASE_URL|POSTGRES_{USER,PASSWORD,HOST,PORT,DB}; MAILSERVER_HOST; MAILSERVER_{SMTP,IMAP}_PORT; MAILSERVER_BOT_SECRET; MATTERMOST_URL|MATTERMOST_ADMIN_TOKEN|MATTERMOST_TEAM_ID; ZAMMAD_URL|ZAMMAD_ADMIN_TOKEN; WIKIJS_URL|WIKIJS_ADMIN_TOKEN; ACCOUNTING_ENGINE_URL; MEETING_SIM_URL; PRINCIPAL_{EMAIL,NAME}; WORDPRESS_URL|WORDPRESS_ADMIN_USER|WORDPRESS_ADMIN_APP_PASSWORD; NEXTCLOUD_URL|NEXTCLOUD_ADMIN_USER|NEXTCLOUD_ADMIN_PASSWORD; LITELLM_URL|LITELLM_MASTER_KEY; DETECTION_POLL_INTERVAL_SECONDS=8; DELIVERABLE_POLL_INTERVAL_SECONDS=30; DELIVERABLE_MAX_ATTEMPTS=5; DELIVERABLE_RETRY_BASE_SECONDS=30; DELIVERABLE_RETRY_MAX_SECONDS=3600; REACTION_POLL_INTERVAL_SECONDS=5; REACTION_MAX_ATTEMPTS=5; REACTION_RETRY_BASE_SECONDS=30; REACTION_RETRY_MAX_SECONDS=3600; COMPANY_DIRECTIVE_WIKI_PATH=company-direction`
`derive_mail_password(email:str)->sha256(MAILSERVER_BOT_SECRET+":"+email)[0:24] ^R1`
`get_pool()->asyncpg.Pool || RuntimeError`
`audit_log(conn,actor,action,detail)->None => system_audit_log`
`send_as_employee(from,name,to,subject,body,conn)->None => SMTP:587 AUTH+optional STARTTLS+X-Sim-Origin => audit(email_sent_as_employee) ^R2`
`post_mattermost_as_employee(mm_id,channel,msg,conn,name)->post_id => admin + ephemeral PAT => channel membership => employee post => POST /users/tokens/revoke => audit ^R3`
`_ensure_detection_tables(conn)->human_bridge_cursors(source PK,cursor_value,updated_at)`
`_get_cursor(source)->str`; `_set_cursor(source,value)->upsert`
`_get_or_create_thread(emp)->latest open departmental thread || + Human interaction thread`
`_record_human_event(emp,type,ref,summary)->None => source_ref dedupe => narrative_events(origin=human)+pending_reactions(status=pending)+audit`
`_mattermost_username_for(email)->localpart dots=>underscores lowercase`
`_resolve_employee_by_mattermost_mention(text)->active [EM] || None`
`_resolve_employee_by_email(address)->active [EM] || None`
`_resolve_employee_by_zammad_agent(id)->active [EM] || None`
`_resolve_employee_by_wiki_tag(tags)->active [EM] via emp-<id> || None ^R4`
`_resolve_principal_{mattermost,zammad,wiki}_id(http)->ID || None => process-lifetime cache`
`_poll_mattermost_once(pool)->None => [PR]-authored posts after cursor + @employee target => human event(chat,mattermost:<post-id>)`
`_poll_zammad_once(pool)->None => [PR]-authored new articles + ticket owner target => human event(ticket,zammad:<article-id>)`
`_poll_wikijs_once(pool)->None => page list+single detail + [PR] author + emp-<id> tag + ignore-revision cursor => human event(wiki,wikijs:<page-id>:<updatedAt>) ^R5`
`_imap_fetch_inbox_from_principal(mailbox,last_uid)->[(uid,raw)] => IMAP employee INBOX AUTH derived password`
`_poll_mail_once(pool)->None => each active mailbox + UID cursor + From=[PR] => human event(email,mail:<mailbox>:<uid>)`
`_detection_loop(pool)->forever => 4 pollers independently guarded => sleep DETECTION_POLL_INTERVAL_SECONDS ^R6`
`_LLMClient.is_available()->bool @ GET /health/liveliness`; `_LLMClient.generate(messages,model,max_tokens)->str @ POST /chat/completions`
`_WordPressClient.create_post(title,content,excerpt)->url => POST /wp-json/wp/v2/posts status=publish Basic/app-password`
`_NextcloudClient._ensure_collections(path)->None => recursive MKCOL; 201|405 accepted`; `_NextcloudClient.put_file(path,content)->url => WebDAV PUT ^R7`
`_generate_content_for_action_item(row,employee,thread)->{title,content,excerpt} => [LLM] JSON; strict nonempty validation; retry once corrective prompt || ValueError ^R8`
`_record_deliverable_failure(conn,row,exc)->None => attempts+1; next_retry_at=NOW()+min(base*2^(n-1),max); last_error; attempt>=max => status=failed+failed_at`
`_fulfill_one_deliverable(conn,row,llm,wp,nc,sim_time)->bool => lock/reload + owner/personality/thread context => generate only deliverable_type!=NULL => wordpress_post|nextcloud_file upload => deliverable_url+status=done+completed_at; provider unavailable=>no retry consumption ^R9`
`_deliverable_fulfillment_loop(pool)->forever => [LLM] availability gate => due open deliverables ordered id => per-row transaction => bounded retry => sleep interval`
`_record_reaction_failure(conn,row,exc)->None => bounded exponential retry fields; max=>failed`
`_process_pending_reactions_once(pool)->{found,done,pending,failed,ignored} => due pending rows; source_type dispatch chat|email|ticket|wiki; per-reaction transaction/advisory lock; [LLM]/PTO deferral no attempt consumption; delivery error=>retry state ^R10`
`_principal_reaction_loop(pool)->forever => process => sleep REACTION_POLL_INTERVAL_SECONDS`
`lifespan()->pool(min=2,max=10)+detection tables+3 tasks => cancel/await+pool.close`
`ExceptionHandler(Exception)->500 JSON => JSON ERROR+flattened traceback ^R11`
`GET /health -> {status,service}`
`POST /detection/poll-now -> per-poller ok|error`
`POST /action/reactions/poll-now -> reaction pass summary`
`GET /state/employees -> roster ordered department,hired_at`
`GET /state/threads?status -> filtered || latest50`
`GET /state/pending-approvals -> pending chronological`
`POST /action/send-email(SendEmailRequest)->sent || 404`
`POST /action/mattermost-post(MattermostPostRequest)->post_id || 404`
`POST /action/approve-expense(ApproveExpenseRequest decision=approved|rejected)->accounting-engine approve || DB reject+audit`
`_sync_directive_to_wikijs(content,version)->GraphQL result => pages.list client filter => pages.update(full required fields)|pages.create(isPrivate required) ^R12`
`POST /action/update-directive(UpdateDirectiveRequest)->{version,id,wiki_sync_error} => transaction old current false + new version current => audit => best-effort Wiki sync ^R13`
`POST /action/trigger-meeting(TriggerMeetingRequest)->meeting-simulator /meeting/run`
`POST /action/zammad-ticket(ZammadTicketRequest)->ticket_id => POST /api/v1/tickets customer_id=guess:<PR email> => audit ^R14`
`POST /action/wiki-page(WikiPageRequest)->GraphQL create => audit ^R15`
`POST /action/deliverables/poll-now -> 503 if [LLM] down; due rows => fulfillment summary`
`GET /action/deliverables/pending -> open|failed deliverables+retry diagnostics`

**RATIONALE**
^R1: deterministic bot secrets remain unstored/re-derivable; simulation-only credential model.
^R2: docker-mailserver AUTH works on submission 587, not inbound 25; TLS optional only inside isolated [NW].
^R3: Mattermost team membership != channel membership; `/posts` otherwise 403. Old DELETE token route 404 leaked PATs; real revoke endpoint POST body token_id.
^R4: no prior Wiki employee-target convention; `emp-<employee_id>` introduced as explicit deterministic routing tag.
^R5: Wiki list items omit needed author fields; detail query required. `authorId` identifies creator, not revision author; ignore cursor suppresses bridge’s own update loop.
^R6: polling chosen because Mattermost outgoing webhooks require trigger words and Zammad/Wiki webhook setup lacked simpler complete capture; durable cursors trade immediacy for robust uniform integration.
^R7: WebDAV PUT does not create parent collections; recursive MKCOL fixed repeatable 404 delivery failures; 405 means collection already exists.
^R8: Gemini-generated empty bodies exposed nominal-success corruption; semantic field validation+one corrective retry blocks empty artifacts.
^R9: narrative invariant: no random/periodic content; only explicit action_items.deliverable_type. Provider downtime pauses without spending attempts; five bounded failures prevent infinite spend/poll churn.
^R10: reaction priority precedes deliverables; transport marker+DB state recover publish-success/DB-failure races; `done` only after appliance delivery.
^R11: uvicorn plaintext ASGI tracebacks lack Loki `level`; duplicate structured ERROR enables [UI] Errors panel; explicit HTTPException remains normal FastAPI handling.
^R12: Wiki.js update demands near-full immutable field set; create additionally requires undocumented `isPrivate:Boolean!`.
^R13: [DB] directive remains source-of-truth; Wiki outage reported but cannot roll back saved business direction.
^R14: Zammad ticket creation hard-requires customer_id; `guess:<email>` resolves/creates customer.
^R15: docstring claims create/update but implementation only create; verified conflict/open gap.

## File: /human-bridge/reaction_chat.py
**Deps:** [HB],[DB],[EM],[LLM],Mattermost,httpx
**State:** one-reaction transactional adapter

`ChatReactionConfig(mm_url,admin_token,llm_url,key,model=heavy,timeout=20)`
`ChatReactionResult(id,status,post_id?,reason?)`
`build_chat_prompt(emp,post)->messages => full JSON personality+exact quoted [PR] text+prompt-injection boundary+<180 words`
`_default_generate(config,messages,http)->reply || ProviderUnavailable(transport|502|503|504) || empty ValueError`
`_fetch_original(source_ref=mattermost:<post-id>)->post || ValueError`
`_find_existing_reply(root,marker)->post_id? @ thread props.fakeco_reaction_id`
`_default_post(emp,original,msg,marker)->post_id => ephemeral PAT+channel membership+threaded post(props marker,pending_post_id)+revoke ^R1`
`process_chat_reaction(conn,id,config,...)->ChatReactionResult => advisory_xact_lock; exact row join; source/status/active/account/PTO/self guards; appliance marker repair; [LLM]; deliver; DB done ^R2`

**RATIONALE**
^R1: PAT provides real employee authorship; always-revoke finally limits credential leakage; marker creates appliance-side idempotency.
^R2: caller transaction required for advisory-lock lifetime; provider/PTO/unavailable stay pending; only successful post or discovered existing post marks done.

## File: /human-bridge/reaction_email.py
**Deps:** [HB],[DB],[EM],[LLM],IMAP,SMTP,MIME,httpx
**State:** one-reaction transactional adapter

`EmailReactionConfig(principal_email,name,mail_host,imap=143,smtp=587,secret,llm_url,key,model=heavy,max_tokens=1200)`
`mailbox_password(address)->sha256(secret+":"+address)[0:24]`
`parse_source_ref(mail:<mailbox>:<positiveUID>)->(mailbox,uid) || UnsafeSourceMessage`
`_plain_body(msg)->text[0:12000] => attachment exclusion; text/plain preference || HTML strip`
`parse_principal_email(raw,PR,employee)->ParsedPrincipalEmail => sender exact+recipient exact+loop/automation headers rejected ^R1`
`build_grounded_prompt(row,profile,email)->messages => personality+quoted untrusted source`
`build_reply_message(id,row,PRname,PRemail,original,body)->EmailMessage => Re:+stable Message-ID <reaction-id@fakecorp.internal>+In-Reply-To+References+X-FakeCo-Reaction-ID+Auto-Submitted:auto-generated`
`InternalImapSource.fetch_uid(mailbox,uid,password)->raw? @ IMAP INBOX readonly`
`InternalSmtpTransport.send(mailbox,password,msg)->None @ SMTP AUTH+best-effort STARTTLS`
`InternalLiteLLM.is_available()->bool`; `complete(...)->str || ProviderUnavailable`
`EmailReactionWorker.process_pending_reaction(conn,{id})->ReactionResult => transaction+FOR UPDATE; done/type/active/account/PTO guards; source fetch+parse; [LLM] availability+complete; SMTP; conditional DB done ^R2`
`process_email_reaction(...)->ReactionResult`

**RATIONALE**
^R1: exact origin/recipient validation plus Auto-Submitted/X markers prevents mail loops and replies to automation.
^R2: row lock serializes workers; stable Message-ID supports retry recognition; provider outage leaves queue untouched; delivery precedes done.

## File: /human-bridge/reaction_wikijs.py
**Deps:** [HB],[DB],[EM],[LLM],Wiki.js GraphQL,httpx
**State:** one-reaction transactional adapter

`WikiReactionConfig(url,token,principal_wiki_user_id,llm_url,key,model=heavy,max_tokens,timeout)`
`parse_source_ref(wikijs:<page-id>:<updatedAt>)->(id,revision) || ValueError`
`_graphql(query,variables)->dict || GraphQL/runtime error`
`_fetch_page(id)->full page{id,path,title,description,content,editor,isPublished,isPrivate,locale,authorId,updatedAt,tags}`
`build_wiki_prompt(emp,page)->messages => personality+exact page content+grounding`
`_append_follow_up(page,emp,reply,marker)->markdown => hidden marker+H2 Follow-up from <name>+role/department`
`_publish(page,content)->None => pages.update(all required fields)`
`process_wikijs_reaction(...)->Result => advisory lock; status/type/active/account/PTO; marker repair before author/revision checks; [PR] creator+exact revision+emp-id tag+self guards; [LLM]; append; publish; refetch; human_bridge_cursors wikijs:ignore:<id>; DB done ^R1`

**RATIONALE**
^R1: no verified comment mutation surface; page follow-up chosen. Exact revision avoids answering stale edits. Hidden marker repairs publish-success/DB-failure. Post-publish ignore cursor required because creator attribution cannot identify bridge revision.

## File: /human-bridge/reaction_zammad.py
**Deps:** [HB],[DB],[EM],[LLM],Zammad REST,httpx
**State:** one-reaction transactional adapter

`ZammadReactionConfig(url,admin_token,principal_email,llm_url,key,model=heavy,max_tokens=900,timeout=30)`
`parse_source_ref(zammad:<positive article-id>)->int || UnsafeTicketSource`
`build_zammad_prompt(emp,ticket,article)->messages => personality+exact article+untrusted boundary+<250 words`
`_principal_id()->id via /users/search exact email`
`_fetch_source(article_id)->(article,ticket)`
`_find_existing(ticket,marker)->article_id? via preferences.fakeco_reaction_id || hidden marker`
`_article_html(reply,marker)->escaped paragraphs+HTML marker`
`_post_as_employee(emp,ticket,body,marker)->article_id => admin PUT fresh temporary password => Basic Auth employee POST public note ^R1`
`process_zammad_reaction(...)->Result => advisory lock; status/type/active/agent/PTO; [PR] article+ticket owner+self guards; marker repair; [LLM]; post; strict conditional done update ^R2`

**RATIONALE**
^R1: Zammad has no admin-on-behalf token/article API; temporary password is only available real-employee authorship path. Bot accounts have no stable human login dependency.
^R2: ticket owner defines target; metadata+HTML dual marker handles versions stripping preferences and post/DB race.

## File: /human-bridge/tests/test_reaction_chat.py
**Deps:** reaction_chat.py,unittest,httpx.MockTransport
**State:** 5 offline async tests

`coverage -> persona+exact-message grounding; thread-marker idempotency; done-after-post; provider-down pending; PTO pending`

## File: /human-bridge/tests/test_reaction_email.py
**Deps:** reaction_email.py,unittest,MIME fakes
**State:** 6 offline tests

`coverage -> multipart plain preference; grounded prompt; Re/In-Reply-To/References/stable markers; success then idempotent; health-down pending; completion-down pending; PTO no fetch/[LLM]`

## File: /human-bridge/tests/test_reaction_wikijs.py
**Deps:** reaction_wikijs.py,unittest,httpx.MockTransport
**State:** 6 offline async tests

`coverage -> grounded attributed publish+cursor; marker idempotency; provider pending; PTO+revision deferral; non-[PR]+failed mutation no done; missing emp tag`

## File: /human-bridge/tests/test_reaction_zammad.py
**Deps:** reaction_zammad.py,unittest,httpx.MockTransport
**State:** 5 offline async tests

`coverage -> grounding+done-after-delivery; marker repair; provider/PTO pending; non-[PR]/wrong-owner rejection; source validation+HTML escaping/marker`

## File: /provisioning/Dockerfile
**Deps:** [EM],[CP],python:3.12-slim,Docker CLI
**State:** image-build

`build -> apt ca-certificates+curl+gnupg => Docker apt repo+docker-ce-cli => pip deps => COPY main+personality-library => EXPOSE8000 => python main.py serve`
`HEALTHCHECK -> python urllib http://localhost:8000/health ^R1`

**RATIONALE**
^R1: slim image lacks curl; Python healthcheck fixed permanent-unhealthy regression. Docker CLI required mailserver setup exec; privileged surface should remain constrained by topology.

## File: /provisioning/README.md
**Deps:** [EM],[AP],[DB]
**State:** partially stale

`declared -> Phase14 CLI account lifecycle+idempotent deactivate-not-delete`
`conflict -> now HTTP serve mode+personality sync/assignment+relationship seeding+reaction reassignment`

## File: /provisioning/requirements.txt
**Deps:** asyncpg>=0.29.0,httpx>=0.27.0,fastapi>=0.115.0,uvicorn[standard]>=0.30.0,pydantic>=2.0.0
**State:** runtime-deps

## File: /provisioning/main.py
**Deps:** [EM],[DB],[AP],Mattermost,Zammad,Wiki.js,docker-mailserver,Docker CLI,FastAPI
**State:** stateful HTTP service + CLI

`ENV -> DATABASE_URL|POSTGRES_*; MAILSERVER_DOMAIN; MAILSERVER_CONTAINER; MAILSERVER_BOT_SECRET; MATTERMOST_URL|ADMIN_TOKEN|TEAM_ID; ZAMMAD_URL|ADMIN_TOKEN; WIKIJS_URL|ADMIN_TOKEN; PRINCIPAL_EMAIL|NAME|MATTERMOST_PASSWORD; PERSONALITY_LIBRARY_PATH; DOCKER_HOST`
`PERSONALITY_REQUIRED_FIELDS -> id,short_label,background,core_personality,communication_style,chat_style,email_style,motivations,strengths,flaws,conflict_style,decision_style,work_habits,quirks,relationship_tendencies,response_guidance,prohibited_assumptions`
`_concise_personality(profile)->core+communication+decision+response guidance ^R1`
`sync_personality_library(conn)->count => read all *.json schema_version=1/nonempty; validate fields+unique ids; upsert personality_profiles JSONB; assign all unassigned [EM]`
`assign_personality_profile(conn,employee_id)->profile_id => stable existing || random among least-used profiles => employees.personality_profile_id+concise personality ^R2`
`MattermostClient.get/create bot|human; add_to_team; generate PAT; disable via DELETE user`
`ZammadClient.get_user_by_email; create_user(active,roles); deactivate_user(active=false)`
`WikiJSClient.graphql; get_user_by_email(search excluding isActive); create_user(deterministic local password,groups=[1],mustChange=false,welcome=false); deactivate_user ^R3`
`MailserverClient._derive_password(email)->sha256(secret:email)[0:24]`; `account_exists()->docker exec setup email list`; `create_account()->idempotent setup email add`; `restrict_account()->setup email restrict add send/receive ^R4`
`provision_employee(conn,employee,clients)->None => assign personality; mail account; Mattermost bot username=email localpart normalized + team; Zammad Agent; Wiki user; write appliance IDs/mailbox; seed relationships; per-appliance errors logged/partial progress retained ^R5`
`seed_employee_relationships(emp)->0..2 => earliest active same-dept peers; canonical min/max pair; neutral affinity=10; ON CONFLICT DO NOTHING`
`fire_employee(...)->None => employees.status=terminated+terminated_at; deactivate-not-delete 4 [AP] identities; reassign pending reactions`
`reassign_pending_reactions(emp)->None => same-dept+role_tier earliest active || any earliest active || warning; pending only`
`lifespan()->pool+personality sync+clients`; `ExceptionHandler->structured ERROR+500`
`GET /health -> ok`
`HireRequest(name,department,title,role_tier=ic)`; `_slugify_email(name)->sanitized dotted localpart@domain`
`POST /hire -> 422 tier || 409 email; pay_rate=market_benchmark||0; +active biweekly [EM]; assign profile; reuse provision_employee => {id,email,pay}`
`POST /fire -> 404 || already_terminated || fire_employee`
`CLI provision --employee-id|--all; fire --employee-id; provision-principal`
`provision-principal -> real Mattermost human account requiring password + Zammad Admin/Agent + Wiki local user + mailbox; idempotent lookups`

**RATIONALE**
^R1: concise legacy `employees.personality` prevents meeting prompts absorbing full biography; full profile preserved JSONB for reactions.
^R2: least-used random selection produces diversity for current/future roster while never changing established identity across restarts.
^R3: Wiki.js `UserMinimal.isActive` can be null despite non-null schema; omit field. local create rejects blank password despite nullable schema; deterministic password. Successful create may return user:null; refetch by email.
^R4: deactivation preserves mailbox/history; deterministic bot password avoids secret rows. Docker exec is legacy exception to socket-proxy EXEC=0 architecture.
^R5: idempotent lookups prevent duplicate [AP] accounts; partial per-appliance failures allow rerun repair rather than cross-system rollback impossible across independent appliances.

## File: /personality-library/batch-01.json
**Deps:** [EM],schema_version=1
**State:** canonical immutable-style profile data; 10 records

`profile schema -> required 18 fields; long background+core; transport styles; motivations/strengths/flaws; conflict/decision/work/quirks/relationships; response guidance; protected-trait/authority anti-assumptions`
`persona-001..010 -> The Systems Cartographer|The Practical Coordinator|The Evidence Skeptic|The Quiet Improviser|The Steady Operator|The Constructive Challenger|The Patient Craftsperson|The Curious Generalist|The Outcome Negotiator|The Grounded Experimenter`
`semantic span -> systems/cross-team mapping; coordination/momentum; evidence skepticism; resourceful creativity; operations/continuity; candid challenge; quality craft/mentoring; cross-domain curiosity; fair negotiation; bounded experimentation`

**RATIONALE**
^R1: role-neutral profiles avoid binding behavior to department/demographics; prohibited_assumptions constrain identity invention.

## File: /personality-library/batch-02.json
**Deps:** [EM],schema_version=1
**State:** canonical profile data; 10 records

`persona-011..020 -> The Trusted Bridge|The Candid Advocate|The Patient Persuader|The Customer Naturalist|The Social Catalyst|The Quiet Diplomat|The Pragmatic Partner|The Principled Negotiator|The Earnest Steward|The Diplomatic Dissenter`
`semantic span -> mediation; fairness advocacy; adaptive persuasion; customer observation; social activation; quiet conflict navigation; practical partnership; principled tradeoffs; stewardship; respectful dissent`

**RATIONALE**
^R1: each record supplies distinct chat/email/decision/conflict behavior plus bounded flaws; not cosmetic labels.

## File: /personality-library/batch-03.json
**Deps:** [EM],schema_version=1
**State:** canonical profile data; 10 records

`persona-021..030 -> The Practical Inventor|The Evidence Auditor|The Dependency Pathfinder|The Quality Steward|The Curious Debugger|The Deliberate Experimentalist|The Cautious Challenger|The Toolsmith Mentor|The Constraint Hacker|The Quiet Futurist`
`semantic span -> maintainable invention; audit rigor; dependency tracing; quality governance; debugging curiosity; controlled experiments; risk-aware dissent; reusable tooling/teaching; resource constraints; long-horizon thinking`

**RATIONALE**
^R1: technical/analytical archetypes remain cross-role and explicitly forbid invented credentials/access.

## File: /personality-library/batch-04.json
**Deps:** [EM],schema_version=1
**State:** canonical profile data; 10 records

`persona-031..040 -> The Quiet Organizer|The Patient Mentor|The Measured Climber|The Cautious Verifier|The Resilient Improviser|The Process Gardener|The Standards Builder|The Deliberate Sponsor|The Focused Finisher|The Reflective Rebuilder`
`semantic span -> organization; mentoring; sustainable ambition; verification; recovery improvisation; process improvement; standards; talent sponsorship; closure; transition learning`

**RATIONALE**
^R1: motivation/flaw combinations prevent uniformly agreeable synthetic workers; stable assignment permits relationships to accrue.

## File: /personality-library/batch-05.json
**Deps:** [EM],schema_version=1
**State:** canonical profile data; 10 records

`persona-041..050 -> Quiet Systems Connector|Constructive Spark|Reflective Craftsperson|Friendly Benchmark Chaser|Patient Consensus Builder|Pragmatic Cross-Team Operator|Curious Pattern Scout|Steady Risk Steward|Candid Collaborative Challenger|Adaptive Team Anchor`
`semantic span -> interfaces; momentum; reflective craft; metrics; consensus; execution; discovery; risk; rigorous debate; continuity through change`

**RATIONALE**
^R1: 50-profile pool supports unique current roster allocation and least-used random future hires without LLM-generated identity drift.

## File: /branding-manager/Dockerfile
**Deps:** [SV],python:3.12-slim,assets
**State:** image-build

`build -> pip deps+COPY main+assets => EXPOSE8000 => uvicorn`

## File: /branding-manager/README.md
**Deps:** [EM],[AP],[UI]
**State:** stale API assumptions

`declared -> employee_id=>avatar asset; randomize|one-all|reset; Mattermost emoji first boot`
`conflict -> Zammad/Wiki.js claimed direct avatar APIs; runtime requires impersonation/direct Wiki DB workaround ^R1`

**RATIONALE**
^R1: BUILD_LOG/live introspection supersedes aspirational README.

## File: /branding-manager/assets/generate_assets.py
**Deps:** Pillow
**State:** one-off generator; excluded runtime requirements

`_font(size)->Arial || Pillow default`
`make_avatar(name,color,letter,size=256)->RGB PNG centered white letter`
`make_emoji_circle|square|star|triangle(name,color,size=64)->RGBA transparent PNG`
`main => mkdir avatars/emoji + 10 avatars A..J colors + thumbsup circle #2A9D8F + shipit square #E63946 + star #F1A208 + alert triangle #EE6C4D + money circle #118AB2`

**RATIONALE**
^R1: simple generated assets are distinct valid appliance-upload fixtures; Pillow absent from runtime image intentionally.

## File: /branding-manager/main.py
**Deps:** [EM],[DB],[AP],Mattermost,Zammad,Wiki.js DB,FastAPI,httpx,asyncpg
**State:** stateful pool; per-request appliance clients

`ENV -> DATABASE_URL|POSTGRES_*; MATTERMOST_URL|ADMIN_TOKEN; ZAMMAD_URL|ADMIN_TOKEN; WIKIJS_URL|ADMIN_TOKEN; WIKIJS_DB_{HOST,PORT,NAME,USER,PASSWORD}; BRANDING_ASSETS_DIR; DEFAULT_AVATAR_ASSET_ID=avatar-01`
`list_avatar_assets()->sorted stems`; `list_emoji_assets()->sorted stems`
`avatar_path|emoji_path(asset_id)->Path || 404 => basename traversal guard`
`MattermostClient.set_user_avatar(id,path)->POST /users/{id}/image`; `reset->DELETE`; `create_emoji(name,path,creator)->POST multipart`; `get_first_admin_id()->/users/me`
`ZammadClient._as_employee_client(id)->(Basic client,user) => admin PUT random Brand-* password ^R1`
`ZammadClient.set_user_avatar->current-user POST /users/avatar data URLs`
`ZammadClient.reset_user_avatar->employee GET+DELETE all avatars => admin PUT image:null ^R2`
`WikiJSClient.set_user_avatar(id,path)->direct wikijs-db upsert "userAvatars"(id,data)`; `reset->DELETE`; `get_user->GraphQL ^R3`
`push_avatar_to_employee(conn,emp,asset)->result => independently push available Mattermost/Zammad/Wiki IDs; per-[AP] error isolation; always upsert employee_branding`
`reset_employee_avatar(...)->result => native/default reset each [AP]; employee_branding asset=DEFAULT`
`upload_emoji_pack(conn)->results => creator admin; name lookup; create missing; idempotent`
`lifespan()->pool min2/max10`; `ExceptionHandler->structured ERROR`
`GET /health`; `GET /assets`; `GET /assets/avatars/{id}.png`; `GET /assets/emoji/{id}.png`
`POST /branding/apply(employee_id,asset_id)->per-[AP] result || 404`
`POST /branding/bulk-apply(employee_ids,mode=randomize|apply-one-to-all|reset-to-default,asset_id?)->count+results || 422|500`; `randomize -> random.choice per employee`
`GET /branding/employee/{id}->mapping|null`
`POST /branding/emoji-pack/upload->idempotent results`

**RATIONALE**
^R1: Zammad avatar routes are current_user-only; no admin impersonation token API. Fresh bot password+Basic Auth is verified workaround.
^R2: Zammad deleting final Avatar leaves dangling `user.image` hash and old blob still serves; explicit image:null restores initials.
^R3: Wiki.js schema/controller exposes only read `/_userav/:uid`; no avatar mutation. Direct write targets exact table consumed by native route; architectural compromise requires [NW] DB access.
^R4: per-appliance errors do not block other pushes; recorded desired asset may differ from failed appliance state, intentionally visible via result details.

## File: /branding-manager/requirements.txt
**Deps:** fastapi>=0.115.0,uvicorn[standard]>=0.30.0,asyncpg>=0.29.0,httpx>=0.27.0,pydantic>=2.0.0
**State:** runtime-deps

## File: /branding-manager/assets/avatars/avatar-01.png
**Deps:** generate_assets.py; consumers branding-manager asset API+3 [AP]
**State:** binary RGB PNG 256x256; red #E63946; white A; 3100B

## File: /branding-manager/assets/avatars/avatar-02.png
**Deps:** generate_assets.py
**State:** binary RGB PNG 256x256; amber #F1A208; white B; 2696B

## File: /branding-manager/assets/avatars/avatar-03.png
**Deps:** generate_assets.py
**State:** binary RGB PNG 256x256; teal #2A9D8F; white C; 3854B

## File: /branding-manager/assets/avatars/avatar-04.png
**Deps:** generate_assets.py
**State:** binary RGB PNG 256x256; navy #264653; white D; 2641B

## File: /branding-manager/assets/avatars/avatar-05.png
**Deps:** generate_assets.py
**State:** binary RGB PNG 256x256; purple #8E44AD; white E; 935B

## File: /branding-manager/assets/avatars/avatar-06.png
**Deps:** generate_assets.py
**State:** binary RGB PNG 256x256; blue #3D5A80; white F; 882B

## File: /branding-manager/assets/avatars/avatar-07.png
**Deps:** generate_assets.py
**State:** binary RGB PNG 256x256; orange #EE6C4D; white G; 3575B

## File: /branding-manager/assets/avatars/avatar-08.png
**Deps:** generate_assets.py
**State:** binary RGB PNG 256x256; olive #606C38; white H; 887B

## File: /branding-manager/assets/avatars/avatar-09.png
**Deps:** generate_assets.py
**State:** binary RGB PNG 256x256; cyan #118AB2; white I; 804B

## File: /branding-manager/assets/avatars/avatar-10.png
**Deps:** generate_assets.py
**State:** binary RGB PNG 256x256; brown #7B2D26; white J; 1878B

## File: /branding-manager/assets/emoji/fakeco-alert.png
**Deps:** generate_assets.py; Mattermost custom emoji
**State:** binary RGBA PNG 64x64; transparent+orange triangle; 330B

## File: /branding-manager/assets/emoji/fakeco-money.png
**Deps:** generate_assets.py; Mattermost custom emoji
**State:** binary RGBA PNG 64x64; transparent+cyan circle; 355B

## File: /branding-manager/assets/emoji/fakeco-shipit.png
**Deps:** generate_assets.py; Mattermost custom emoji
**State:** binary RGBA PNG 64x64; transparent+red square; 193B

## File: /branding-manager/assets/emoji/fakeco-star.png
**Deps:** generate_assets.py; Mattermost custom emoji
**State:** binary RGBA PNG 64x64; transparent+amber 5-point star; 388B

## File: /branding-manager/assets/emoji/fakeco-thumbsup.png
**Deps:** generate_assets.py; Mattermost custom emoji
**State:** binary RGBA PNG 64x64; transparent+teal circle; 355B

## File: /accounting-engine/Dockerfile
**Deps:** python:3.12-slim, accounting-engine/requirements.txt, accounting-engine/main.py
**State:** image-build stateless

`build() -> python image + pip deps + /app/main.py`
`runtime` = `WORKDIR=/app`; `EXPOSE=8000`; `uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info`
`healthcheck` = external @[CP], not Dockerfile; Python `urllib.request` because curl absent.^R1

**RATIONALE**
^R1: Shared custom-[SV] slim-image convention; curl-based checks previously made healthy services permanently unhealthy.

## File: /accounting-engine/README.md
**Deps:** [DB], Akaunting, Zammad, Phase 15/24
**State:** documentation; partially stale

`declared` = deterministic financial math; expense routing; aggregate payroll; revenue; Books Auditor; idempotency; schema=`pending_approvals|employees|system_audit_log`; [AP]=Zammad+Akaunting.
`declared approval` = IC<=25 auto; IC>25->dept lead; lead<=500; >500->[PR]; [PR] unlimited.
`declared pay-cut` = stub until Phase24.
`stale` = wording “will contain”; `is_lead` reference while code uses `role_tier`; omits PTO delegation, API endpoints, Akaunting Host/X-Company/payment-method/category workarounds, Phase34 reject/cash/raise endpoints.^R1

**RATIONALE**
^R1: README predates implementation/fixes; `accounting-engine/main.py` + BUILD_LOG are stronger current-state evidence.

## File: /accounting-engine/main.py
**Deps:** [SV], [DB], [SC], Akaunting REST, Zammad REST, asyncpg, httpx, FastAPI, Pydantic, Decimal
**State:** stateful; pooled [DB]; per-request [AP] clients; deterministic money engine

`env` = `DATABASE_URL` || `POSTGRES_USER|POSTGRES_PASSWORD|POSTGRES_HOST|POSTGRES_PORT|POSTGRES_DB`; `AKAUNTING_URL`; `AKAUNTING_ADMIN_EMAIL`; `AKAUNTING_ADMIN_PASSWORD`; `AKAUNTING_COMPANY_ID=1`; `ZAMMAD_URL=http://zammad-nginx:8080`; `ZAMMAD_ADMIN_TOKEN`; `SIM_CLOCK_URL=http://sim-clock:8000`; `IC_AUTO_APPROVE_LIMIT=25.00`; `LEAD_AUTO_APPROVE_LIMIT=500.00`; `AKAUNTING_PAYROLL_ACCOUNT_ID`; `AKAUNTING_EXPENSE_ACCOUNT_ID`; `AKAUNTING_REVENUE_ACCOUNT_ID`; `AKAUNTING_LLM_EXPENSE_ACCOUNT_ID`; `AKAUNTING_PAYROLL_CATEGORY_ID`; `AKAUNTING_EXPENSE_CATEGORY_ID`; `AKAUNTING_REVENUE_CATEGORY_ID`; optional `AKAUNTING_PAYMENT_METHOD`.
`invariant` = all balances/thresholds/payroll/revenue arithmetic via `Decimal`/code; [LLM] absent.^R1

`AkauntingClient(base_url:str,email:str,password:str,company_id:int)`
`+__init__() -> /api BasicAuth client(headers={Host:accounting.fakecorp.internal,X-Company:<id>},timeout=30s) ^R2`
`close() -> None`
`_get_payment_method() -> str` = cached value || `AKAUNTING_PAYMENT_METHOD` || `GET /api/settings/offline-payments.methods`=>JSON decode first method code || RuntimeError(empty).^R3
`post_transaction(account_id:int,amount:Decimal,description:str,transaction_type:str='expense',contact_id?:int,category_id?:int,reference?:str,idempotency_key?:str) -> dict || HTTP error`
`payload` = company_id,type,account_id,float amount,USD/rate1,UTC wall-date,description,payment_method,number=`idempotency_key||TXN-<wall timestamp>`; optional contact/category/reference; `POST /api/transactions` BasicAuth=>created `data`.
`get_transactions(search:str='') -> list` = `GET /api/transactions?company_id&search`.
`get_accounts() -> list` = `GET /api/accounts?company_id`; Akaunting-owned `current_balance` source.

`ZammadClient(base_url:str,admin_token:str)` = `/api/v1`; header=`Authorization: Token token=<token>`; timeout=30s.
`create_ticket(title:str,body:str,customer_id:int,group:str='Users') -> dict` = `POST /tickets` article `{type:note,internal:false}`.
`add_note(ticket_id:int,note:str) -> None` = `POST /ticket_articles`; no `raise_for_status`; currently unused.^R4
`get_pool() -> asyncpg.Pool || RuntimeError`
`lifespan(app) -> pool(min=2,max=10) => close`

`get_sim_time() -> datetime` = `GET [SC]/sim_time` parse ISO || UTC wall-time + warning.^R5
`_is_on_pto(conn,employee_id,sim_time) -> bool` = active `[start_sim_time,end_sim_time)` row.
`_redirect_pto_approver(conn,approver_id,sim_time) -> (employee_id?:int,is_principal:bool)` = approver if available; active non-PTO `backup_approver_id`; || [PR].^R6
`resolve_approver(conn,requester_id,amount,sim_time?) -> (employee_id?:int,is_principal:bool)`
`rules` = inactive/missing=>ValueError; IC amount<=IC limit->self; IC amount<=lead limit->earliest-`hired_at` active same-dept lead with PTO redirect; missing lead|above lead limit->[PR]; lead<=lead limit->self/PTO redirect; lead>limit->[PR]; any other role->[PR].^R7

`submit_expense_request(pool,akaunting,zammad,requester_id,amount,description,idempotency_key?) -> {status,approval_id,akaunting_transaction_id?,auto_approved,duplicate?}`
`key` = supplied || SHA256(`expense:<requester>:<description[0:50]>:<float amount>`)[0:32].
`duplicate` = existing `pending_approvals.idempotency_key`->existing status/id.
`new` = +`pending_approvals(expense_request_ref=pending_<key16>,requester,approver,principal,amount,status=approved|pending,key)`.
`auto` = approver=self&&!principal => Akaunting expense `[AUTO-APPROVED]`; category/account env; ref=`approval:<id>` => update ref `akaunting:<tx>` + audit `expense_auto_approved`; Akaunting failure=>ERROR, row remains approved with pending ref for Books Auditor.^R8
`manual` = Zammad ticket title/body+assignment note; hardcoded `customer_id=1`; success=>ref `zammad:<ticket>` + audit `expense_queued_for_approval`; failure=>ERROR, pending row retained without live ticket.^R9

`approve_expense(pool,akaunting,approval_id,approved_by,note='') -> {status:'approved',akaunting_transaction_id}`
`guard` = DB row status=pending || ValueError.
`flow` = DB transaction + external Akaunting expense `[APPROVED by ...]`, ref=`approval:<id>` => DB status approved/ref `akaunting:<tx>` + audit `expense_approved`.^R10
`reject_expense_endpoint(req,pool) -> {status:'rejected',approval_id}` = pending row || 404; DB status rejected/updated_at wall NOW + audit `expense_rejected`; no Akaunting mutation.

`run_payroll(pool,akaunting,idempotency_key?) -> result`
`key` = supplied || `payroll:<UTC YYYY-MM-DD-HH>`.^R11
`duplicate` = `system_audit_log(action=payroll_posted,detail.idempotency_key)`->already_posted.
`employees` = all status=active; empty->no_active_employees; terminated/vacant excluded.
`total` = exact sum `Decimal(pay_rate)`; `POST` one Akaunting expense/category with description count, reference key; no employee vendor/contact records.^R12
`audit` = `payroll_posted` detail key,tx,total,count,full per-[EM] pay list; result posted.

`post_revenue(pool,akaunting,customer_id,deal_amount,description,idempotency_key?) -> result`
`key` = supplied || `revenue:customer:<id>:<float>`.
`guard` = customer exists; `abs(customers.deal_size-input)<=0.01`; audit key not already posted.^R13
`flow` = Akaunting income `[REVENUE]`, account/category, reference key => customer `akaunting_transaction_id`, `relationship_status=active` + audit `revenue_posted`.

`propose_pay_cut(pool,employee_id,proposed_pay,initiated_by='principal') -> queued_for_negotiation`
`behavior` = employee lookup; audit `pay_cut_proposed_stub`; no pay mutation; no meeting/pending_reaction actually created despite docstring wording.^R14
`run_books_audit(pool,akaunting) -> {status:'complete',corrections_made,corrections}`
`expense check` = approved rows whose ref not `akaunting:%` => post `[AUDIT CORRECTION]` expense + update ref + audit `audit_correction`; failures logged and run continues.
`payroll check` = latest 10 `payroll_posted`; missing tx-id=>report `payroll_no_akaunting_ref` only, no correction transaction/audit action of that name.^R15
`finish` = audit `audit_run_complete`.
`audit_log(conn,actor,action,detail) -> None` = INSERT JSON into append-only-intended `system_audit_log`; DB default wall time.

`_unhandled_exception_handler(request,exc) -> JSONResponse(500)` = flattened traceback via JSON logger=>[OB] `level=ERROR`; FastAPI `HTTPException`/validation unaffected; uvicorn may additionally emit plaintext traceback.^R16
`models` = `ExpenseRequest(amount>0)`; `PayrollRequest`; `RevenueRequest(deal_amount>0)`; `PayCutRequest(proposed_pay>0)`; `ApproveExpenseRequest`; `RejectExpenseRequest`.
`GET /health -> {status:ok,service:accounting-engine}`
`POST /expense/submit -> submit_expense_request`
`POST /expense/approve -> approve_expense`
`POST /expense/reject -> reject`
`GET /accounting/cash-balance -> sum(current_balance||opening_balance), per-account list`
`POST /payroll/run -> run_payroll`
`POST /revenue/post -> post_revenue`
`POST /payroll/propose-cut -> propose_pay_cut`
`POST /audit/run -> run_books_audit`
`POST /payroll/raise?employee_id&new_pay&reason -> result` = active employee ||404; `new_pay>old_pay` ||400 directing cuts to propose-cut; update pay/pay_last_changed_at/pay_last_change_reason + audit `raise_applied`; immediate/no approval/Akaunting post.^R17

**RATIONALE**
^R1: Financial correctness must remain deterministic/reproducible; [LLM] may narrate but never decide values.
^R2: Laravel TrustHosts rejects service DNS `akaunting`; configured APP_URL host required. `X-Company`, not `company` or query param, must exist before Laravel module activation; absent header caches zero payment-method listeners and causes misleading 422.
^R3: Hardcoded `offline-payments.cash.1` drifted and broke all real transaction paths; live Akaunting settings are source, one-process cache limits calls; env override supports controlled recovery.
^R4: Ticket-note helper lacks response validation; callers cannot trust delivery. No current call site.
^R5: Approval routing remains available during [SC] outage, but wall-time fallback can misclassify PTO relative to simulation time.
^R6: PTO cannot stall money approval; configured active backup first, then deterministic tier escalation.
^R7: Longest tenure resolves multiple leads without [LLM]; no lead escalates safely to [PR]. `role_tier` supersedes README `is_lead` wording.
^R8: Retaining approved DB record on [AP] failure enables later auditor repair; status says approved before ledger exists, intentionally visible discrepancy. External post lacks propagated transaction idempotency number, so crash-after-post/before-DB-update can duplicate.^R18
^R9: Zammad `customer_id` mandatory; id=1 is bootstrap assumption. Ticket failure is swallowed, leaving manual approval lacking UI surface.
^R10: DB transaction cannot atomically include external Akaunting; rollback after successful external POST can duplicate retry. Service-level precheck limits ordinary duplicates but not crash windows.
^R11: Wall-hour default approximates payroll cycle, not biweekly [SC]; explicit scheduler key required for intended cycles.
^R12: One aggregate ledger transaction mandated by clarification #2; per-[EM] detail retained in [DB].
^R13: Revenue amount locked to deal size set at thread-open; prevents closing-time hallucination/manipulation.
^R14: Human-only cuts mandated; Phase24 absent. Current function only logs stub, contrary “queues pending_reaction/opens meeting” prose.
^R15: Auditor repairs only missing approved-expense references; payroll validation shallow (presence in JSON only), latest-10 only, no Akaunting cross-check; correction POST has same external-transaction crash window.
^R16: Promtail labels JSON `level`; raw ASGI traceback previously invisible in dashboard Errors panel.
^R17: Raises intentionally frictionless; decrease rejected defense-in-depth until Phase24 negotiation.
^R18: `post_transaction(idempotency_key=...)` supports stable Akaunting `number`, but all current money call sites pass `reference` only; generated timestamp `number` weakens appliance-side idempotency.

## File: /accounting-engine/requirements.txt
**Deps:** PyPI
**State:** build manifest

`fastapi>=0.115.0`; `uvicorn[standard]>=0.30.0`; `asyncpg>=0.29.0`; `httpx>=0.27.0`; `pydantic>=2.0.0`.

**RATIONALE**
^R1: Unpinned upper versions improve install flexibility but reduce byte-reproducibility/API stability.

## File: /akaunting-init/entrypoint-idempotent.sh
**Deps:** Akaunting vendor image, bash `-e`, PHP/PDO, artisan/tinker, Apache
**State:** startup state machine; Akaunting container filesystem ephemeral + MariaDB persistent

`cwd` = `/var/www/html`.
`if .env && APP_INSTALLED=true` => unset `AKAUNTING_SETUP`; exec `/usr/local/bin/akaunting.sh --start`.^R1
`DB_HAS_DATA` = PHP PDO using `DB_HOST|DB_PORT|DB_NAME|DB_USERNAME|DB_PASSWORD|DB_PREFIX`; `SELECT 1 FROM <prefix>companies LIMIT 1`; any Throwable=>false.
`if DB_HAS_DATA=false` => exec vendor `/usr/local/bin/akaunting.sh --setup`.
`if DB_HAS_DATA=true && .env missing` => `php artisan tinker`: `Installer::createDefaultEnvFile()` + `createDbTables(...)` || exit1 + `Installer::finalTouches()`; never recreate company/admin.^R2
`filesystem prep` = `a2enmod rewrite`; +`storage/framework/{sessions,views,cache}` +`storage/app/uploads`; chmod `u=rwX,g=rX,o=rX`; chown `www-data:root`.
`final` = exec `docker-php-entrypoint apache2-foreground`.

**RATIONALE**
^R1: Vendor entrypoint reruns non-idempotent install whenever `AKAUNTING_SETUP=true`; restart against existing users crash-looped with “Not able to create a new user.” Same-container restart keeps `.env`, so skip installer entirely.
^R2: Recreated container loses `.env`/APP_KEY but keeps DB volume. Safe installer half reconstructs runtime config/migrations/permissions; company/admin transaction omitted to prevent duplicate/failure. Verified fresh install, restart, recreate.

## File: /purge-manager/Dockerfile
**Deps:** python:3.12-slim, default-mysql-client, purge-manager/requirements.txt, purge-manager/main.py
**State:** image-build stateless

`apt` = default-mysql-client; remove apt lists.
`runtime` = `/app`; pip no-cache; `EXPOSE=8000`; uvicorn info.
`mysql CLI` => Akaunting direct-MariaDB ledger purge; no Docker exec.^R1

**RATIONALE**
^R1: Akaunting lacks usable bulk-wipe API; direct DB fallback preserves socket-proxy `EXEC=0` boundary.

## File: /purge-manager/README.md
**Deps:** Phase29, [AP], [DB]
**State:** documentation; materially stale

`declared scopes` = emails/chat/tickets/wiki/meetings+narrative/accounting/external/KPI/roster/direction.
`correct` = `system_audit_log` never directly purged.
`stale confirmation` = README=`DELETE EVERYTHING`; code=`PURGE EVERYTHING`.^R1
`stale behavior` = emails claims Maildir but code only clears `employees.mailbox_address`; roster claims reset-default but code empties employees and leaves appliance accounts; dependencies/testing prose predates completed verification.

**RATIONALE**
^R1: Exact phrase is server-side safety contract; stale README value guarantees operator 400 and must not be treated authoritative.

## File: /purge-manager/main.py
**Deps:** [SV], [DB], snapshot-manager, [SC], Mattermost/Zammad/Wiki.js APIs, Akaunting MariaDB, asyncpg/httpx/mysql CLI
**State:** destructive stateful coordinator

`env` = `DATABASE_URL` || Postgres vars; `SNAPSHOT_MANAGER_URL=http://snapshot-manager:8000`; `SIM_CLOCK_URL`; `ZAMMAD_URL`; `ZAMMAD_ADMIN_TOKEN`; `WIKIJS_URL`; `WIKIJS_ADMIN_TOKEN`; `MATTERMOST_URL`; `MATTERMOST_ADMIN_TOKEN`; `AKAUNTING_DB_PASSWORD`; fixed Akaunting DB host/name/user=`akaunting-db/akaunting/akaunting`.
`SCOPE_PHRASES` = emails:`PURGE EMAILS`; chat:`PURGE CHAT`; tickets:`PURGE TICKETS`; wiki:`PURGE WIKI`; meetings_narrative:`PURGE MEETINGS AND NARRATIVE MEMORY`; accounting:`PURGE ACCOUNTING LEDGER`; external_world:`PURGE EXTERNAL WORLD`; kpi_history:`PURGE KPI HISTORY`; roster:`PURGE ROSTER`; company_direction:`PURGE COMPANY DIRECTION`; full=`PURGE EVERYTHING`.
`lifespan` = [DB] pool 1..5 + shared httpx timeout60s.
`_unhandled_exception_handler` = JSON ERROR+flattened traceback ->500; same [OB] workaround as accounting.
`ScopeRequest(confirm:str)`.
`set_maintenance_mode(pool,enabled,reason) -> UPSERT id=1,set_by=purge-manager,timestamps=wall NOW`
`pause_sim_clock_best_effort() -> POST /set_speed {speed_multiplier:0.1} || warning`
`resume_sim_clock_best_effort() -> POST /set_speed {speed_multiplier:1.0} || warning ^R1`
`log_op(pool,operation,scope,status,detail,log_id?) -> id` = INSERT started || UPDATE finished.
`mandatory_pre_purge_snapshot(scope_label) -> snapshot result || HTTP502` = `POST [snapshot-manager]/snapshot/save {label:pre_purge_<scope>}` timeout180; any reachability/non200 aborts before maintenance/data mutation.^R2

`purge_emails(pool) -> note` = `UPDATE employees SET mailbox_address=NULL`; raw Maildir and mail accounts/messages preserved.^R3
`purge_chat(pool) -> {deleted_posts,errors}` = admin Bearer; list teams; list channels; first-page channel posts; DELETE each post; catches all errors into array; channels retained; `deleted_channels` unused.^R4
`purge_tickets(pool) -> {deleted_tickets,errors}` = token auth; GET ticket list then DELETE each; catches errors; likely API pagination not traversed.^R4
`purge_wiki(pool) -> {deleted_pages,errors}` = GraphQL page list; per-id delete mutation; counts HTTP200 without checking `responseResult.succeeded`; catches errors.^R4
`purge_meetings_narrative(pool) -> counts` = DB transaction; sequential `TRUNCATE ... CASCADE` for pending_reactions,pending_approvals,action_items,narrative_events,meetings,narrative_threads; `system_audit_log|snapshot_purge_log` untouched.
`purge_accounting(pool) -> {returncode,stderr<=500}` = mysql direct DB; FK checks off; truncate transactions,documents,document_items,document_transactions; FK checks on.^R5
`purge_external_world(pool) -> counts` = transaction truncate customers,market_benchmark CASCADE.
`purge_kpi_history(pool) -> count` = truncate kpi_snapshots.
`purge_roster(pool) -> count+orphan warning` = truncate employees CASCADE; no appliance deprovision; no default reseed.^R6
`purge_company_direction(pool) -> reset note` = truncate company_directives + hardcoded version1/current row `Default company direction (post-purge reset).` created_by purge-manager.^R7
`SCOPE_FUNCS` = exact scope->implementation map.
`_run_scope(scope,pool) -> result` = mandatory snapshot => +log(started) => maintenance true => speed0.1 => scope; success log; exception=>failed log+HTTP500; finally speed1+maintenance false.
`_make_scope_endpoint(scope)` = exact phrase ||400; dynamic `POST /purge/<scope>` registration.
`POST /purge/full` = exact full phrase ||400; one mandatory full snapshot; maintenance+speed gate; ordered scopes emails,chat,tickets,wiki,meetings_narrative,accounting,external_world,kpi_history,company_direction,roster; each exception captured; status succeeded|partial_failure; always clear/resume.^R8
`GET /health -> {status:ok}`.

**RATIONALE**
^R1: [SC] has no 0 speed; 0.1 only best-effort slowdown, maintenance row is correctness gate. Previous speed is not read/preserved: every operation resets 1.0, surprising non-1x users.
^R2: User sign-off mandated snapshot before every purge; server gate independent of [UI]'s four-step “nuclear launch” confirmation.
^R3: No exec-free bulk mailbox wipe was implemented; scope name overstates result. Snapshot/restore-from-empty suggested but no endpoint automates it.
^R4: Appliance APIs preserve internal derived state better than DB truncation; however swallowed errors remain normal return values, so `_run_scope` logs `succeeded`; full purge also sees no exception and can report overall success with nonempty `errors`. Pagination/completeness guarantees absent.
^R5: Direct truncate required due absent Akaunting bulk API. Nonzero mysql return code is returned, not raised, so operation may be logged succeeded. Table set may not represent full ledger state and initialization/reseed is operator responsibility.
^R6: Plan required default roster reset/deprovision ordering; v1 intentionally empties [EM] and orphans Mattermost/Zammad/Wiki.js/mail accounts. README contradicts actual behavior.
^R7: Earlier draft invented columns; disposable live test corrected to migration002 names.
^R8: Full purge uses one pre-full snapshot, not one snapshot per internal scope; intentional composition avoids ten huge snapshots. Best-effort/partial semantics mean destructive later scopes continue after earlier failure. No distributed rollback.

## File: /purge-manager/requirements.txt
**Deps:** PyPI
**State:** build manifest

`fastapi>=0.115.0`; `uvicorn[standard]>=0.30.0`; `asyncpg>=0.29.0`; `httpx>=0.27.0`; `pydantic>=2.0.0`.

**RATIONALE**
^R1: MySQL capability comes from OS CLI, not Python package; broad minimum versions are non-reproducible.

## File: /snapshot-manager/Dockerfile
**Deps:** python:3.12-slim, PGDG apt repository, PostgreSQL client16, default-mysql-client, tar, snapshot-manager requirements/main
**State:** image-build stateless; network-fetching build

`apt bootstrap` = ca-certificates,wget,gnupg,lsb-release; +PGDG signing key/repo over HTTP repository with signed packages; +`postgresql-client-16`,default-mysql-client,tar; apt-list cleanup.
`runtime` = `/app`; pip deps; main; `EXPOSE=8000`; uvicorn info.
`healthcheck` = [CP] Python urllib; curl absent.

**RATIONALE**
^R1: Debian bookworm default client v17 emits `transaction_timeout` GUC rejected by PostgreSQL16 appliance servers; explicit v16 pin fixed restore round-trip.
^R2: Image build requires internet for PGDG key/repo/PyPI; runtime design remains isolated. Supply-chain/version pinning beyond major client absent.

## File: /snapshot-manager/README.md
**Deps:** Phase29, [DB], all stateful [AP]
**State:** documentation; materially inconsistent with code

`declared capture` = all appliance DBs, Maildir, narrative, [SC], roster,direction.
`declared exclusion` = `system_audit_log` excluded capture+restore.
`declared restore` = destructive confirmation; stop affected containers; dashboard list/save/restore/delete.
`conflict` = code full-dumps narrative [DB], therefore audit+maintenance+snapshot log included; save does not stop applications; restore phrase differs from scoped purge phrases.^R1

**RATIONALE**
^R1: README/spec intent not implemented. This is a verified safety/audit-integrity defect, not wording-only staleness.

## File: /snapshot-manager/main.py
**Deps:** [SV], [DB], [SC], Docker socket proxy, PostgreSQL16 CLI, MariaDB CLI, tar, shared named volumes, asyncpg/httpx
**State:** destructive stateful backup/restore coordinator

`env` = `DATABASE_URL`; Postgres fallback vars; `SIM_CLOCK_URL`; `SOCKET_PROXY_URL=http://docker-socket-proxy:2375`; `SNAPSHOT_ROOT=/snapshots`; `MAILDIR_PATH=/maildir`; `NEXTCLOUD_DATA_PATH=/nextcloud_data`; DB passwords=`POSTGRES_PASSWORD|MATTERMOST_DB_PASSWORD|ZAMMAD_DB_PASSWORD|WIKIJS_DB_PASSWORD|NEXTCLOUD_DB_PASSWORD|WORDPRESS_DB_PASSWORD|AKAUNTING_DB_PASSWORD`.
`RESTORE_CONFIRM_PHRASE` = `RESTORE SNAPSHOT`.
`POSTGRES_TARGETS` = narrative@postgres/<POSTGRES_DB>/<POSTGRES_USER>; mattermost@mattermost-db; zammad@zammad-db; wikijs@wikijs-db; nextcloud@nextcloud-db; each `pg_dump -Fc`.
`MYSQL_TARGETS` = wordpress@wordpress-db; akaunting@akaunting-db; each own DB/user.
`APP_CONTAINERS_BY_TARGET` = mattermost:[fakeco-mattermost]; zammad:[fakeco-zammad-nginx,fakeco-zammad-websocket,fakeco-zammad-scheduler,fakeco-zammad-railsserver]; wikijs,nextcloud,wordpress,akaunting; narrative:[]; mail=`fakeco-mailserver`.
`topology` = one privileged sidecar crosses all state [NW] + holds every DB password + RW Maildir/Nextcloud volumes; socket proxy still `EXEC=0`, only CONTAINERS+POST start/stop.^R1
`lifespan` = pool1..5 + httpx60.
`_unhandled_exception_handler` = JSON ERROR traceback->500.
`set_maintenance_mode(pool,enabled,reason,set_by) -> id=1 UPSERT`
`pause_sim_clock_best_effort -> speed0.1`; `resume_sim_clock_best_effort(speed=1.0) -> set_speed`; previous state not restored.^R2
`log_op(...) -> id` = append started/update completion in `snapshot_purge_log`.
`docker_container_action(container,action) -> bool` = POST socket-proxy `/containers/<name>/<action>?t=15`; accepts 204|304; error false; callers do not enforce false.^R3
`get_sim_state(pool) -> {sim_time,speed_multiplier} || {}`.
`sha256_of(path) -> hex` = 1MiB chunks.
`run_subprocess(cmd,env?) -> (rc,stdout,stderr)`.

`SaveRequest(label?:str)`.
`POST /snapshot/save -> snapshot result`
`name` = `<sim ISO stripped ':' '-'>_<UTC wall YYYYMMDDTHHMMSSZ>[_<label>]`; unsanitized label can add path separators.^R4
`flow` = +directory(exist_ok=false) => +log(started) => maintenance true => speed0.1.
`Postgres capture` = each target `pg_dump -Fc -f <name>.sql`; ok iff rc0+exists+size>0.
`Maria capture` = `mysqldump --single-transaction`; stdout bytes written only on rc0/nonempty.
`mail capture` = `tar -cf mailserver_maildir.tar -C /maildir .`; mailserver remains running.
`Nextcloud capture` = tar `/nextcloud_data`; missing mount=>failed.
`manifest` = snapshot_name, UTC capture, sim_state, artifacts `{size_bytes,sha256}` excluding manifest itself.
`status` = all 9 artifacts succeeded || HTTP500 detail; partial failed directory/artifacts retained; finally speed1+maintenance false.^R5
`GET /snapshot/list -> manifests+total_size_bytes` = sorted directories with manifest; malformed manifest raises unhandled500.
`DELETE /snapshot/{snapshot_name} -> deleted` = basename coercion + directory+manifest requirement; recursive delete + audit log; no typed confirmation.^R6

`RestoreRequest(snapshot_name:str,confirm:str)`.
`POST /snapshot/restore -> result`
`guard` = exact phrase ||400; `<SNAPSHOT_ROOT>/<request name>/manifest.json` exists ||404; restore path lacks basename/direct-child validation.^R7
`manifest` = parsed but artifact checksums/sizes never verified before mutation.^R8
`flow` = log started => maintenance true => speed0.1 => stop all app containers+mail; ignore stop failures; sleep2.
`Postgres restore` = each existing archive `pg_restore --clean --if-exists --single-transaction`; rc0 authoritative; missing=>failed.^R9
`Maria restore` = pipe archive into mysql; rc0 authoritative.
`Maildir restore` = untar into existing `/maildir` while mail stopped; no pre-clean.
`Nextcloud files restore` = untar into existing mounted tree while app stopped; no pre-clean.
`restart` = mail then reverse each target container list; Zammad reverse yields railsserver,scheduler,websocket,nginx; ignore failures.
`note` = Zammad Elasticsearch not reindexed; search may remain stale.
`failure` = aggregate failed=>HTTP500; non-HTTP exception logged=>HTTP500; finally only speed1+maintenance false, not guaranteed container restart if exception occurs before explicit restart block.^R10
`GET /health -> {status:ok}`.

**RATIONALE**
^R1: Direct-DB sidecar chosen over Docker exec because socket-proxy EXEC=0 is hard security boundary; privilege blast radius consolidated but narrower than arbitrary container command execution. Multi-homing is deliberate exceptional topology.
^R2: Maintenance row, checked by [OR], is real write gate; speed0.1 cannot pause. Always restoring 1.0 loses prior user speed and manifest [SC] state is informational only.
^R3: Restore consistency assumes app stop, but false stop results do not abort; DB/files can be mutated while writers remain live.
^R4: Label is operator/UI-supplied and not sanitized; path injection/nested directories possible. Snapshot core name uses both [SC] and wall time for narrative position+uniqueness.
^R5: Per-DB dumps are individually transaction-consistent, not cross-database atomic; maintenance blocks [OR] writes but other [AP]/[PR] writes remain possible. Save does not stop app tiers. Failed snapshots remain discoverability-dependent on manifest presence.
^R6: Delete is storage-only; basename prevents traversal. Lack of confirmation relies on [UI] modal and recoverability is absent after deletion.
^R7: Restore snapshot_name can contain `..`/absolute semantics depending Path composition; unlike delete, no containment guard.
^R8: Manifest hashes provide evidence but are unused during restore; corrupt/tampered artifacts discovered only through tool failure, and valid-but-altered archives may restore silently.
^R9: `--single-transaction` makes rc authoritative and prevents partial PostgreSQL restore; added after brittle `ERROR` substring heuristic. PostgreSQL client16/server16 alignment avoids PG17-only GUC.
^R10: Zammad index is derived but stale after DB restore; no exec-free reindex API. More critically, unexpected exception before restart leaves stopped apps down because restart is inside try, not finally. Tar extraction overlays rather than exact-replaces, so post-snapshot extra files can survive restore.

## File: /snapshot-manager/requirements.txt
**Deps:** PyPI
**State:** build manifest

`fastapi>=0.115.0`; `uvicorn[standard]>=0.30.0`; `asyncpg>=0.29.0`; `httpx>=0.27.0`; `pydantic>=2.0.0`.

**RATIONALE**
^R1: DB dump/restore functionality intentionally delegated to versioned OS CLIs; Python deps cover API/control state only.

## File: /dashboard/Dockerfile
**Deps:** [UI], [SV], Node20, Python3.12, Vite, uvicorn
**State:** build/runtime image

`frontend-build(node:20-slim) @ /app/frontend + package.json => npm install + frontend/** => npm run build -> /app/static`
`runtime(python:3.12-slim) @ /app + requirements.txt + main.py + /app/static`
`EXPOSE -> 8000`
`HEALTHCHECK(interval=10s,timeout=5s,retries=3,start=15s) -> urllib.request.GET(http://localhost:8000/health)==200 || unhealthy ^R1`
`CMD -> uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info`

**RATIONALE**
^R1: `python:3.12-slim` lacks curl; prior curl healthchecks permanently failed and blocked `depends_on:service_healthy`; stdlib urllib avoids extra package/image surface.

## File: /dashboard/README.md
**Deps:** [UI], [SV], [CP], [SC], [LLM], [DB], [OR], [HB], [OB], [AP]
**State:** design summary; partially stale

`[UI] -> thin BFF/API-gateway; owning [SV]/[AP] retain mutations; no control-plane monolith`
`tabs -> Simulation|LLM Status|Narrative|HR/Org|Payroll|Accounting|External World|KPI/Performance|Company Direction|Chaos|Data Management|Branding|Errors|Deep Links`
`/tv -> no-chrome spectator wall`
`[NW] placement -> net_mgmt; host access @ 8090:8000`
`declared Docker access -> socket-proxy only; actual [UI] has no Docker client/socket and proxies [OR] chaos API ^R1`
`stale claims -> worker-scale built; speed slider functional; full purge @ Data Management; pay-cut negotiation available ^R2`

**RATIONALE**
^R1: Container lifecycle allow-list/safety resides in [OR] + docker-socket-proxy; [UI] only requests start/stop/restart.
^R2: Runtime truth: worker-scale intentionally scrapped; speed slider disabled/Coming Soon because Phase32 deferred; full purge moved to Settings; pay cuts blocked pending Phase24. Treat source + BUILD_LOG as authoritative.

## File: /dashboard/frontend/index.html
**Deps:** [UI], React
**State:** static entry

`document(lang=en,charset=UTF-8,viewport=device-width/initial-scale=1) + title="FakeCo Control Dashboard" + #root + module:/src/main.tsx`

**RATIONALE**
^R1: Minimal shell; all access control server-side before HTML delivery.

## File: /dashboard/frontend/package-lock.json
**Deps:** [UI], npm
**State:** deterministic dependency lock

`lockfileVersion -> 3; requires -> true; packages -> 177`
`root -> fakeco-dashboard-frontend@1.0.0`
`locked runtime -> react@18.3.1 + react-dom@18.3.1 + react-force-graph-2d@1.29.1 + recharts@2.15.4`
`locked build -> typescript@5.9.3 + vite@5.4.21 + @vitejs/plugin-react@4.7.0`
`transitive families -> Babel7.29 + Rollup4.62 + esbuild0.21.5 platform optionals + D3 graph/chart stack + React support stack`
`platform binaries -> optional @esbuild/* + @rollup/* + fsevents; npm host selection`
`integrity/resolved metadata -> npm reproducibility/tamper checking`

**RATIONALE**
^R1: Manifest semver ranges resolve newer compatible versions than minimums; lock is actual build truth and must remain paired with package.json.

## File: /dashboard/frontend/package.json
**Deps:** [UI], React18, Vite5, TypeScript5, react-force-graph-2d, Recharts
**State:** frontend package manifest

`name -> fakeco-dashboard-frontend; private=true; type=module; version=1.0.0`
`dev() -> vite`
`build() -> tsc -b => vite build`
`preview() -> vite preview`
`runtime deps -> react ^18.3.1; react-dom ^18.3.1; react-force-graph-2d ^1.25.5; recharts ^2.12.7`
`dev deps -> @types/react; @types/react-dom; @vitejs/plugin-react; typescript; vite`

**RATIONALE**
^R1: Force graph selected for affinity topology auto-layout; ReactFlow rejected because manual coordinates add state/code without workflow semantics. Recharts supplies only standard bar visualization.

## File: /dashboard/frontend/src/api.ts
**Deps:** [UI], [SV], [DB], browser Fetch/Basic Auth
**State:** stateless typed BFF client

`apiFetch<T>(path:str,init?:RequestInit) -> Promise<T> || Error("<status> <statusText>: <body>") ^R1`
`browser Basic credentials -> native 401/WWW-Authenticate cache => same-origin fetch/EventSource auth; no JS credential store ^R1`
`SimulationStatus -> {sim_clock:SimClockState|null,sim_clock_error,tick:TickStatus|null,tick_error}`
`LlmStatus -> {provider_config:{tiers,model_group_alias,fallbacks,num_retries,error},speed_multiplier}`
`LlmSpend -> totals + trailing-1h wall burn + speed + sim-hour burn + by_model[]`
`NarrativeSummary -> threads[]+action_items[]+pending_reactions[]+pending_approvals[]+meetings[]+pending_actions{depth,recent[]}`
`HrRoster/HrRelationships -> [EM] rows + graph nodes/affinity edges`
`PayrollRoster/PayrollHistory/AccountingSummary -> pay editor data + audit entries + cash/accounts/approvals/deep-link`
`ExternalWorldNews/Customers/RevenueByCustomer -> BetaCorp events + pipeline + realized revenue`
`Kpi* -> department/employee aggregates + review log/tier + approval_mode`
`CompanyDirective* -> current/versioned history`
`Chaos* -> container states + outage events + crisis result`
`DataManagement* -> 10 scopes + manifest/artifact hashes + snapshot list`
`Branding* -> avatar/emoji IDs + per-[EM] selection`
`Tv*/Error*/DeepLink* -> recent [AP] activity + Loki rows + credential-bearing appliance links`
`api.simulationStatus() -> GET /api/simulation/status`
`api.tickPause()/tickResume() -> POST /api/simulation/tick/{pause|resume}`
`api.llmStatus()/llmSpend()/narrativeSummary() -> GET /api/{llm/status|llm/spend|narrative/summary}`
`api.hrRoster()/hrRelationships() -> GET /api/hr/{roster|relationships}`
`api.hrHire(body)/hrFire(id) -> POST /api/hr/employees/{hire|<id>/fire}`
`api.payrollRoster()/payrollHistory() -> GET /api/payroll/{roster|history}`
`api.payrollRaise({employee_id,new_pay,reason}) -> POST /api/payroll/raise`
`api.accountingSummary() -> GET /api/accounting/summary`
`api.accountingApprove|Reject(id) -> POST /api/accounting/expense/{approve|reject}; actor=principal`
`api.externalWorld{News|Customers|RevenueByCustomer}() -> GET /api/external-world/*`
`api.kpi{Department|Employee}Scoreboard()/kpiReviewLog()/kpiReviewMode() -> GET /api/kpi/*`
`api.kpiSetReviewMode(enabled) -> POST /api/kpi/review-mode`
`api.companyDirection{Current|History}() -> GET /api/company-direction/*`
`api.companyDirectionSave(content) -> POST /api/company-direction/save`
`api.chaosStatus()/chaosOutages() -> GET /api/chaos/*`
`api.chaosApplianceAction(name,stop|start|restart) -> POST /api/chaos/appliances/<name>/<action>`
`api.chaosTriggerEvent({scenario,custom_text?}) -> POST /api/chaos/trigger-event`
`api.dataManagementScopes()/Snapshots() -> GET /api/data-management/*`
`api.dataManagementPurgeScope(scope,confirm) -> POST /api/data-management/purge-scope`
`api.dataManagementSnapshotSave(label?) -> POST /api/data-management/snapshots/save`
`api.dataManagementSnapshotRestore(name,confirm) -> POST /api/data-management/snapshots/restore`
`api.dataManagementSnapshotDelete(name) -> DELETE /api/data-management/snapshots/<name>`
`api.brandingAssets()/brandingEmployee(id) -> GET /api/branding/*`
`api.brandingApply(id,asset)/brandingBulkApply(body) -> POST /api/branding/{apply|bulk-apply}`
`api.settingsLastSnapshot() -> GET /api/settings/full-purge/last-snapshot`
`api.settingsFullPurge(confirm) -> POST /api/settings/full-purge`
`api.tvChatFeed()/tvTicketFeed()/errorsServices()/errorsRecent(service?)/deepLinks() -> GET /api/*`

**RATIONALE**
^R1: Native Basic Auth avoids browser-side secret persistence; one thin error path preserves upstream response evidence but may expose internal text to authenticated [PR].

## File: /dashboard/frontend/src/main.tsx
**Deps:** [UI], React18, App, TvWall
**State:** route bootstrap

`isTv := trimTrailingSlash(window.location.pathname)=="/tv"`
`ReactDOM.createRoot(#root).render(StrictMode + (isTv?TvWall:App))`

**RATIONALE**
^R1: One alternate top-level route does not justify router dependency/state. Route split affects chrome only; BFF auth gates `/tv` identically.

## File: /dashboard/frontend/src/TvWall.tsx
**Deps:** [UI], api.ts, [SC], [DB], [AP]
**State:** polling/cycling spectator view

`PANELS -> chat|tickets|financial|kpi|sim; CYCLE_MS=18000`
`TvWall() + panelIdx/chat/tickets/accounting/kpi/sim/narrative/error state`
`load() => parallel-ish api calls tvChatFeed+tvTicketFeed+accountingSummary+kpiDepartmentScoreboard+simulationStatus+narrativeSummary`
`data refresh -> immediate + every 15000ms; panel advance -> every 18000ms; cleanup -> clearInterval`
`chat panel -> channel+username+message; empty -> No recent chat activity`
`ticket panel -> number+title; empty -> No recent tickets`
`financial panel -> cash balance+pending approvals+pending_actions retry depth`
`kpi panel -> rows sort(total DESC) -> first 10 department/metric totals`
`sim panel -> localized sim_time+speed_multiplier+tick paused/running`
`weekly digest -> omitted ^R1`

**RATIONALE**
^R1: Phase25 digest generator absent; fabricating panel content would violate source-of-truth/narrative semantics.

## File: /dashboard/frontend/src/App.tsx
**Deps:** [UI], api.ts, React hooks, react-force-graph-2d, Recharts, [SC], [LLM], [DB], [OR], [HB], [AP]
**State:** client-local tab/forms/polling/modal state

`NAV_ITEMS -> 15 tabs: simulation,llm,narrative,hr,payroll,accounting,external-world,kpi,company-direction,chaos,data-management,branding,errors,deep-links,settings`
`App() + tab=simulation -> button-nav conditional component; /tv external new-tab link`
`ErrorBanner(msg) -> "Service unavailable" alert`

`SimulationTab() -> poll /simulation/status every 5s; localized sim/wall time; speed; tick state/last/interval; pause|resume => refresh`
`SPEED_PRESETS -> 0.1|0.25|0.5|1|2|5|10; slider/buttons disabled + Coming Soon ^R1`
`pause semantics -> [OR] scheduler loop only; containers/[CP] unaffected`

`LlmStatusTab() -> config once + spend once/every15s; tiers/model order table; total spend/tokens; trailing1h $/wall-hour; speed-adjusted $/sim-hour; per-model calls/tokens/spend`

`NarrativeTab() -> poll every10s; open/in-progress threads with priority>0 CRISIS highlight; action items; pending reactions; pending approvals; latest meetings; pending_actions queue depth/retry schedule`

`HrTab() -> roster+relationships immediate/every15s; PTO/status badges; hire modal(name,department,title,role_tier ic|lead); fire confirmation`
`graphData(selectedEmployeeId?) -> all graph || selected node+incident edges; link width=max(.5,abs(affinity)/20); positive blue; negative red; nodes auto-color department; click node filter; clear filter ^R2`
`fire copy -> deactivate Mattermost/Zammad/Wiki.js + restrict mailbox; preserve data; status=terminated`

`PayrollTab() -> active roster+audit history initial; proposal per [EM]; increase => immediate /payroll/raise + toast + reload`
`proposed<current -> Save disabled + Phase24 tooltip; no cut request ^R3`
`history -> raise_applied|pay_cut_proposed_stub details`

`AccountingTab() -> summary immediate/every15s; cash/error; Akaunting P&L deep link; pending expense Approve/Reject; audit-correction log`

`ExternalWorldTab() -> news+customers+revenue immediate/every20s; BetaCorp feed; offers/resignations subset; customer sort(status|deal_size); at_risk/churned highlight; Recharts revenue bars; empty/error states`

`KpiTab() -> department+employee scoreboards/review log/review mode initial; mode toggle immediate; employee metric auto-select first available; totals DESC ^R4`
`review tier badges -> top_quartile active-style; second_quartile PTO-style; rest vacant-style`

`CompanyDirectionTab() -> current+history initial; edit current text; nonblank Save => [HB] version + Wiki sync result toast; history toggle; current highlight; preview first160 chars`

`CRISIS_SCENARIOS -> data_breach|surprise_audit|viral_complaint|custom`
`ChaosTab() -> status+outages immediate/every10s; stop requires modal; start/restart direct; nonrunning highlight; custom requires text; trigger => thread/forced attendees/audit/meeting/expense result; outage log`

`DataManagementTab() -> scopes+snapshots initial; multi-scope Set selection`
`requiredPhrase(scopes) -> selected confirm phrases joined " + " ^R5`
`purge selected -> sequential per-scope API calls; each owning phrase; success clears selection`
`snapshot save -> immediate manifest; restore -> exact "RESTORE SNAPSHOT" gate; delete -> confirmation only; bytes -> B|KB|MB|GB`
`full purge -> absent from tab; Settings only`

`BrandingTab() -> assets+roster initial; avatar/emoji image grid through BFF; per-[EM] avatar; multi-[EM] Set; modes=randomize|apply-one-to-all|reset-to-default; apply-one requires asset`

`ErrorsTab() -> services once; error rows immediate/every15s + optional service filter; display exact LogQL; no rows state`
`EventSource(/api/logs/tail) -> parse SSE; retain last200; malformed frame ignored; server error frame shown; disconnect warns auto-retry`

`DeepLinksTab() -> 8 [AP] rows; new-tab URLs; usernames visible; password masked by default/per-row reveal; absent secret label; no iframe ^R6`

`PurgeStep -> idle|modal|typed|final|done`
`SettingsTab() -> last snapshot; isolated ☢ danger zone; enumerated destruction; auto-prepurge snapshot notice`
`full purge confirmations -> initial arm + modal explicit acknowledgement + exact "PURGE EVERYTHING" + final Execute => API; any stage cancel/reset ^R7`
`success -> status+pre_purge_snapshot`

**RATIONALE**
^R1: Phase32 runtime speed API/cadence audit deferred by user; visible disabled shape preserves future UX without cosmetic fake control. Worker-scale omitted because user scrapped undefined concept.
^R2: Force-directed graph matches relationship network; ReactFlow manual positioning rejected.
^R3: Pay cuts require unbuilt Phase24 `pay_negotiation`; UI plus accounting-engine increase-only validation prevent direct cut bypass.
^R4: Hardcoded metric previously rendered empty despite data; runtime available-metric selection fixes misleading blank scoreboard.
^R5: Multi-scope operation requires explicit acknowledgement of every selected destruction scope; server independently validates each and mandates pre-purge snapshot.
^R6: Iframes rejected because [AP] frame policies/login boundaries; credentials intentionally visible only inside dashboard-wide Basic Auth. This is operator convenience, not per-[AP] SSO.
^R7: User required nuclear/scary Settings-only UX and at least 3 post-selection confirmations; implementation provides 3 staged confirmations after initial selection, while BFF + purge-manager add independent server gates and mandatory snapshot.

## File: /dashboard/frontend/src/styles.css
**Deps:** [UI]
**State:** global presentation

`theme -> dark; body #0f1115; cards/topbar #171a21; accent #2f6fed; danger #c0392b/#ff2b2b`
`layout -> topbar flex; tabs; content max-width1200; responsive wrap; block-scroll tables`
`status classes -> active/on-PTO/vacant/terminated/resigned/prospect/at-risk/churned; crisis/PTO row backgrounds`
`controls -> disabled opacity+cursor; modal fixed overlay z100; forms; toast/error banners`
`danger-zone -> 2px red + radial red field + glow; explicit nuclear visual isolation`
`log-tail -> 320px scroll monospace; timestamp/container coloring; wrap long lines`
`tv-wall -> full viewport/no chrome/high contrast; max1100; fixed cycle dots/error; 60vh lists; 2.4rem stats/headings`

**RATIONALE**
^R1: Nuclear controls intentionally violate routine visual calm to reduce accidental destructive action.
^R2: TV wall optimizes across-room legibility rather than dashboard density.

## File: /dashboard/frontend/tsconfig.json
**Deps:** [UI], TypeScript
**State:** compiler configuration

`target/lib -> ES2020 + DOM + DOM.Iterable; module=ESNext; moduleResolution=bundler; jsx=react-jsx`
`strict=true; isolatedModules=true; noEmit=true; useDefineForClassFields=true; resolveJsonModule=true; skipLibCheck=true`
`include -> src`

**RATIONALE**
^R1: TypeScript validates only; Vite owns emission/bundling.

## File: /dashboard/frontend/vite.config.ts
**Deps:** [UI], Vite, React plugin
**State:** build/dev configuration

`plugins -> react()`
`base -> /`
`build.outDir -> ../static; emptyOutDir=true`
`dev.proxy(/api) -> http://localhost:8000`

**RATIONALE**
^R1: Output outside frontend tree lets multistage image copy one static directory into same FastAPI container; no second web server/container.

## File: /dashboard/main.py
**Deps:** [UI], [SV], [DB], [SC], [OR], [HB], [LLM], [AP], [OB], asyncpg, aiomysql, httpx, FastAPI, Pydantic, PyYAML
**State:** stateful BFF; async pools + static serving; no business-domain ownership

`env -> DATABASE_URL|POSTGRES_*; SIM_CLOCK_URL; ORCHESTRATOR_URL; LITELLM_CONFIG_PATH; PROVISIONING_URL; ACCOUNTING_ENGINE_URL; AKAUNTING_COMPANY_ID; AKAUNTING_PUBLIC_URL; EXTERNAL_WORLD_URL; KPI_ENGINE_URL; HUMAN_BRIDGE_URL; PURGE_MANAGER_URL; SNAPSHOT_MANAGER_URL; BRANDING_MANAGER_URL; AKAUNTING_DB_HOST|NAME|USER|PASSWORD; DASHBOARD_AUTH_USER|PASSWORD; LOKI_URL; MATTERMOST_URL|ADMIN_TOKEN|TEAM_ID; ZAMMAD_URL|ADMIN_TOKEN; PRINCIPAL_EMAIL; MAILSERVER_BOT_SECRET; KPI_SCOREBOARD_LOOKBACK_DAYS`
`DATA_MANAGEMENT_SCOPES -> emails/chat/tickets/wiki/meetings_narrative/accounting/external_world/kpi_history/roster/company_direction + exact phrases`
`FULL_PURGE_CONFIRM_PHRASE -> "PURGE EVERYTHING"`
`_derive_mailbox_password(email) -> sha256("<MAILSERVER_BOT_SECRET>:<email>")[:24] ^R1`
`_build_deep_links() -> Mattermost(/login),Zammad(/#login),Wiki.js(/login),Nextcloud(/login),WordPress(/wp-login.php),Akaunting(/auth/login),Roundcube(root),Grafana(:3000/login) + env credentials ^R1`
`require_basic_auth(credentials) -> username || 401 WWW-Authenticate || 503 missing config ^R2`
`lifespan() + asyncpg pool(min2,max5) + httpx client(timeout15) + Akaunting aiomysql pool(min1,max3,autocommit); MariaDB failure => warning/null chart only; shutdown closes all`
`_unhandled_exception_handler(req,exc) => JSON ERROR log with one-line traceback -> 500 generic body ^R3`
`GET /health -> {status:ok,service:dashboard}; no auth ^R2`

`GET /api/simulation/status -> GET [SC]/clock + GET [OR]/tick/status; independent error fields`
`POST /api/simulation/tick/{pause|resume} => [OR]/tick/{pause|resume} || 502`
`_parse_litellm_config() -> tiers by model_name prefix + model_group_alias+fallbacks+num_retries || error ^R4`
`GET /api/llm/status -> provider config + [DB].sim_clock.speed_multiplier || 1.0`
`GET /api/llm/spend -> SUM(spend,total_tokens), trailing1h spend, model aggregates, speed; burn_per_sim_hour=wall_rate/speed ^R5`

`GET /api/narrative/summary -> open/in_progress threads(limit100,priority DESC); action_items(limit100,open first/due); pending reactions(limit100); pending approvals(limit100); meetings(limit50); pending_actions depth+recent20`
`GET /api/hr/roster -> all [EM]+wall-NOW PTO approximation+display_status ^R6`
`GET /api/hr/relationships -> [EM] nodes + joined relationship edges`
`POST /api/hr/employees/hire(body:HireBody) => provisioning/hire`
`POST /api/hr/employees/<id>/fire => provisioning/fire`
`GET /api/payroll/roster -> active [EM] pay fields`
`GET /api/payroll/history -> audit actions raise_applied|pay_cut_proposed_stub limit200`
`POST /api/payroll/raise(body:RaiseBody) => accounting-engine/payroll/raise query params || upstream status|502`
`GET /api/accounting/summary -> accounting-engine cash || embedded error + [DB] pending approvals/audit correction + Akaunting P&L URL`
`POST /api/accounting/audit/run => accounting-engine/audit/run`
`POST /api/accounting/expense/{approve|reject}(ApprovalBody) => accounting-engine with approved_by|rejected_by actor + note`

`GET /api/external-world/news -> system_audit_log actions betacorp_offer_sent|employee_resigned_betacorp|pay_gap_flag_raised; category derived`
`GET /api/external-world/customers -> customers + sales/support [EM] joins`
`GET /api/external-world/revenue-by-customer -> [DB] customer tx refs => Akaunting ak_transactions income/nondeleted direct MariaDB; sorted revenue DESC || []+error ^R7`
`GET /api/kpi/department-scoreboard -> SUM/AVG kpi_snapshots by department+metric within configurable 30d`
`GET /api/kpi/employee-scoreboard -> [EM] join + SUM/AVG by employee+metric within lookback`
`GET /api/kpi/review-log -> audit review_raise_applied|queued; tier parsed from reason ^R8`
`GET|POST /api/kpi/review-mode -> kpi-engine/config/review-mode; POST actor=principal`
`GET /api/company-direction/current|history -> append-only company_directives current/latest100`
`POST /api/company-direction/save(content) => [HB]/action/update-directive created_by=principal`

`GET /api/chaos/status|outages -> [OR]/chaos/appliances/status|outages`
`POST /api/chaos/appliances/<name>/<action> -> action allow-set stop|start|restart => [OR] || 400|upstream|502`
`POST /api/chaos/trigger-event(TriggerEventBody) => [OR]/chaos/trigger-event timeout120`
`GET /api/data-management/scopes -> mirrored labels/phrases`
`POST /api/data-management/purge-scope -> local scope allow-set => purge-manager/purge/<scope> timeout180`
`GET /api/data-management/snapshots -> snapshot-manager/snapshot/list`
`POST /api/data-management/snapshots/save -> snapshot-manager/snapshot/save timeout180`
`POST /api/data-management/snapshots/restore -> snapshot-manager/snapshot/restore timeout300`
`DELETE /api/data-management/snapshots/<name> -> snapshot-manager/snapshot/<name>`
`GET /api/branding/asset-proxy/{avatars|emoji}/<id>.png -> branding-manager bytes; media=image/png ^R9`
`GET /api/branding/assets|employee/<id> -> branding-manager`
`POST /api/branding/apply|bulk-apply -> branding-manager`
`GET /api/settings/full-purge/last-snapshot -> max(wall_clock_captured_at) || null/error`
`POST /api/settings/full-purge(confirm) => purge-manager/purge/full timeout600 ^R10`

`GET /api/tv/chat-feed -> Mattermost token; resolve first team if TEAM_ID blank; channels; last5/channel; username cache; global newest20; message[:280]`
`GET /api/tv/ticket-feed -> Zammad token; all tickets sort created DESC -> first20`
`GET /api/errors/services -> fixed 9-container allow-list`
`GET /api/errors/recent(service?,limit=200) -> validate service; Loki query_range {container=~...,level="ERROR"}; ns timestamp -> UTC ISO; DESC; limit ^R11`
`GET /api/deep-links -> credential-bearing links ^R1`
`LOG_TAIL_QUERY -> {container=~"fakeco-traefik|fakeco-dns"}`
`GET /api/logs/tail -> SSE; initial start=now-30s; Loki forward poll every3s; dedupe ts<=last_ns; sorted frames; failures emitted as data.error ^R12`
`GET /<path> -> existing static file || index.html; auth required; route declared last ^R13`

**RATIONALE**
^R1: Roundcube password is never stored separately; exact provisioning derivation reproduced. Deep-link plaintext secrets are accepted single-[PR] convenience behind dashboard Basic Auth; no iframe/SSO.
^R2: Entire SPA/API fails closed if credentials absent. `/health` exemption is container-internal probe convention.
^R3: Uvicorn/Starlette unhandled tracebacks were plaintext and invisible to Promtail JSON `level`; explicit JSON re-log restores Errors panel visibility while generic response avoids traceback leakage. Starlette may still emit duplicate plaintext.
^R4: No proven keyless LiteLLM config-introspection endpoint; read-only mounted YAML avoids API-key plumbing.
^R5: Query intentionally identical to Phase31 Grafana source. At speed>1, wall-hour covers more sim-hours; division gives per-sim-hour burn.
^R6: PTO table uses sim-time, but query uses wall-clock `NOW()`; badge is approximate/display-only and never gates behavior.
^R7: Direct ledger DB read avoids Akaunting REST `Host: accounting.fakecorp.internal` + `X-Company` quirks and follows Grafana Phase31 pattern. Optional pool failure degrades one chart, not BFF startup.
^R8: Tier is embedded only in audit reason; parser avoids recomputing review formula.
^R9: Branding manager lacks browser-reachable [NW]; BFF streams assets without duplicating files or exposing internal service.
^R10: Client confirmations are UX only; purge-manager revalidates exact phrase and forces fresh pre-purge snapshot. BFF never performs deletion itself.
^R11: Promtail promotes JSON `level` to Loki label; label match avoids text scan. Fixed list limits query/control exposure.
^R12: SSE is sufficient one-way near-live transport; no WebSocket dependency. Timestamp cursor provides at-most-once-by-timestamp behavior; equal-nanosecond distinct lines could theoretically collapse.
^R13: Catch-all after API routes enables SPA navigation while preserving real assets and auth.

## File: /dashboard/requirements.txt
**Deps:** [UI], [SV]
**State:** Python dependency bounds

`fastapi>=0.115; uvicorn[standard]>=0.30; asyncpg>=0.29; httpx>=0.27; pydantic>=2; pyyaml>=6; aiomysql>=0.2`

**RATIONALE**
^R1: aiomysql supports direct Akaunting ledger read with no native client package; direct read shares Phase31 reporting semantics.

## File: /monitoring/README.md
**Deps:** [OB], [CP], [NW], [AP], [DB], [LLM]
**State:** architecture summary

`Phase2 -> cAdvisor container metrics + node-exporter host metrics + Prometheus scrapes`
`Phase11 -> Loki+Promtail+Grafana; container health + HTTP/DNS/mail/activity`
`Phase31 -> LLM cost, narrative backlog, headcount, sim/wall, financials, KPI, customer pipeline/revenue`
`[NW] -> net_mgmt; Prometheus/Grafana multi-home only when target/data access required`

**RATIONALE**
^R1: Observability reaches isolated networks; network attachment is visibility, not internet egress. README says all appliance logs, while Promtail actually filters `fakeco.managed=true`.

## File: /monitoring/grafana/dashboards/container-health.json
**Deps:** [OB], Prometheus, cAdvisor, node-exporter
**State:** provisioned dashboard; uid=fakeco-container-health; refresh=30s; range=1h

`P1 stat up -> up; mapping 0=DOWN/red,1=UP/green`
`P2 timeseries CPU -> sum(rate(container_cpu_usage_seconds_total{name=~"fakeco-.+"}[2m])) by(name)`
`P3 timeseries memory(bytes) -> sum(container_memory_usage_bytes{name=~"fakeco-.+"}) by(name)`
`P4 stat host load -> node_load1`
`P5 stat containers seen -> count(count by(name)(container_last_seen{name=~"fakeco-.+"}))`

**RATIONALE**
^R1: Stable datasource uid `Prometheus` decouples dashboard JSON from Grafana-generated identifiers.

## File: /monitoring/grafana/dashboards/customer-pipeline-revenue.json
**Deps:** [OB], [DB], Akaunting MariaDB
**State:** provisioned mixed-datasource dashboard; uid=fakeco-customer-pipeline-revenue; refresh=1m; range=30d

`P1 pie -> customers count by relationship_status`
`P2 USD stat -> SUM(deal_size) WHERE status prospect|active`
`P3 table -> customer status/deal_size + sales/support [EM] joins`
`P4 USD stat -> Akaunting SUM(income amount) company_id=1 nondeleted`
`P5 timeseries -> Akaunting paid_at/revenue income nondeleted + $__timeFilter`

**RATIONALE**
^R1: One dashboard intentionally mixes narrative pipeline intent with authoritative ledger realization; customer-to-transaction granularity lives in [UI], while Grafana reports aggregate ledger truth.

## File: /monitoring/grafana/dashboards/financials.json
**Deps:** [OB], Akaunting MariaDB
**State:** provisioned dashboard; uid=fakeco-financials; refresh=1m; range=7d

`P1 cash USD -> SUM(account opening_balance)+SUM(income)-SUM(expense); company_id=1; nondeleted`
`P2 burn/day USD -> trailing30d expense SUM/30`
`P3 runway days -> cash/NULLIF(burn/day,0)`
`P4 payroll USD -> transactions JOIN categories name='Payroll Expense'`
`P5 timeseries -> income vs expense UNION ALL by paid_at + $__timeFilter`
`P6 table -> expense category count+SUM DESC`

**RATIONALE**
^R1: Direct DB reporting bypasses Akaunting API host/company-header bugs; admin credential reuse accepted by user for implementation simplicity.

## File: /monitoring/grafana/dashboards/headcount-by-status.json
**Deps:** [OB], [DB], [EM]
**State:** provisioned dashboard; uid=fakeco-headcount-by-status; refresh=30s; range=6h

`P1 pie -> count [EM] GROUP BY status`
`P2 bargauge(min0) -> same status counts`
`P3 stat -> active count`
`P4 table -> department,status,count`

**RATIONALE**
^R1: Pie and bar intentionally duplicate aggregation for composition vs magnitude readability.

## File: /monitoring/grafana/dashboards/kpi-trends.json
**Deps:** [OB], [DB], [EM]
**State:** provisioned dashboard; uid=fakeco-kpi-trends; refresh=1m; range=30d

`P1 timeseries -> department kpi_snapshots; series=entity_id/metric; $__timeFilter`
`P2 table -> DISTINCT ON(department,metric) latest department snapshot`
`P3 table -> DISTINCT ON(employee,metric) latest employee snapshot + LEFT JOIN [EM]`

**RATIONALE**
^R1: Trend plus latest tables separate temporal change from current cross-section.

## File: /monitoring/grafana/dashboards/llm-spend.json
**Deps:** [OB], [DB], [LLM], [SC]
**State:** provisioned dashboard; uid=fakeco-llm-spend; refresh=1m; range=24h

`P1 USD stat -> SUM("LiteLLM_SpendLogs".spend)`
`P2 stat -> SUM(total_tokens)`
`P3 USD stat -> trailing1h SUM(spend)`
`P4 stat -> sim_clock.speed_multiplier id=1`
`P5 timeseries -> spend SUM in Grafana 5m buckets + $__timeFilter`
`P6 table -> model call count/token sum/spend sum DESC`

**RATIONALE**
^R1: LiteLLM writes into shared [DB], so direct SQL is authoritative and reused verbatim by [UI]. Speed is annotation only; true runtime adjustment remains deferred Phase32.

## File: /monitoring/grafana/dashboards/narrative-backlog.json
**Deps:** [OB], [DB], [OR], [HB]
**State:** provisioned dashboard; uid=fakeco-narrative-backlog; refresh=30s; range=6h

`P1 -> count threads open|in_progress`
`P2 -> count action_items open|overdue`
`P3 -> count pending_approvals pending`
`P4 -> count pending_reactions pending`
`P5 -> pending_actions pending|retrying; to_regclass guard => 0 if table absent ^R1`
`P6 -> latest50 open threads table`

**RATIONALE**
^R1: Dashboard landed near concurrent Phase27 migration; schema-existence guard preserved load order compatibility. Panel title text still says “Phase 27, not yet built” although table is built: stale presentation metadata.

## File: /monitoring/grafana/dashboards/sim-time-vs-wallclock.json
**Deps:** [OB], [DB], [SC]
**State:** provisioned live-snapshot dashboard; uid=fakeco-sim-time-vs-wallclock; refresh=30s; range=1h

`P1 -> speed_multiplier`
`P2 ISO datetime -> sim_time`
`P3 ISO datetime -> DB now()`
`P4 consistency row -> checkpoint wall delta + implied_current_sim_time=sim_time+delta*speed`

**RATIONALE**
^R1: `sim_clock` is one mutable row, not history; trend chart would fabricate history. Live state + implied-time drift check documents actual model.

## File: /monitoring/grafana/dashboards/traffic-and-activity.json
**Deps:** [OB], Loki, Traefik, Technitium, mailserver, [AP]
**State:** provisioned dashboard; uid=fakeco-traffic-activity; refresh=30s; range=1h

`P1 -> Traefik request/min from JSON RequestHost nonempty`
`P2 -> fakeco-dns log lines/min`
`P3 -> fakeco-mailserver log lines/min`
`P4 -> all fakeco-.+ container log activity/min by container`
`P5 logs -> {container=~"fakeco-traefik|fakeco-dns"}`

**RATIONALE**
^R1: Log volume is an activity proxy, not semantic business throughput. P5 query is exact source reused by [UI] SSE tail.

## File: /monitoring/grafana/provisioning/dashboards/dashboards.yml
**Deps:** [OB], Grafana
**State:** provisioning definition

`provider fakeco-dashboards -> orgId1/folder FakeCo/type=file/path=/var/lib/grafana/dashboards`
`disableDeletion=false; updateIntervalSeconds=30; allowUiUpdates=true; foldersFromFilesStructure=false`

**RATIONALE**
^R1: Dashboard file provider polls live files; unlike datasource provisioning, dashboard changes need no Grafana restart. UI edits are allowed but file state remains declarative authority on reprovision.

## File: /monitoring/grafana/provisioning/datasources/datasources.yml
**Deps:** [OB], [DB], [NW], Prometheus, Loki, PostgreSQL16, Akaunting MariaDB
**State:** startup provisioning; apiVersion=1

`Prometheus(uid=Prometheus,url=http://prometheus:9090,default,proxy,immutable)`
`Loki(uid=Loki,url=http://loki:3100,proxy,immutable)`
`Postgres-Fakeco(uid=PostgresFakeco,url=postgres:5432,user=${POSTGRES_USER},password=${POSTGRES_PASSWORD},db=${POSTGRES_DB},ssl=disable,version=1600,immutable)`
`MySQL-Akaunting(uid=MySQLAkaunting,url=akaunting-db:3306,user=akaunting,password=${AKAUNTING_DB_PASSWORD},db=akaunting,immutable)`

**RATIONALE**
^R1: Fixed uids prevent persisted auto-generated uid mismatch; initial Phase11 setup required Grafana restart/one-time data-volume reset after uid correction.
^R2: Existing admin DB credentials reused by explicit user choice; dedicated read-only roles would require cross-DB provisioning/migrations. Security compromise acceptable for single-operator isolated stack; revisit for multi-tenant exposure.
^R3: Direct MariaDB access avoids Akaunting's mandatory Host+X-Company API headers.

## File: /monitoring/loki-config.yaml
**Deps:** [OB], [NW]
**State:** single-node Loki config

`auth_enabled=false`
`server -> HTTP3100; gRPC9096`
`ingester WAL -> /loki/wal; ring=inmemory; replication_factor=1; address=127.0.0.1; final_sleep=0`
`chunks -> idle1h|max1h|target1048576|retain30s`
`schema -> TSDB v13 from 2024-01-01; filesystem object store; daily index_`
`storage -> /loki/index + /loki/index_cache(ttl24h) + /loki/chunks`
`compactor -> /loki/retention; delete store filesystem`
`limits retention -> 744h(31d)`
`table_manager retention deletes=false; retention=0`

**RATIONALE**
^R1: Single-node/in-memory ring/replication1 fits local simulation, not HA. No Loki auth relies on isolated [NW]/dashboard-Grafana mediation.

## File: /monitoring/prometheus.yml
**Deps:** [OB], cAdvisor, node-exporter
**State:** scrape configuration

`global scrape_interval=15s;evaluation_interval=15s;external_label environment=fakecorp`
`job prometheus -> localhost:9090`
`job cadvisor -> cadvisor:8080`
`job node-exporter -> node-exporter:9100`
`postgres-exporter -> commented future placeholder; no service`

**RATIONALE**
^R1: Custom [SV] expose JSON `/health`, not Prometheus `/metrics`; Phase31 uses direct SQL instead of instrumenting every service. Comment “additional scrape targets later” is stale: none added.

## File: /monitoring/promtail-config.yaml
**Deps:** [OB], Docker socket, Loki, [CP]
**State:** log discovery/shipping

`server -> HTTP9080; gRPC disabled`
`positions -> /tmp/positions.yaml`
`client -> http://loki:3100/loki/api/v1/push`
`docker_sd(refresh=5s,host=unix:///var/run/docker.sock) -> label filter fakeco.managed=true`
`relabel container -> strip leading / from Docker name`
`relabel service <- fakeco.service; phase <- fakeco.phase`
`pipeline JSON extract level,msg => promote level label`

**RATIONALE**
^R1: Raw Docker socket is an observability exception; Promtail needs read discovery/log access and is not an application control surface. Managed-label filter excludes unrelated host containers.
^R2: Only JSON logs with `level` gain ERROR label; explicit global FastAPI exception handlers were added to re-log unhandled crashes as JSON. Appliance/plaintext errors remain unlabelled unless their format supplies level.

## OPEN_GAPS
`phase24 -> pay_negotiation invocation+pay-cut workflow absent`
`phase32 -> full speed/cadence integration explicitly deferred; [UI] control disabled`
`phase38 -> top-level README,clean first-boot,env-contract audit,graceful per-backend [UI] errors incomplete`
`docs -> important.md+narrative-db/README.md+older plans contain stale state; BUILD_LOG/current code supersede`
`sim-clock -> ticker SELECT+UPDATE not row-locked; singleton service assumption; multiple replicas could double-advance`
`schema -> 002 action_items original status omits failed but 013 repairs; 002 pending_reactions original status omits failed but 015 repairs; consumers require fully applied migration chain`

`[OR] strict continuity priority order([PR] reaction>approval>action-item>filler) -> absent; fixed scheduled sequence + separate [HB] worker`
`[OR] crisis expense requester -> first attendee; SPEC_CLARIFICATIONS #7 requires [PR] employee/account`
`meeting HR privacy -> pay_negotiation/performance_review currently published to Mattermost+Wiki.js despite README/spec exclusion`
`meeting cross-functional attendee cap -> historical flat truncation can exclude all ICs when leads fill cap`
`Phase24 -> pay negotiation/pay cuts/full underperformance-meeting handling absent; performance-review raise outcome stub`
`Phase25 -> weekly digest absent despite kpi-engine README claim`
`external flavor news -> absent despite external-world README claim`
`[SC] consistency -> several tenure/lookback/default-rollup queries use wall NOW/UTC`
`[LLM] local last-resort model -> intentionally unspecified/deferred`
`[LLM] database isolation -> historical isolated-stack race when LITELLM_DATABASE_URL shared narrative public schema; require dedicated DB URL`
`README phase/status text -> multiple future-tense/stale completion claims; source+BUILD_LOG govern`

`[HB]/action/wiki-page docstring=create-or-update; implementation=create-only => duplicate/path-conflict risk`
`[HB] Zammad/Wiki reaction adapters unit-tested+integrated per BUILD_LOG/bugs.md; full paid-[LLM] behavior unavailable while [LLM] intentionally stopped`
`[HB] Wiki response surface=page append; native comments mutation unavailable/unverified`
`[EM] Mailserver management still Docker-exec based; conflicts with broader socket-proxy EXEC=0 safety posture`
`[EM] fire path reassigns pending_reactions only; source comment states action_items reassignment absent`
`branding desired mapping persists despite individual [AP] push failures; reconciliation worker absent`
`branding README claims APIs disproven by live implementation; update pending`
`Phase38 -> unattended first-boot including initial branding/personality/provisioning; .env.example audit; clean-environment verification`

`P0 audit-continuity` = snapshot narrative dump/restore currently includes `system_audit_log` + `snapshot_purge_log` + maintenance row, violating authoritative clarification #8 and [MG]008 comments.
`P0 restore-safety` = no manifest checksum/size verification; restore path traversal; app stop failures ignored; unexpected mid-restore exception can leave containers stopped; tar restore overlays stale files.
`P1 purge-truthfulness` = email scope no raw mail purge; roster no reseed/deprovision; appliance errors/nonzero mysql can still log success; chat/ticket pagination/completeness absent; Wiki delete success not inspected; accounting table coverage/reseed incomplete.
`P1 money-idempotency` = stable idempotency key not passed into Akaunting `number`; external POST+DB update non-atomic crash windows can duplicate expense/payroll/revenue/corrections; Zammad ticket failure retained without repair queue.
`P1 audit-depth` = Books Auditor only repairs approved expense ref gaps; payroll latest10/presence-only; no real Akaunting reconciliation; revenue/payroll duplication/cross-ledger checks absent.
`P1 state-preservation` = purge/snapshot always resume [SC] at1.0; saved sim_time/speed never restored; maintenance excludes [OR] only, not direct human/appliance writes.
`P1 restore-derived-state` = Zammad Elasticsearch reindex manual; restored DB and search can disagree.
`P2 pay-cuts` = Phase24 absent; endpoint only logs stub despite claims of meeting/reaction queue.
`P2 stale-docs` = purge README wrong full phrase and reset semantics; snapshot README false audit exclusion/current stop behavior; accounting README pre-implementation wording.
`P2 reproducibility` = Python requirements use minimum-only versions; snapshot image depends on external PGDG/PyPI at build.

`Phase24 -> pay-cut/pay_negotiation absent; [UI] decrease disabled; README claim stale`
`Phase25 -> weekly digest absent; /tv panel intentionally omitted`
`Phase32 -> live speed mutation/cadence/billing reconciliation deferred; slider disabled; worker-scale scrapped`
`Phase38 -> top-level first-boot/hardening/README/error-state audit incomplete`
`dashboard/README.md -> stale worker-scale/speed/full-purge/pay-cut descriptions`
`narrative-backlog.json P5 title -> stale "Phase 27, not yet built" text; query still correct`
`[UI] PTO badge -> wall-clock NOW approximation against sim-time calendar`
`Errors panel -> fixed 9 [SV] only; JSON level-labelled errors only; plain [AP]/uvicorn lines may remain invisible`
`Deep Links -> plaintext [AP] passwords available to any dashboard-authenticated caller; no SSO/secret-vault boundary`
`[OB] DB datasources -> admin credentials, not read-only roles`
`[OB] alerting -> absent by design/spec; dashboards only`
`Loki -> unauthenticated single-node/31d retention; relies on [NW]`
`Promtail -> raw Docker socket read exception; no socket-proxy mediation`
`Roundcube/Wiki.js/Zammad/Akaunting live DB/config repairs -> BUILD_LOG records; reproducibility on fresh purge/rebuild not fully encoded by assigned monitoring/[UI] files`

## COVERAGE
`.env.example`
`.gitignore`
`BUILD_LOG.md`
`Future_Plans.md`
`PHASE29_PLAN.md`
`PHASES.md`
`PLAN_PHASES_27_28_31_32.md`
`PLAN_PHASES_33_38_DASHBOARD.md`
`PLAN_REMAINING_PHASES.md`
`SPEC_CLARIFICATIONS.md`
`bugs.md`
`docker-compose.yml`
`fakeco-real-appliances-BUILD-PROMPT.md`
`important.md`
`narrative-db/Dockerfile`
`narrative-db/README.md`
`narrative-db/migrate.py`
`narrative-db/migrations/001_sim_clock.sql`
`narrative-db/migrations/002_narrative_core.sql`
`narrative-db/migrations/003_employees.sql`
`narrative-db/migrations/004_additive_schemas.sql`
`narrative-db/migrations/005_customers_seed.sql`
`narrative-db/migrations/006_phase19_pto.sql`
`narrative-db/migrations/007_branding.sql`
`narrative-db/migrations/008_phase29_purge_snapshots.sql`
`narrative-db/migrations/009_phase27_pending_actions.sql`
`narrative-db/migrations/010_phase28_crisis.sql`
`narrative-db/migrations/011_kpi_engine_config.sql`
`narrative-db/migrations/012_deliverable_action_items.sql`
`narrative-db/migrations/013_deliverable_retry_state.sql`
`narrative-db/migrations/014_personality_profiles.sql`
`narrative-db/migrations/015_reaction_retry_state.sql`
`narrative-db/requirements.txt`
`sim-clock/Dockerfile`
`sim-clock/README.md`
`sim-clock/main.py`
`sim-clock/requirements.txt`
`orchestrator/Dockerfile`
`orchestrator/README.md`
`orchestrator/main.py`
`orchestrator/requirements.txt`
`meeting-simulator/Dockerfile`
`meeting-simulator/README.md`
`meeting-simulator/main.py`
`meeting-simulator/requirements.txt`
`external-world/Dockerfile`
`external-world/README.md`
`external-world/main.py`
`external-world/requirements.txt`
`kpi-engine/Dockerfile`
`kpi-engine/README.md`
`kpi-engine/main.py`
`kpi-engine/requirements.txt`
`litellm/README.md`
`litellm/config.yaml`
`human-bridge/Dockerfile`
`human-bridge/README.md`
`human-bridge/requirements.txt`
`human-bridge/main.py`
`human-bridge/reaction_chat.py`
`human-bridge/reaction_email.py`
`human-bridge/reaction_wikijs.py`
`human-bridge/reaction_zammad.py`
`human-bridge/tests/test_reaction_chat.py`
`human-bridge/tests/test_reaction_email.py`
`human-bridge/tests/test_reaction_wikijs.py`
`human-bridge/tests/test_reaction_zammad.py`
`provisioning/Dockerfile`
`provisioning/README.md`
`provisioning/requirements.txt`
`provisioning/main.py`
`personality-library/batch-01.json`
`personality-library/batch-02.json`
`personality-library/batch-03.json`
`personality-library/batch-04.json`
`personality-library/batch-05.json`
`branding-manager/Dockerfile`
`branding-manager/README.md`
`branding-manager/assets/generate_assets.py`
`branding-manager/main.py`
`branding-manager/requirements.txt`
`branding-manager/assets/avatars/avatar-01.png`
`branding-manager/assets/avatars/avatar-02.png`
`branding-manager/assets/avatars/avatar-03.png`
`branding-manager/assets/avatars/avatar-04.png`
`branding-manager/assets/avatars/avatar-05.png`
`branding-manager/assets/avatars/avatar-06.png`
`branding-manager/assets/avatars/avatar-07.png`
`branding-manager/assets/avatars/avatar-08.png`
`branding-manager/assets/avatars/avatar-09.png`
`branding-manager/assets/avatars/avatar-10.png`
`branding-manager/assets/emoji/fakeco-alert.png`
`branding-manager/assets/emoji/fakeco-money.png`
`branding-manager/assets/emoji/fakeco-shipit.png`
`branding-manager/assets/emoji/fakeco-star.png`
`branding-manager/assets/emoji/fakeco-thumbsup.png`
`accounting-engine/Dockerfile`
`accounting-engine/README.md`
`accounting-engine/main.py`
`accounting-engine/requirements.txt`
`akaunting-init/entrypoint-idempotent.sh`
`purge-manager/Dockerfile`
`purge-manager/README.md`
`purge-manager/main.py`
`purge-manager/requirements.txt`
`snapshot-manager/Dockerfile`
`snapshot-manager/README.md`
`snapshot-manager/main.py`
`snapshot-manager/requirements.txt`
`dashboard/Dockerfile`
`dashboard/README.md`
`dashboard/frontend/index.html`
`dashboard/frontend/package-lock.json`
`dashboard/frontend/package.json`
`dashboard/frontend/src/api.ts`
`dashboard/frontend/src/main.tsx`
`dashboard/frontend/src/TvWall.tsx`
`dashboard/frontend/src/App.tsx`
`dashboard/frontend/src/styles.css`
`dashboard/frontend/tsconfig.json`
`dashboard/frontend/vite.config.ts`
`dashboard/main.py`
`dashboard/requirements.txt`
`monitoring/README.md`
`monitoring/grafana/dashboards/container-health.json`
`monitoring/grafana/dashboards/customer-pipeline-revenue.json`
`monitoring/grafana/dashboards/financials.json`
`monitoring/grafana/dashboards/headcount-by-status.json`
`monitoring/grafana/dashboards/kpi-trends.json`
`monitoring/grafana/dashboards/llm-spend.json`
`monitoring/grafana/dashboards/narrative-backlog.json`
`monitoring/grafana/dashboards/sim-time-vs-wallclock.json`
`monitoring/grafana/dashboards/traffic-and-activity.json`
`monitoring/grafana/provisioning/dashboards/dashboards.yml`
`monitoring/grafana/provisioning/datasources/datasources.yml`
`monitoring/loki-config.yaml`
`monitoring/prometheus.yml`
`monitoring/promtail-config.yaml`
