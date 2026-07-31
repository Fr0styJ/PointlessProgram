# BUILD_LOG.md — FakeCo "Real Appliances" Build

---

## STATUS HEADER

| Field | Value |
|---|---|
| **Current Phase** | Phase 1 — Compose topology, networks, shared Postgres, socket-proxy |
| **Percent Complete** | ~8% (Phase 0 complete; Phase 1 code complete, runtime verification BLOCKED) |
| **Status** | Phase 1 CODE COMPLETE — **BLOCKED on Docker installation** |
| **Exact Next Action** | Install Docker Desktop (or Docker Engine) on this machine, then run `docker compose up postgres docker-socket-proxy -d` and verify Phase 1 exit criteria: (1) both services healthy, (2) Postgres reachable from net_data container, (3) NOT reachable from net_clients container, (4) socket-proxy allows START/STOP/RESTART on labeled container, rejects image-pull. After that, proceed to Phase 2 (add phase2 profile services: cadvisor, node-exporter, prometheus). |
| **BLOCKER** | Docker is not installed. Was at `C:\Program Files\Docker\Docker` but was **uninstalled 2026-06-22** per `C:\ProgramData\DockerDesktop\install-log-admin.txt`. No container runtime found on PATH. |

**Environment:**
- OS: Windows, shell: pwsh
- Repo root: `c:\code\PointlessProgram`
- Git initialized: YES (first commit pending)
- Docker: not yet verified (Phase 1)

**Ports / credentials / tokens:** None yet established. See `.env.example` for expected credential env vars.

**Deliverables checklist (§27) — checked off as completed:**
- [ ] `docker-compose.yml`
- [ ] `.env.example` ← IN PROGRESS (skeleton only, Phase 0)
- [ ] `orchestrator/`
- [ ] `meeting-simulator/`
- [ ] `human-bridge/`
- [ ] `sim-clock/`
- [ ] `accounting-engine/`
- [ ] `purge-manager/`
- [ ] `snapshot-manager/`
- [ ] `external-world/`
- [ ] `kpi-engine/`
- [ ] `branding-manager/`
- [ ] `narrative-db/`
- [ ] `dashboard/`
- [ ] `provisioning/`
- [ ] `litellm/config.yaml`
- [ ] `monitoring/`
- [ ] README

---

## LOG (newest first)

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
