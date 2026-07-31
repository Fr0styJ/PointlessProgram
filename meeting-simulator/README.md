# meeting-simulator/

**Populated by:** Phase 16 (standup & cross-functional types) + Phase 24 (pay_negotiation, performance_review, crisis_response types)

This directory will contain the Meeting Simulator service: generates all five meeting types
(standup, cross_functional, pay_negotiation, performance_review, crisis_response) using the
LiteLLM proxy (spec §6, §20.1). Publishes minutes to Wiki.js and Mattermost — except
pay_negotiation and performance_review meetings, which are HR-private.

**Key constraints:**
- Attends only active employees not on PTO.
- Weighted by relationship data (§5) for topic relevance.
- Company direction (§8) injected into every prompt.
- Static prefix cached per token-efficiency spec (§20.1).

**Dependencies:** Phases 5 (Mattermost), 7 (Wiki.js), 10 (LiteLLM), 13 (schema), 14 (roster).
