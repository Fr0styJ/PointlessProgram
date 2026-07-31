# external-world/

**Populated by:** Phase 21 (BetaCorp rival) + Phase 22 (customers & revenue)

This directory will contain the External-World Generator service: simulates the rival company
BetaCorp and the customer base (spec §11).

**BetaCorp (§11.1):**
- Occasional industry/rival flavor news (wiki article or #general mention) — cheap tier, no
  thread/action-item overhead.
- `market_benchmark` table (role/department → benchmark pay) drives job-offer risk.
- Deterministic probability check (weighted by pay gap, NEVER by LLM judgment) selects
  employee to receive a BetaCorp recruiter email.
- Near-miss surfaces as a `pending_reactions`-style flag to the Principal.
- Unaddressed large gap resolves deterministically to `resigned`.
- Mail injection: externally-looking sender fields injected locally within closed network.
  Server must NOT relay outbound to real external domains (SPEC_CLARIFICATIONS #5).

**Customers (§11.2):**
- `customers` table: company_name, contact_name, contact_email, relationship_status,
  assigned_sales_rep_id, assigned_support_rep_id.
- Prospects email Sales; active customers file Zammad tickets against Support.
- Revenue posting: deal amount read from field set at thread-open time — NEVER invented at
  close time. Posts real Akaunting revenue transaction.
- At-risk customers churn deterministically if support tickets sit open past configured threshold.

**`narrative_events.origin` for this service:** `external` (SPEC_CLARIFICATIONS #9)

**Dependencies:** Phases 4 (mail), 6 (Zammad), 14 (roster), 15 (accounting engine for revenue posting), 18 (pending_reactions pattern).
