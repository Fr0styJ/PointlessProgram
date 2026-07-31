# BUILD_LOG.md — FakeCo "Real Appliances" Build

---

## STATUS HEADER

| Field | Value |
|---|---|
| **Current Phase** | Phase 0 — Repo & build-log scaffolding |
| **Percent Complete** | ~3% (1/39 phases, weighted) |
| **Status** | IN PROGRESS |
| **Exact Next Action** | Create directory stubs for all custom deliverables listed in spec §27, each with a placeholder README.md stating which phase populates it |

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
