# monitoring/

**Populated by:** Phase 2 (cAdvisor, node-exporter, Prometheus — minimal slice) + Phase 11 (Loki, Promtail, Grafana — base dashboards) + Phase 31 (KPI/financial/LLM-burn panels)

This directory will contain all observability stack configuration (spec §21).

**Phase 2 — Minimal slice (pulled forward for early health visibility):**
- cAdvisor: container metrics
- node-exporter: host metrics
- Prometheus: scrapes cAdvisor + node-exporter; targets confirmed `up` for every phase

**Phase 11 — Observability completion, pass 1:**
- Loki: log aggregation
- Promtail: log shipping from Traefik, Technitium, all appliance containers
- Grafana base dashboards:
  - Container health
  - HTTP+DNS+mail traffic
  - Per-appliance activity rate
  - Appliance up/down state

**Phase 31 — Observability completion, pass 2 (needs real data to exist first):**
- Grafana panels added:
  - LLM token spend/cost (speed-annotated)
  - Narrative backlog
  - Headcount by status
  - Sim-time vs wall-clock
  - Cash balance / burn rate / runway / payroll total (from Akaunting)
  - KPI trends
  - Customer pipeline / revenue

**Isolation note:** Prometheus may be multi-homed onto isolated app networks purely to scrape
targets without breaking network isolation (spec §21).

**Network placement:** `net_mgmt` (host-published).

**Dependencies (Phase 2):** Phase 1. (Phase 11/31 need later phases for meaningful data.)
