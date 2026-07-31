# orchestrator/

**Populated by:** Phase 18 — Orchestrator continuity loop

This directory will contain the worker-bot orchestrator service: the custom component
that drives the priority-ordered continuity loop (spec §4.3), reads the employee roster,
sim clock, PTO calendar, and relationship graph every cycle, implements reachability checks
and the `pending_actions` idempotent retry queue, and hosts/coordinates the scheduled
deterministic jobs listed in spec §24.

This is one of several genuinely separate, independently-deployable custom services (see
SPEC_CLARIFICATIONS.md item 13). It is NOT a monolith absorbing all other managers.

**Dependencies before this phase:** Phases 12 (sim clock), 15 (approvals), 16 (action items), 17 (reactions).
