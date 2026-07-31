# dashboard/

**Populated by:** Phases 33–37 — Dashboard (shell + all tabs)

This directory will contain the Control Dashboard: a thin API gateway that routes each action
to whichever specific service owns it (SPEC_CLARIFICATIONS #13). NOT a monolith.

**Tabs and their populating phases:**
- **Simulation controls** (start/stop, worker scale, speed slider) — Phase 33
- **LLM status** (provider/fallback, override, usage/cost, burn rate) — Phase 33
- **Narrative view** (threads, action items, pending reactions/approvals, meetings) — Phase 33
- **Org Chart / HR tab** (roster, relationship view, Fire, Hire) — Phase 34
- **Payroll tab** (per-employee pay editor; raise→immediate, cut→pay_negotiation meeting) — Phase 34
- **Accounting tab** (cash balance, P&L deep link, expense-approval queue, payroll history, audit log) — Phase 34
- **External World tab** (BetaCorp feed, job-offer/resignation log, customer pipeline, revenue) — Phase 35
- **KPI / Performance tab** (scoreboards, performance-review log, mode toggle) — Phase 35
- **Company Direction tab** (textarea + Save + history) — Phase 35
- **Chaos tab** (per-appliance toggle, outage log, Trigger Event control) — Phase 36
- **Data Management tab** (full purge gated, scoped purge, Snapshots save/restore/delete) — Phase 36
- **Branding tab** (avatar/emoji picker with bulk apply) — Phase 36
- **`/tv` route** (TV wall — auto-cycling spectator view) — Phase 37
- **Errors panel** (recent unhandled exceptions across all custom services) — Phase 37
- **Deep links** into every real appliance including Principal accounts — Phase 37
- **Log tail** (live Traefik + Technitium log stream) — Phase 37

**Network placement:** `net_mgmt` (host-published so browser can reach it).
**Container access:** via `tecnativa/docker-socket-proxy` ONLY — never raw Docker socket.

**Dependencies:** Phases 12, 32 (sim controls), 10, 31 (LLM), 18 (narrative), 14, 20 (HR),
15, 24 (payroll/accounting), 21, 22 (external world), 23, 24 (KPI/performance),
13 (company direction), 27, 28 (chaos), 29 (purge/snapshots), 30 (branding).
