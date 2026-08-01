# Future Plans

Deferred phases/ideas — not scheduled for the current build pass. Each entry should stay
self-contained enough to pick up later without re-deriving context.

---

## Phase 32 — Simulation speed slider, full integration (DEFERRED 2026-07-31)

Status: **Not being built now.** User explicitly deferred this phase during the 27/28/31/32
planning round ("Put this function in a 'Future plans.md' file, lets not do it now"). Full
design content below is carried over verbatim from `PLAN_PHASES_27_28_31_32.md` (which has
been trimmed to 27/28/31 only) so nothing is lost if this gets picked up later.

**Hard dependency**: needs Phase 31 (LLM cost-reading logic) built first, since Phase 32's
LLM-burn reconciliation reuses Phase 31's LiteLLM-usage-reading logic. Phase 31 has since
been completed — see BUILD_LOG.md — so this dependency is satisfied whenever Phase 32 is
picked back up.

### 1. What it is

Spec §19.2-19.5 (`fakeco-real-appliances-BUILD-PROMPT.md:490-526`) and `PHASES.md:683-700`:
the `set_speed` API must expose the full continuous 0.1x-10x range with labeled presets
(0.1/0.25/0.5/1/2/5/10x), applying immediately. At any speed, `sim_time` must advance at
exactly that multiple of wall-clock (verified via a measured interval), while the underlying
*behavioral rates* (filler frequency per sim-hour, per §19.3's per-employee/per-sim-workday
targets) stay calibrated to their 1x targets — i.e., compression must not also inflate the
rate. Business-hours gating (full weight Mon-Fri 9am-6pm sim-time, 5-10% trickle otherwise,
§19.4) must be observable across a simulated day/night cycle. A recurring "LLM burn" expense
line must reconcile into Akaunting at a rate matching the dashboard's estimated
$/wall-clock-hour figure (§19.5).

`docker-compose.yml` shows `SPEED_MULTIPLIER` is currently a static env var
(`"${SPEED_MULTIPLIER:-1.0}"`) baked in at container start, not a live mutable value — "full
integration" means building the actual runtime `set_speed` API and propagating it, not just
wiring up something that mostly already works.

### 2. What already exists vs. what's missing

- **Exists:** `sim-clock/main.py` (Phase 12) already implements the `sim_time += wall_elapsed
  * speed_multiplier` ticker per §19.1, reading `SPEED_MULTIPLIER` from its env var at startup.
  It has a `/health` endpoint and is the authoritative sim-time source every other service
  (`SIM_CLOCK_URL`) already reads from.
- **Missing:**
  - A live `PUT/POST /speed` endpoint on `sim-clock` that changes `speed_multiplier` in the
    `sim_clock` table at runtime rather than only reading a static env var at boot — need to
    confirm whether the ticker already re-reads the DB row's `speed_multiplier` on every tick
    or only reads the env var once at startup.
  - Any behavioral-rate calibration logic anywhere — nothing in orchestrator, meeting-simulator,
    human-bridge, or external-world currently reads `speed_multiplier` to adjust its own
    per-sim-hour generation cadence independent of tick frequency. Needs an audit ensuring every
    per-employee/per-workday rate check reads `sim_time` deltas, not wall-clock-tick counts.
  - Business-hours gating: no evidence of a 9am-6pm Mon-Fri sim-time check gating generation
    rate anywhere yet.
  - The recurring "LLM burn" Akaunting expense line: no evidence this exists — needs a new
    scheduled job (natural home: orchestrator's tick loop) that reads LiteLLM's live usage/cost
    data, computes a $/wall-clock-hour rate, and posts a recurring expense transaction to
    accounting-engine.

### 3. Implementation plan

No new microservice — extends `sim-clock` (new endpoint) and `orchestrator` (new scheduled
job + audit of existing cadence logic).

1. **`sim-clock/main.py`**: add `POST /speed {"speed_multiplier": float}` — validate range
   0.1-10.0, update the `sim_clock.speed_multiplier` DB column, return the new value
   immediately. If the ticker loop doesn't already re-read this value per tick, fix that too.
   Add `GET /speed/presets` returning the labeled preset list (0.1/0.25/0.5/1/2/5/10x).
2. **Cadence audit across orchestrator/meeting-simulator/human-bridge/external-world**:
   confirm every "should I generate routine content now" check compares against `sim_time`
   deltas rather than wall-clock tick counts. Convert tick-count-based checks to
   sim-time-window checks.
3. **Business-hours gating**: a small `business_hours_weight(sim_time) -> float` function,
   duplicated per service (no shared library currently exists across these Python services;
   this matches existing repo convention).
4. **LLM-burn recurring expense**: new orchestrator scheduled job that queries LiteLLM's usage
   data (same source as Phase 31's panel), computes actual $ spent since last posting, calls
   accounting-engine's existing expense-posting endpoint with a "LLM API costs" line item.
5. **`docker-compose.yml` wiring:** no new services. Decide whether `SPEED_MULTIPLIER` env var
   becomes a first-boot-only default or is removed entirely in favor of always-DB-backed state.

### 4. Dependencies/ordering

- Depends on Phase 12 (sim clock), Phase 18 (business-hours gating partial), Phase 15
  (Akaunting expense posting), and Phase 31 (LLM cost data) — all satisfied once Phase 31
  ships.
- Touches the same orchestrator tick loop that Phase 27's reachability wrapper touches —
  when picked back up, rebase/re-read orchestrator's current state first to avoid conflicts
  with Phase 27's since-landed changes.
- Blocks Phase 33's dashboard speed-slider control.

### 5. Verification plan

- Call the new `/speed` endpoint with `2.0`; measure `sim_time` advancement over a fixed
  60-second wall-clock window; confirm it advanced ~120 simulated minutes (2x), not 60.
- With speed at e.g. 5x, measure the actual count of emails/chat messages/tickets generated
  over a fixed *sim-time* window and confirm it lands near the §19.3 calibrated targets,
  contrasted against the same test at 1x.
- Advance sim-time across a simulated Saturday; confirm generation volume drops to the 5-10%
  trickle band relative to a weekday.
- Let the LLM-burn job run for a few cycles; cross-check posted Akaunting amounts against
  LiteLLM's own usage/cost table.

### 6. Risks/open questions (unresolved — revisit when unblocked)

- **Real regression risk**: the cadence-audit step touches shared, already-verified code in
  orchestrator/meeting-simulator/human-bridge/external-world. Any refactor from
  tick-count-based to sim-time-window-based checks carries real regression risk to
  already-working behavior. Do this behind careful before/after testing against the existing
  1x baseline before testing other speeds.
- **Design choice**: whether `SPEED_MULTIPLIER` env var becomes a first-boot-only default or
  is removed entirely in favor of always-DB-backed state.
- No destructive/data-loss risk.
