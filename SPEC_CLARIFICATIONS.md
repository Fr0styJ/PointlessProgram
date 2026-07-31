# SPEC_CLARIFICATIONS.md

Read this alongside `fakeco-real-appliances-BUILD-PROMPT.md` and `PHASES.md`. These are
authoritative resolutions to the 13 items in PHASES.md's "Open questions / spec gaps" section
— treat them as amendments to the build spec, not open items to reconsider. Numbering matches
PHASES.md exactly.

1. **Polymorphic approver field.** `pending_approvals` gets two nullable columns:
   `approver_employee_id` and `approver_is_principal` (boolean), instead of a single tagged
   column. Simpler to query, no encoding scheme needed.

2. **No Akaunting-side employee identity.** Payroll posts as **one aggregate transaction per
   cycle** in Akaunting, categorized "Payroll Expense." Per-employee detail (who got paid
   what) lives only in Postgres, referencing that single Akaunting transaction ID. Employees
   do not get individual vendor/contact records inside Akaunting.

3. **"Department lead" isn't a defined role.** Add an `is_lead` boolean (or `role_tier` enum:
   `ic` / `lead`) to the `employees` table. Default: exactly one lead per department, seeded
   at hire time. If a department currently has no lead (e.g. fired), individual-contributor
   requests from that department escalate straight to the Principal. If more than one
   candidate ever exists, the longest-tenured one is the lead — deterministic tiebreak, no
   LLM judgment involved.

4. **What triggers a pay cut.** Manual only — a deliberate action from the dashboard's
   Payroll tab. BetaCorp benchmark gaps (11.1) and performance data (12.2) may justify a raise
   or flag someone for a performance-review conversation, but must never automatically propose
   a cut. Cuts stay something a human decides to initiate.

5. **Mail relay lockdown vs. externally-looking senders.** docker-mailserver accepts inbound
   delivery only for the `@fakecorp.internal` domain. Externally-styled sender addresses
   (BetaCorp, customers) are locally-injected display artifacts on mail that's delivered
   entirely within the closed network — the server must reject any actual attempt to relay
   outbound to a real external domain. This is "closed relay, permissive local sender-spoofing
   for simulation flavor," not an open relay, and should be verified explicitly (Phase 4, with
   a regression check around Phase 21 once the external-world generator exists).

6. **Performance-review cold start.** Skip the review entirely — no raise, no flag — for any
   employee with less than one full review cycle of tenure, or in a department with fewer than
   2 members. They're picked up automatically at the next cycle once there's enough peer data.

7. **Requester for a crisis-generated expense.** Use the Principal's own employee/account ID
   as `requester_employee_id`. You're the one who triggered the crisis event, and the request
   is already headed to your attention regardless of the approval-policy table.

8. **Snapshot/audit-log interaction.** `system_audit_log` is excluded from snapshot capture
   and restore entirely, in both directions. Restoring a snapshot never rolls the audit log
   backward or forward — it stays a continuous, honest record of everything that happened to
   the running system, independent of whichever snapshot is currently loaded. This is what
   makes "survives every purge, including the full purge" (14.3) actually true.

9. **`narrative_events.origin` enum missing a value.** Add a third value, `external`, alongside
   `ai` and `human`, for BetaCorp job-offer content and customer-generated traffic (sections
   11.1/11.2) — it's LLM-generated but neither employee-bot "work" content nor
   Principal-authored, and downstream consumers (the weekly digest's selection logic, KPI
   counts) need to be able to tell it apart from both.

10. **No seed roster provided.** Intentional gap — the building agent should invent a
    placeholder roster (names, departments, roles, personalities, starting pay) and note in
    `BUILD_LOG.md` that it's a placeholder, swappable for a real roster later if specific
    people/departments are wanted.

11. **Traefik's full multi-homing footprint.** Beyond the explicit `net_mgmt` exception, Traefik
    also needs `net_clients` (its base network), `net_office`, `net_mail`, and `net_dmz` — every
    network it routes to or needs to be reached from. State this explicitly rather than
    inferring it from the routing description alone (Phase 3).

12. **Local-model fallback tier unspecified.** Left genuinely unspecified for now — it's the
    last-resort LiteLLM fallback and only matters if DeepSeek, Anthropic, and OpenAI are all
    unreachable simultaneously. Revisit and pick a specific hosted model only if that tier is
    ever actually exercised in practice; don't spend build effort on it up front.

13. **Orchestrator vs. dedicated managers.** "The orchestrator" in section 24 was written
    loosely to mean "the backend collectively." The intent is a set of genuinely separate,
    independently deployable custom services — Meeting Simulator, Human Interaction Bridge,
    Accounting Engine, Purge Manager, Snapshot Manager, External-World Generator, KPI Engine,
    Branding/Asset Manager, and Sim Clock — matching the service replacement map (section 3)
    and the one-directory-per-deliverable structure in the checklist (section 27). The
    worker-bot orchestrator is just one of these services, specifically the one running the
    continuity loop for routine employee actions. The dashboard backend should be a thin API
    gateway that routes each action to whichever specific service owns it, not a monolith that
    absorbs all of them.
