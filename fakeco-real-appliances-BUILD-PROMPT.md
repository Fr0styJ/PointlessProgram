# BUILD PROMPT: FakeCo Network Simulation — "Real Appliances" Edition

## Context for the agent

There is an existing project ("PointlessProgram" / FakeCo Network Simulation) that simulates
a 20-person corporate network using hand-rolled, minimal services: a bespoke Flask app for
mail, a bespoke Flask app for chat, a bespoke Flask app for tickets, a bespoke Flask app for
wiki, a custom DNS server, and nginx as a router — each backed by a lonely SQLite file.

**Do not reuse those bare-bones services.** Rebuild the same functionality using real,
mature, production-grade, off-the-shelf Docker images for every "appliance" role. The only
code that should be custom-written is the glue: the employee/worker-bot orchestrator, the
meeting simulator, the human-interaction bridge, the sim clock, the accounting engine, the
purge/snapshot manager, the external-world generator, the KPI/reporting engine, the
branding/asset manager, and a lightweight control dashboard. Everything else should be a real
piece of software a real company would actually run — including the books.

This is a living spec. Beyond the original "real appliances" scope, it now also covers:
1. A full observability/monitoring suite.
2. Persistent narrative memory so storylines actually continue instead of vanishing.
3. Token-efficiency requirements for the AI-generation side.
4. A simulated-meetings subsystem that seeds those storylines.
5. A human-in-the-loop layer — you can reply to emails, comment on tickets, and write wiki
   pages as yourself, and the simulated staff react to it.
6. A static "company direction" document that steers what the simulated staff work toward.
7. Dynamic headcount — hire and fire simulated employees at runtime.
8. Full financials — a real accounting appliance, role-based spending approvals, payroll with
   negotiated pay cuts, and quiet auditing/self-correction of the books.
9. Chaos controls and on-demand narrative crises.
10. Granular and full data purge, plus named save/load snapshots.
11. A speed slider — from a glacial "caveman in an office" pace up to a hard-capped 10x.
12. **An interpersonal relationship graph, a rival company and real customers, deterministic
    KPI/performance-review reporting, PTO, ambient flavor events, custom branding, and a
    spectator "TV wall" view.**

---

## 0. Build process & progress logging (read this first)

This section governs how the agent(s) building this work, not what the finished system does.
This build is large enough, and is being handed off across multiple tools/sessions/usage
limits, that continuity has to be treated as a first-class requirement, not an afterthought.

- Maintain a single `BUILD_LOG.md` at the repo root, committed to git alongside every code
  change, starting from the very first commit.
- Structure it in two parts:
  - A **Status header** at the very top, always kept current: current phase/milestone
    (referencing whatever phase breakdown this spec gets split into before building starts),
    rough percent complete, and — most importantly — the exact next action to take. A brand
    new agent instance with zero conversational history should be able to read only this
    header and know precisely where to pick up.
  - Below it, a reverse-chronological (newest-first) log of timestamped entries. Each entry:
    what was just completed, what's currently in progress, any decision or deviation from
    this spec and the reasoning behind it, any blockers hit, and which files/components were
    touched.
- **Update frequency: after every discrete step, and never let more than about 30 seconds of
  active work go by without writing an entry.** A file created, a service configured, a test
  run, a decision made — each gets its own entry rather than being batched up and written
  after the fact. If a step involves a long-running, non-interactive operation (a slow build,
  `docker compose up` pulling images, a long test run), write an entry immediately before it
  starts and immediately after it finishes, at minimum.
- This log is the continuity mechanism, not a nice-to-have: the plan is to run an initial pass
  through another tool before handing off to Claude Code proper, so if the current agent's
  context or usage runs out mid-task, the next instance — Claude or otherwise — needs to be
  able to read `BUILD_LOG.md` alone and continue exactly where things left off, without
  re-deriving decisions that were already made.
- Log every deviation from this spec, however small, with the reasoning. A future agent
  shouldn't have to guess why something doesn't match a given section.
- Explicitly reference the Deliverables checklist (section 27) in the log — check items off as
  they're completed, and note which sub-parts are done if an item is only partially finished.
- Record enough environment detail that a fresh instance doesn't have to rediscover it: ports
  in use, which appliances have already had first-boot setup completed, and which named
  credentials/tokens already exist. **Never write an actual secret value into the log** —
  reference credentials by the env var name they're stored under instead.
- Keep entries terse and factual, written for another agent to parse quickly — not a narrative
  status update for a human audience.

---

## 1. Goal

Stand up a fully Dockerized, network-isolated "fake company" — same 20 employees, same
departments, same wiki/mail/chat/tickets functionality as the original — built entirely from
genuine self-hosted server software, including a real double-entry accounting system with
both expenses and real revenue. Employees generate routine work, meeting-derived
follow-through, and reactions to whatever you personally say or do, colored by who actually
gets along with whom. The company has real outside pressure — a rival poaching underpaid
staff, real customers generating real revenue and real support load — and reports on its own
performance well enough to hand out raises without you lifting a finger, if that's what you
want. Anything that costs money clears a role-based approval before it touches the books. Pay
can rise freely but only falls through an actively negotiated HR meeting. All of it runs at
whatever pace you dial in, on top of a full monitoring stack, with the ability to save/restore
named snapshots and selectively or fully wipe generated data, and with financial math kept
strictly out of the LLM's hands.

---

## 2. Non-negotiable principle

For every functional role below, use the specified (or an equivalent-tier) real open-source
project's official Docker image — not a hand-written REST toy. If a substitution is made, it
must be a comparably mature, real-world piece of software, not a simplified reimplementation.

---

## 3. Service replacement map

| Role | Real replacement | Why | Integration surface |
|---|---|---|---|
| `mail` | **docker-mailserver** + **Roundcube** | Real MTA, real mailboxes, real filtering, real Sieve vacation-responder (used for PTO, section 15) | SMTP + IMAP; also where *you* read/reply as yourself |
| `chat` | **Mattermost** | Real channel chat + REST/websocket API, real custom status API (PTO, section 15), real custom emoji/avatar APIs (branding, section 17) | Bot accounts per employee; you get a real human account too |
| `tickets` | **Zammad** | Real, mature helpdesk with full REST API | Per-employee API tokens; hosts expense approvals (10.2) and customer support tickets (11.2) |
| `wiki` | **Wiki.js** | Real wiki, markdown, GraphQL API, versioning | GraphQL page create/update; you edit as yourself through its normal editor |
| `web_public` | **WordPress** | Real CMS pattern | Occasional hits for HTTP log realism |
| `web_portal` | **Nextcloud** | Real intranet appliance | Occasional API/webdav hits |
| `dns` | **Technitium DNS Server** | Real DNS, own UI+API, query logging | Resolves `*.fakecorp.internal` |
| `router` | **Traefik v3** | Real reverse proxy, structured logs, own dashboard | Routes internal HTTP; multi-homed onto `net_mgmt` too (section 22) so your browser can reach the office apps |
| **Accounting** | **Akaunting** | Real double-entry accounting: chart of accounts, transactions, P&L, balance sheet | System of record for all money, expense *and* revenue (section 11.2) |
| `llm_proxy` | **LiteLLM Proxy** | Real multi-provider LLM gateway (DeepSeek/Anthropic/OpenAI/local), routing, fallback, cost tracking | Every custom component calls this one endpoint |
| Monitoring | **Prometheus + Grafana + Loki + Promtail + cAdvisor + node-exporter** | Real observability stack | Scrapes/aggregates everything above, incl. KPI/financial panels |
| Container control | **tecnativa/docker-socket-proxy** | Real least-privilege wrapper around the Docker Engine API | Dashboard uses this, never the raw socket, to start/stop appliances |
| Narrative memory store | **PostgreSQL** (shared instance, separate schemas) | Real relational store for every workflow table in this spec | Read/written by every custom component |
| `simulator` (worker bots) | Custom | Personas driving real protocols | — |
| Meeting simulator | Custom | No off-the-shelf tool simulates fake meetings (incl. pay negotiation, performance review, crisis response) | Writes to Postgres + Wiki.js + Mattermost |
| Human interaction bridge | Custom | No off-the-shelf tool fans out "the CEO just replied" to bots | Polls/receives webhooks from mail/Mattermost/Zammad/Wiki.js |
| Sim clock | Custom | No off-the-shelf tool decouples a simulated calendar from wall-clock at a variable rate | Tiny ticker + one Postgres row |
| Accounting engine | Custom | Deterministic approval routing, payroll runs, revenue posting, audit/reconciliation | Calls Akaunting's API; never does financial math via the LLM |
| Purge/snapshot manager | Custom | No off-the-shelf tool understands "wipe/backup just the wiki, everywhere it's referenced" across this whole stack | Per-appliance bulk-delete + backup/restore + narrative DB cleanup |
| External-world generator | Custom | No off-the-shelf tool simulates a rival company or customer base | Injects mail/tickets from simulated external parties; drives revenue posting |
| KPI & reporting engine | Custom | Deterministic aggregation across every appliance's own data | Feeds performance reviews, the weekly digest, and Grafana |
| Branding/asset manager | Custom | No off-the-shelf tool manages "theme my fake company's avatars/emoji" | Pushes images through each appliance's real avatar/emoji upload APIs |
| `dashboard` | Custom control panel | No off-the-shelf tool does "control my fake company" | Talks to every service above; also serves the TV-wall view (section 18) |

---

## 4. Persistent memory & narrative continuity

Nothing should happen exactly once.

### 4.1 Narrative memory store (PostgreSQL schema, minimum viable)

- `narrative_threads` — id, topic, department, status (`open`/`in_progress`/`resolved`/`archived`), summary, created_at, updated_at *(sim-time — section 19)*
- `narrative_events` — id, thread_id, employee_id (nullable), origin (`ai`/`human`), source_type (`meeting`/`email`/`chat`/`ticket`/`wiki`/`payroll_change`/`approval`/`customer`/`external`), source_ref, short_summary, created_at
- `meetings` — id, thread_id, meeting_type (`standup`/`cross_functional`/`pay_negotiation`/`performance_review`/`crisis_response`), attendees (json), agenda, transcript_summary, decisions (json), outcome (json), created_at
- `action_items` — id, meeting_id (nullable), thread_id, owner_employee_id, description, due_at, status (`open`/`done`/`overdue`/`orphaned`), resulting_event_ids (json)
- `pending_reactions` — id, thread_id, target_employee_id, triggering_event_id, status (`pending`/`done`)
- `pending_approvals` — id, expense_request_ref, requester_employee_id, approver_employee_id_or_principal, amount, status (`pending`/`approved`/`rejected`/`escalated`)
- `system_audit_log` — id, actor, action, detail, created_at — **survives every purge, including the full purge** (section 14.3)

Ambient flavor content (section 16) is deliberately excluded from this schema entirely — it
has no thread, no consequence, and shouldn't cost more than a single cheap LLM call.

### 4.2 Content origin

- **Work-related**: routine content from an employee's role/persona/department weighting.
- **Meeting-derived**: content fulfilling an open `action_item`; must reference the source and mark it progressed/done.
- **Human-derived**: content reacting to something you personally wrote (section 7). Always takes priority.

### 4.3 Continuity loop the orchestrator must implement, in priority order

1. **React to the Principal.** Resolve `pending_reactions` first, on the higher-tier model regardless of what tier the content type would normally get.
2. **Resolve pending approvals** owned by this employee (section 10.2) — rule-based decision, LLM only writes the explanatory comment.
3. **Fulfill open/overdue `action_items`** (evaluated against sim-time).
4. **Generate routine work-related filler**, gated by business-hours weighting (section 19.4) and skipped entirely for anyone currently on PTO (section 15).

For all four: pull only a small, targeted slice of memory — the specific thread's summary,
last 1-2 events, current company direction (section 8), and, when relevant, a one-line note
on the relationship (section 5) between the people involved — never the full history.

---

## 5. Interpersonal relationships

- `employee_relationships` — employee_a_id, employee_b_id, relationship_type
  (`ally`/`rival`/`mentor`/`mentee`/`neutral`), affinity_score (-100 to 100), last_updated
  (sim-time), notes.
- Seeded lightly at hire time (a few starting pairings, cheap-tier or simple deterministic
  assignment) and evolved from ordinary events, not dedicated LLM calls: the meeting
  simulator's existing generation call (section 6) already produces attendee stances per
  decision as a cheap structured field, and agreement/disagreement between two attendees nudges
  their affinity by a small deterministic delta. No extra LLM call is spent purely to "update
  relationships."
- Consumed by: meeting attendee selection (weighted toward existing allies on a given topic),
  who gets cc'd/looped in on email and chat (skewed toward allies, away from rivals), and the
  one-line relationship note injected into generation context (section 4.3).
- Surfaced on the dashboard's Org Chart / HR tab (section 25) as a simple relationship view —
  a node/edge visualization is a natural fit, not a required one.

---

## 6. Meeting simulation

- Runs on its own schedule in sim-time, weighted toward simulated business hours (section 19).
- `meeting_type`: `standup` / `cross_functional` / `pay_negotiation` (section 10.3) /
  `performance_review` (section 12.2) / `crisis_response` (section 13.2).
- Attendee selection draws only from currently active employees not on PTO (sections 9, 15),
  weighted by relationship data (section 5) for topic relevance.
- Calls the LLM (heavier tier) to produce attendees, agenda, discussion, decisions, and either
  generic action items or a structured `outcome` (for pay negotiations), explicitly weighed
  toward the current company direction (section 8).
- Publishes minutes to a Wiki.js page (`meeting-notes`) and a Mattermost summary — **except**
  `pay_negotiation` and `performance_review` meetings, which stay HR-private, not posted to a
  public channel.
- Resulting action items feed continuity-loop priority 3 (section 4.3).

---

## 7. Human-in-the-loop management (the Principal)

- One real account for you across every appliance: a mailbox (`PRINCIPAL_EMAIL`) on
  docker-mailserver, a Mattermost user, a Zammad agent account, a Wiki.js editor account.
  Display name via `PRINCIPAL_NAME`.
- You interact through the real appliance UIs directly; the dashboard deep-links into these
  rather than duplicating them — including your Zammad agent view for approving over-threshold
  expense requests (section 10.2).
- **Human Interaction Bridge** (custom): detects Principal-authored content via native
  webhooks (Mattermost/Zammad/Wiki.js) or IMAP polling (mail), converts each into
  `narrative_events(origin='human')`, and writes a `pending_reactions` row for whoever it was
  addressed to.
- If you fire an employee a reaction/approval was pending on, reassign it the same way
  `action_items` get reassigned (section 9).

---

## 8. Company direction & strategic goals

- `company_directives` table holding the current direction statement, versioned.
- Editable via textarea + Save in the dashboard; synced to a pinned Wiki.js page.
- Injected as a fixed block in every LLM prompt — part of the cached static prefix from the
  token-efficiency tips (section 20.1).
- The meeting simulator weighs decisions toward it; an unrelated decision is the exception.

---

## 9. Roster management (hire / fire)

- Employee roster in Postgres: `id, name, email, department, role, personality, status
  (active/vacant/terminated/resigned), hired_at, terminated_at, mattermost_id,
  zammad_agent_id, wiki_user_id, mailbox_address`, plus payroll fields (section 10.3).
  `resigned` can come out of a failed pay negotiation (10.3) or an unaddressed BetaCorp job
  offer (11.1) — not something you set directly.
- Dashboard **Org Chart / HR** tab: roster list with status and relationship view (section 5),
  a **Fire** button, and a **Hire** form (name, department, personality, starting pay).
- **Fire**: status -> `terminated`; deactivate (never delete) accounts everywhere; owned open
  items get flagged for reassignment or explicit orphaning.
- **Vacant**: no activity generated; department volume drops proportionally.
- **Hire**: inserts the roster row and runs the same per-employee provisioning routine used at
  first boot, for just that one person, including a starting relationship seed (section 5) and
  a default branding avatar (section 17).

---

## 10. Accounting & payroll

### 10.1 Ledger appliance

- **Akaunting** is the real system of record for money: chart of accounts, transactions, real
  P&L / balance-sheet reports — including customer revenue (section 11.2), not just expenses.
- Akaunting owns the ledger; Postgres only tracks workflow state and stores the resulting
  Akaunting transaction ID.
- **All financial math is deterministic code, never the LLM.** Balances, thresholds, payroll
  totals, burn rate, revenue postings — all plain backend logic. The LLM only narrates around
  numbers already decided by code.

### 10.2 Expense approval workflow

- Anything that costs money is filed as a Zammad ticket (`type = expense_request`).
- Deterministic `approval_policy` (`role -> auto_approve_limit -> escalates_to_role`), default:

| Role tier | Auto-approve up to | Escalates to |
|---|---|---|
| Individual contributor | $25 | Department lead |
| Department lead | $500 | Principal (you) |
| Principal (you) | Unlimited | — final approver |

- Rule-based routing/decision; an over-threshold request becomes a ticket assigned to your
  Zammad agent account. If the designated approver is on PTO (section 15), it routes to a
  configured backup or escalates a tier automatically.
- Only on approval does the Accounting Engine post to Akaunting. Resolving owned approvals is
  continuity-loop priority 2 (section 4.3).

### 10.3 Payroll

- Per-employee pay, pay frequency (sim-time cadence), last-change timestamp/reason.
- Deterministic **Payroll Run**, scheduled on the sim clock (section 19), posts total pay for
  active employees to Akaunting each cycle. Vacant/terminated draw no pay.
- **Raises apply immediately** — no meeting required.
- **Pay cuts never apply directly** — instead open a `pay_negotiation` meeting (section 6)
  between HR and the employee, seeded with the proposed figure. The meeting's structured
  outcome (agreed figure / compromise / resignation) is what actually gets applied.
- Underperformance (section 12.2) never triggers an automatic cut — only a conversation.

### 10.4 Quiet audit & correction

- A deterministic **Books Auditor**, scheduled periodically in sim-time (and callable on
  demand — see the "surprise audit" crisis preset, section 13.2), reconciles debits/credits
  and that every approval/payroll record that should have posted actually did.
- Corrections auto-post as clearly-tagged "audit correction" transactions plus a
  `system_audit_log` entry — quiet in that it runs unattended, never quiet about what it found.

---

## 11. External world: rivals & customers

### 11.1 BetaCorp (rival company)

- A sim-time-scheduled "external world" generator posts occasional industry/rival flavor news
  (a wiki article or #general mention) — cheap tier, no thread/action-item overhead, same
  no-consequence pattern as ambient events (section 16).
- `market_benchmark` (role/department -> benchmark pay) drives job-offer risk: a deterministic
  check computes each employee's gap to benchmark and probabilistically (weighted by that gap,
  never by LLM judgment) selects someone to receive a job-offer email from a simulated
  BetaCorp recruiter.
- Whether they stay or leave is a deterministic probability against the pay gap and tenure —
  never an LLM decision. A near-miss surfaces as a `pending_reactions`-style flag ("Alice
  mentioned an outside offer") so you can counter with a raise before losing them; an
  unaddressed large gap can resolve to `resigned`, feeding the vacancy/rehire flow (section 9).
- Implementation note: docker-mailserver needs to accept mail with an external-looking
  envelope sender injected directly by the orchestrator inside this closed network — nothing
  here is meant to actually resolve external DNS/SMTP.

### 11.2 External customers

- `customers` — company_name, contact_name, contact_email, relationship_status
  (`prospect`/`active`/`at_risk`/`churned`), assigned_sales_rep_id, assigned_support_rep_id.
- Customers generate real inbound traffic on the normal sim-time/business-hours cadence:
  prospects email Sales, active customers file real Zammad tickets against Support;
  escalations/renewals use the heavier LLM tier like other meeting-derived content.
- **Revenue, not just expense**: closing a deal posts a real revenue transaction in Akaunting
  (section 10.1) against that customer. The dollar amount comes from a deal-size field set
  when the sales thread was opened, not invented at invoice time — deal-closing is a
  deterministic outcome of the thread reaching a decision, never an LLM-tallied number.
- At-risk customers churn deterministically if support tickets sit open past a configured
  sim-time threshold — a concrete, code-checked consequence, not a vibe.

---

## 12. KPIs, performance reviews & reporting

### 12.1 KPI scoreboards

- Deterministic daily (sim-time) rollup pulling directly from each real appliance's own data:
  Zammad ticket counts/resolution time, Wiki.js page counts, Mattermost message counts, and
  Sales revenue (section 11.2) from Akaunting — stored in `kpi_snapshots`
  (department/employee, metric, value, sim_time). No LLM involved — pure aggregation, same
  principle as accounting (section 10.1).
- Surfaced on a dashboard **KPI / Performance** tab with trend charts, mirrored into Grafana
  (section 21).

### 12.2 Performance review cycle

- Deterministic scheduled job (sim-time, default quarterly-equivalent, tunable) reads recent
  `kpi_snapshots`, normalizes against department peers, and computes a suggested raise tier
  via a plain formula (e.g. top quartile +5%, second +2%, rest +0%) — the formula decides the
  number, never the LLM.
- **Runs fully automatically by default, no input required**: qualifying raises apply the same
  frictionless way as any other raise (section 10.3), logged as a `narrative_event`.
- Underperformance never triggers an automatic cut — it opens a `performance_review` meeting
  (section 6) instead, a conversation rather than a penalty.
- A dashboard toggle can switch to "review & approve" mode (proposed raises queue for your
  sign-off) — off by default, since automatic-with-no-input is what was asked for.

### 12.3 "This Week at FakeCo" digest

- Weekly (sim-time) job deterministically selects the past sim-week's notable events — newly
  resolved threads, crises, hires, customer wins/losses — explicitly excluding HR-sensitive
  threads (pay negotiations, terminations, performance reviews), same privacy boundary as
  section 6.
- One LLM call (cheap/mid tier, since selection was free) turns that pre-selected list into a
  company-newsletter-voiced digest, published to Wiki.js and posted to Mattermost #general.

---

## 13. Chaos / service availability controls & crisis events

### 13.1 Service availability

- Dashboard toggle per real appliance that actually stops/starts that container, via
  **`tecnativa/docker-socket-proxy`** (never the raw socket), restricted to
  `START`/`STOP`/`RESTART` on labeled containers only.
- Orchestrator treats outages as first-class: reachability check before any action, queue in
  `pending_actions` if down (wall-clock-based retry — a container being down is a physical
  fact independent of sim speed), optional visible reaction elsewhere
  (`reactive_outage_behavior`), logged as a `narrative_event` phrased in sim-time terms.

### 13.2 Manually-triggered crisis events

- The Chaos tab also gets a **Trigger Event** control: a dropdown of canned scenarios (data
  breach, surprise audit, viral public-site complaint, extensible via config) plus a free-text
  field for a custom scenario.
- Triggering one opens a high-priority `narrative_thread` (`crisis`), immediately schedules a
  `crisis_response` meeting (section 6) with a forced relevant attendee list, and seeds
  downstream `action_items` — the same continuity machinery as any other meeting, just
  invoked on demand.
- "Surprise audit" should actually invoke the real Books Auditor (section 10.4) and narrate
  its real findings rather than inventing a result.
- Crises may carry a real cost, routed through the normal approval flow (10.2) like any other
  expense.

---

## 14. Data purge, reset & snapshots

### 14.1 Full purge ("Clear Everything")

- Wipes every appliance's content and the entire narrative memory store, resets the roster to
  the original starting set, resets the sim clock, clears the company direction to default.
- Irreversible: a plain-language red warning plus a required typed confirmation phrase (e.g.
  `DELETE EVERYTHING`) before the button becomes clickable.

### 14.2 Scoped purge

- Independent checkboxes: Emails, Chat, Tickets, Wiki, Meetings & narrative memory, Accounting
  ledger, External world (customers/BetaCorp state), KPI history, Roster (reset to default),
  Company direction (reset to default). Anything unchecked stays untouched.
- Still requires an explicit confirmation, lighter than the full-purge gate.
- **Purge Manager** (custom): per scope, calls each appliance's own bulk-delete/reset
  mechanism or truncates its own database as a fallback, then cleans up the corresponding
  `narrative_events` and orphans/cascades anything that only referenced now-deleted content.

### 14.3 Immutable system audit log

- `system_audit_log` is explicitly excluded from every purge, including the full purge.

### 14.4 Named snapshots (save / load)

- **Snapshot Manager** (custom, sibling to the Purge Manager): captures the full state — every
  appliance's own database, docker-mailserver's Maildir volume, the narrative Postgres schema,
  sim clock, roster, company direction — into a named, sim-time-tagged snapshot.
- Dashboard **Snapshots** tab (grouped with Data Management): list, **Save Snapshot Now**,
  **Restore**, **Delete**.
- Restoring is destructive to current unsaved state and requires the same confirmation as a
  scoped purge. Consistent restore needs the affected containers briefly stopped — a real
  constraint of doing this properly against real databases rather than in-memory toy state.

---

## 15. PTO / out-of-office

- `pto_calendar` — employee_id, start_sim_time, end_sim_time, reason (flavor only).
- Deterministic scheduler picks upcoming PTO windows per employee on a light sim-time-based
  probability, spaced so nobody's out constantly.
- On PTO start: a real Sieve vacation auto-responder on their docker-mailserver mailbox and a
  real Mattermost custom status ("Out of Office," with return date) — both genuine, built-in
  appliance features, no custom auto-reply logic needed. Both revert automatically at end.
- Continuity loop skips new proactive routine work for anyone currently on PTO, and allows a
  small "catching up after vacation" burst right when they return.
- **Approval delegation**: an approver on PTO (section 10.2) temporarily routes to a backup or
  escalates a tier automatically, rather than stalling requests behind someone who's out.

---

## 16. Ambient flavor events

- Low-frequency sim-time-scheduled generator (a few times per sim-week) posts a single
  cheap-tier LLM message from a config list of mundane categories (kitchen mishap,
  printer/equipment gripe, small talk) to a general channel.
- Deliberately outside the narrative memory system entirely — no thread, no action item, no
  follow-up — so the cheapest content never accidentally becomes "important" or costs more
  than one cheap call. Direct reinforcement of the token-efficiency principle (section 20.1).

---

## 17. Branding & appearance

- First-boot provisioning uploads a themed custom-emoji pack to Mattermost (a real, built-in
  feature) and sets initial employee avatars via each appliance's own profile-image API
  (Mattermost, Zammad, Wiki.js all support this natively).
- Dashboard **Branding** tab:
  - A bundled or user-uploaded library of avatar images and an emoji pack, managed by a small
    **Branding/Asset Manager** (custom) mapping `employee_id -> avatar_asset_id`.
  - Per-employee avatar picker, plus bulk actions — randomize all, apply one set to everyone
    selected, reset to defaults — so you can restyle some or all employees at once.
  - An "Apply" action pushes the selected images through each appliance's real avatar-upload
    API; only the selection/bulk-push logic is custom, rendering is entirely the real appliance's.

---

## 18. Spectator "TV wall" view

- A dedicated, no-controls dashboard route (e.g. `/tv`) auto-cycling existing panels at a
  larger, screen-friendly scale: live chat feed, live ticket feed, financial snapshot, KPI
  highlights, sim-time/speed display, recent digest highlights — meant to run passively on a
  second screen.
- Primarily a presentation-layer addition: it composes data the dashboard (section 25) already
  exposes, and shouldn't need meaningful new backend logic beyond a "curated summary" endpoint.

---

## 19. Simulation speed control

### 19.1 Sim clock

- `sim_clock`: `sim_time`, `last_wall_checkpoint`, `speed_multiplier`. A lightweight ticker
  advances it: `sim_time += wall_elapsed_since_last_tick * speed_multiplier`.
- Every time-aware decision anywhere in this spec reads `sim_time`, never wall-clock directly.

### 19.2 The slider

- Continuous range **0.1x ("Caveman") to 10x ("Fast-forward")**, default **1.0x ("Normal")**,
  labeled presets at 0.1x/0.25x/0.5x/1x/2x/5x/10x. Changes apply immediately.
- **Normal (1x)**: one simulated hour equals one wall-clock hour, calibrated to 19.3.
- **10x is a hard cap that only compresses time**, never inflates the behavioral model.
- Below 1x genuinely slows down.

### 19.3 Normal (1x) baseline behavioral calibration (default, tunable)

| Signal | Default normal (1x) rate | Role weighting |
|---|---|---|
| Emails sent | ~15 / employee / sim-workday | Sales heaviest (~25), HR lightest (~10) |
| Chat messages | ~20 / employee / sim-workday | Support/Ops heaviest (~30), Sales/HR lighter (~15) |
| Tickets opened/commented | ~10 / sim-workday, concentrated in Support | Support ~10, others ~0-2 incidental |
| Wiki edits | ~1 / employee / sim-week | HR/Ops heaviest |
| Meetings | 1 daily department standup + 1 cross-functional / sim-week | plus ad hoc, pay-negotiation, performance-review, and crisis meetings |

### 19.4 Business-hours gating

Default: simulated Mon-Fri 9am-6pm gets full weighting; nights/weekends drop to a light
trickle (~5-10% of daytime rate).

### 19.5 Cost implication

LLM call volume tracks sim-time throughput: 10x burns roughly 10x the tokens per wall-clock
hour versus 1x. The dashboard's LLM status panel shows a live estimated $/wall-clock-hour burn
rate, reconciled into Akaunting as a real recurring expense line (section 21).

---

## 20. LLM gateway requirements

- **LiteLLM Proxy** is the single entry point for all AI content generation.
- Provider priority: DeepSeek (primary) -> Anthropic (Claude) -> OpenAI (ChatGPT) -> local
  model — LiteLLM fallback chain. API keys via env vars only.
- LiteLLM's own cost/usage tracking exposed through the dashboard alongside the speed-adjusted
  burn-rate estimate (19.5).

### 20.1 Token-efficiency requirements (three concrete tips for the coding agent)

1. **Cache the static prefix, vary only the small tail.** Fixed system instructions + persona +
   JSON schema + company direction first, byte-identical across calls; enable
   DeepSeek/Anthropic prompt caching in LiteLLM.
2. **Tier models by task weight.** Cheapest model for routine filler and ambient events
   (section 16); reserve the reasoning-tier model for meetings, meeting-derived content, and
   anything reacting to the Principal.
3. **Compact memory instead of accumulating it.** Only the specific thread's short summary +
   last 1-2 events, never full history; periodically collapse resolved/archived threads.

Related principle (section 10.1): deterministic code handles every dollar figure, every KPI
number, every relationship-affinity delta, every job-offer probability — the LLM only
narrates around numbers already decided by code.

---

## 21. Full monitoring suite

- **cAdvisor** + **node-exporter** — container/host metrics.
- **Prometheus** — scrapes cAdvisor/node-exporter, LiteLLM's `/metrics`, app-level endpoints.
- **Loki + Promtail** — aggregates Traefik/Technitium/container logs.
- **Grafana** — dashboards: container health; HTTP+DNS+mail traffic; per-appliance activity
  rate; LLM token spend/cost (speed-annotated); narrative backlog; headcount by status;
  appliance up/down state; sim-time vs wall-clock; cash balance/burn rate/runway/payroll total
  from Akaunting; KPI trends and customer pipeline/revenue (sections 11-12).
- Isolation note: Prometheus may be multi-homed onto the isolated app networks purely to
  scrape targets without breaking isolation.

---

## 22. Network architecture

| Network | Contains | Internet/host access |
|---|---|---|
| `net_clients` | orchestrator, meeting simulator, human bridge, sim clock, external-world generator, Traefik, Technitium DNS | No |
| `net_office` | Wiki.js, Zammad, Mattermost, Nextcloud, Akaunting | No |
| `net_mail` | docker-mailserver, Roundcube | No |
| `net_dmz` | WordPress + DB | No |
| `net_data` | shared PostgreSQL (incl. Akaunting's own database, snapshot storage) | No |
| `net_llm_bridge` | LiteLLM proxy only | Yes — its only job is reaching the LLM providers |
| `net_mgmt` | control dashboard, docker-socket-proxy, Prometheus, Grafana, Loki | Yes — host-published |

Implementation notes:
- Port-publishing works on `internal: true` networks too — `net_mgmt` can be made fully
  internal if you want it tighter.
- Traefik is also multi-homed onto `net_mgmt`, same reasoning as Prometheus, purely so your
  browser can reach the office apps' hostnames without granting other networks a new route out.

---

## 23. Reliability & error handling

- Every financial mutation is atomic (DB transactions) — approvals, ledger posting, payroll,
  revenue posting.
- Idempotency keys on anything that posts money, checked before the outage-retry queue
  (section 13.1) can ever double-post.
- Structured error logging surfaced (Loki + a dashboard "Errors" panel), never a silent
  crash-loop, across every custom service in this spec.
- Input validation on every dashboard/control-API request.
- Negative cash balance is a valid business state, not a bug — approval policy (10.2)
  automatically tightens as reserves run low.

---

## 24. Orchestrator ("simulator") requirements

- Reads the roster (`active`/`vacant`/`terminated`/`resigned`), sim clock, PTO calendar, and
  relationship graph every cycle.
- Implements the full priority-ordered continuity loop (section 4.3).
- Implements reachability checks + idempotent `pending_actions` retry queue.
- Hosts (or coordinates with) the scheduled deterministic jobs from this spec: meeting
  scheduling, payroll runs, the Books Auditor, the external-world generator, KPI rollups, the
  performance-review cycle, the weekly digest, PTO scheduling, and ambient flavor events —
  each reading its own cadence from the sim clock.
- Each action hits a real backend instead of a toy REST call.
- Exposes a control API covering every dashboard action in section 25.

---

## 25. Control dashboard requirements

- Simulation controls: start/stop, worker scale, speed slider (section 19).
- LLM status: provider/fallback, override, usage/cost view, speed-adjusted burn rate.
- Narrative view: open threads, action items, pending reactions/approvals, meetings.
- **Org Chart / HR tab**: roster, relationship view (section 5), Fire, Hire.
- **Payroll tab**: per-employee pay editor — raises apply immediately, cuts route into a
  pay-negotiation meeting.
- **Accounting tab**: cash balance, P&L/balance-sheet (linked from Akaunting), expense-approval
  queue, payroll history, audit-correction log.
- **External World tab**: BetaCorp news feed, job-offer/resignation log, customer
  pipeline/at-risk list, revenue by customer.
- **KPI / Performance tab**: department/employee scoreboards, performance-review log and mode
  toggle (automatic vs review-and-approve).
- **Company Direction tab**: editable textarea + history.
- **Chaos tab**: per-appliance up/down toggle, status, outage log, and the crisis Trigger Event control.
- **Data Management tab**: full purge (hard-gated), scoped purge, and Snapshots (save/restore/delete).
- **Branding tab**: avatar/emoji picker with bulk apply.
- **`/tv` route**: the spectator TV-wall view (section 18).
- **Errors panel**: recent unhandled exceptions across custom services.
- Deep links/embeds into every real appliance, including your own Principal accounts.
- Tail/stream Traefik and Technitium logs for a live feed.

---

## 26. Deployment requirements

- Single `docker compose up -d` for the entire stack.
- `.env.example`: LLM provider keys, initial admin credentials for every appliance including
  Akaunting, Postgres credentials, `PRINCIPAL_EMAIL`/`PRINCIPAL_NAME`, default
  `speed_multiplier`, starting cash balance.
- Resource note: budget roughly 8-10 GB RAM and several GB of disk with everything running.
  LLM call volume scales with speed; snapshot storage scales with how often you save.
- First-boot section: admin setup, account/token generation for the 20 employees and the
  Principal, Akaunting chart-of-accounts setup, and an initial branding pass.

---

## 27. Deliverables checklist

- [ ] `docker-compose.yml` — full topology from section 22
- [ ] `.env.example`
- [ ] `orchestrator/` — worker bots, continuity loop, retry queue, real-protocol integrations, all scheduled jobs listed in section 24
- [ ] `meeting-simulator/` — all five meeting types, publishing, HR-privacy exclusions
- [ ] `human-bridge/` — mail poller + webhook receivers
- [ ] `sim-clock/` — ticker + `set_speed` API
- [ ] `accounting-engine/` — approval routing, payroll, revenue posting, books auditor
- [ ] `purge-manager/` + `snapshot-manager/` — per-appliance purge and backup/restore adapters
- [ ] `external-world/` — BetaCorp job-offer logic, customer traffic generation, churn/revenue logic
- [ ] `kpi-engine/` — daily rollups, performance-review formula, weekly digest selection
- [ ] `branding-manager/` — asset library + bulk avatar/emoji push
- [ ] `narrative-db/` — Postgres migrations for every table in this spec
- [ ] `dashboard/` — every tab in section 25, including `/tv`
- [ ] `provisioning/` — per-employee (and Principal) account creation, single-add capable
- [ ] `litellm/config.yaml` — provider priority, fallback, per-task routing, caching config
- [ ] `monitoring/` — Prometheus/Loki/Promtail config, Grafana dashboards (incl. KPI/financial panels)
- [ ] README — deployment, first-boot setup, resource requirements, troubleshooting, how to use every tab

---

## 28. Assumptions made while drafting this (swap freely)

- All new cadences (BetaCorp job-offer checks, performance reviews, weekly digest, PTO
  frequency, ambient flavor events) are estimated starting points, exposed as config.
- The crisis-preset list (section 13.2) is a starting set, meant to be extended.
- docker-mailserver's acceptance of external-looking envelope senders (BetaCorp, customers) is
  a closed-network configuration choice, not real external mail delivery.
- Snapshot save/restore requires briefly stopping affected containers for consistency — a real
  constraint of doing this against real databases rather than in-memory state.
- Performance-review raises apply automatically by default; the review-and-approve mode exists
  but is off unless you turn it on.
- Approval thresholds, payroll cadence, and the 19.3 behavioral rates remain estimated starting
  points from earlier revisions, still exposed as editable config.
- Akaunting remains the chosen accounting appliance; Firefly III is a viable swap.
- Every other appliance choice from earlier revisions (Mattermost, Zammad, Wiki.js,
  docker-mailserver + Roundcube, Traefik, Technitium, WordPress, Nextcloud,
  docker-socket-proxy) is unchanged; drop-in swaps remain available for any of them.
- LiteLLM Proxy remains effectively a hard requirement given DeepSeek-primary + multi-provider
  fallback + per-task routing + caching all needing to live in one place.
