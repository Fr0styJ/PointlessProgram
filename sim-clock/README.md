# sim-clock/

**Populated by:** Phase 12 — Sim clock

This directory will contain the Sim Clock service: a lightweight ticker that advances
`sim_time` using `sim_time += wall_elapsed_since_last_tick * speed_multiplier` (spec §19.1).

**Table:** `sim_clock` — `sim_time`, `last_wall_checkpoint`, `speed_multiplier`

**API:** `set_speed` endpoint accepting a multiplier from 0.1x (Caveman) to 10x (Fast-forward).
Changes apply immediately to the next tick.

**Key rules:**
- Every time-aware decision in this system reads `sim_time`, never wall-clock directly.
- 10x is a hard cap that only compresses time, never inflates behavioral rates.
- Business-hours gating: Mon-Fri 9am-6pm simulated time = full weight; other times = 5-10%.

**Dependencies:** Phase 1 (Postgres).
