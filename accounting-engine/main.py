"""
accounting-engine/main.py — FakeCo "Real Appliances"
Phase 15: Deterministic accounting engine.

Spec §10.1–10.4, SPEC_CLARIFICATIONS #1, #2, #3:
- All financial math is deterministic code — NEVER the LLM.
- Expense approval workflow with role-based routing (§10.2)
- Payroll runs: one aggregate Akaunting transaction per cycle (SPEC_CLARIFICATIONS #2)
- Revenue posting: posts real Akaunting revenue when deals close (§11.2)
- Books Auditor: reconciles approvals/payroll, posts "audit correction" transactions (§10.4)
- Idempotency keys on all money-posting operations (§23)

SPEC_CLARIFICATIONS #3: "Department lead" = is_lead=TRUE on employees table.
  If dept has no lead, IC requests escalate straight to Principal.
  Multiple leads: longest-tenured (earliest hired_at) is the effective lead.

SPEC_CLARIFICATIONS #4: Pay cuts are MANUAL ONLY from dashboard Payroll tab.
  This service stubs the pay-cut path (queues with "requires pay_negotiation meeting")
  until Phase 24 wires the meeting outcome back.

Exposed as a FastAPI service + CLI for Phase 33 dashboard wiring.
"""
import asyncio
import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Annotated
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","service":"accounting-engine","msg":"%(message)s"}'
)
log = logging.getLogger("accounting_engine")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql://{os.environ.get('POSTGRES_USER','fakeco')}:"
    f"{os.environ.get('POSTGRES_PASSWORD','fakeco')}@"
    f"{os.environ.get('POSTGRES_HOST','postgres')}:"
    f"{os.environ.get('POSTGRES_PORT','5432')}/"
    f"{os.environ.get('POSTGRES_DB','fakeco')}"
)
AKAUNTING_URL = os.environ.get("AKAUNTING_URL", "http://akaunting")
AKAUNTING_EMAIL = os.environ.get("AKAUNTING_ADMIN_EMAIL", "")
AKAUNTING_PASSWORD = os.environ.get("AKAUNTING_ADMIN_PASSWORD", "")
AKAUNTING_COMPANY_ID = int(os.environ.get("AKAUNTING_COMPANY_ID", "1"))
ZAMMAD_URL = os.environ.get("ZAMMAD_URL", "http://zammad-nginx:8080")
ZAMMAD_ADMIN_TOKEN = os.environ.get("ZAMMAD_ADMIN_TOKEN", "")

# Approval policy thresholds (spec §10.2 defaults — all tunable via env)
IC_AUTO_APPROVE_LIMIT = Decimal(os.environ.get("IC_AUTO_APPROVE_LIMIT", "25.00"))
LEAD_AUTO_APPROVE_LIMIT = Decimal(os.environ.get("LEAD_AUTO_APPROVE_LIMIT", "500.00"))

# Akaunting account IDs (set at first-boot via Akaunting UI; stored here as env vars)
AKAUNTING_PAYROLL_ACCOUNT_ID = int(os.environ.get("AKAUNTING_PAYROLL_ACCOUNT_ID", "0"))
AKAUNTING_EXPENSE_ACCOUNT_ID = int(os.environ.get("AKAUNTING_EXPENSE_ACCOUNT_ID", "0"))
AKAUNTING_REVENUE_ACCOUNT_ID = int(os.environ.get("AKAUNTING_REVENUE_ACCOUNT_ID", "0"))
AKAUNTING_LLM_EXPENSE_ACCOUNT_ID = int(os.environ.get("AKAUNTING_LLM_EXPENSE_ACCOUNT_ID", "0"))
# Akaunting *category* IDs — distinct from the account (bank) IDs above. `category_id` is a
# separate required field on every transaction (income/expense classification); omitting it
# entirely was a bug (every post 422'd with "The category id field is required").
AKAUNTING_PAYROLL_CATEGORY_ID = int(os.environ.get("AKAUNTING_PAYROLL_CATEGORY_ID", "0"))
AKAUNTING_EXPENSE_CATEGORY_ID = int(os.environ.get("AKAUNTING_EXPENSE_CATEGORY_ID", "0"))
AKAUNTING_REVENUE_CATEGORY_ID = int(os.environ.get("AKAUNTING_REVENUE_CATEGORY_ID", "0"))


# ---------------------------------------------------------------------------
# Akaunting API client
# ---------------------------------------------------------------------------
class AkauntingClient:
    """
    Wraps the Akaunting REST API (v1/v2).
    All financial math happens HERE in Python, not in the LLM.
    """
    def __init__(self, base_url: str, email: str, password: str, company_id: int):
        self.base = base_url.rstrip("/") + "/api"
        self.company_id = company_id
        self.auth = (email, password)
        # Laravel's TrustHosts middleware rejects the bare service DNS name ("akaunting") —
        # every request needs a Host header matching Akaunting's configured APP_URL
        # (accounting.fakecorp.internal), even though we connect directly to the container,
        # bypassing Traefik. Found live: every real call from this client was silently 500ing
        # with "Untrusted Host" outside of manual tests that happened to pass an explicit
        # Host header via curl -H — this was never actually exercised as this client sends it.
        self._client = httpx.AsyncClient(timeout=30.0, headers={"Host": "accounting.fakecorp.internal"})

    async def close(self):
        await self._client.aclose()

    async def post_transaction(
        self,
        account_id: int,
        amount: Decimal,
        description: str,
        transaction_type: str = "expense",
        contact_id: Optional[int] = None,
        category_id: Optional[int] = None,
        reference: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """Post a transaction to Akaunting. Returns the created transaction dict."""
        # `number` and `payment_method` are both required by Akaunting's transaction
        # validation (neither was being sent before, so every post 422'd) — `number` needs to
        # be unique per transaction, so derive it from the idempotency key when the caller has
        # one (every financial mutation in this service is meant to be idempotency-keyed per
        # spec §23), falling back to a timestamp otherwise. `payment_method` is fixed to the
        # seeded offline "Cash" method since this sim only ever uses one bank account.
        payload = {
            "company_id": self.company_id,
            "type": transaction_type,  # "income" or "expense"
            "account_id": account_id,
            "amount": float(amount),
            "currency_code": "USD",
            "currency_rate": 1,
            "paid_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "description": description,
            "payment_method": "offline-payments.cash.1",
            "number": idempotency_key or f"TXN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        }
        if contact_id:
            payload["contact_id"] = contact_id
        if category_id:
            payload["category_id"] = category_id
        if reference:
            payload["reference"] = reference

        r = await self._client.post(
            f"{self.base}/transactions",
            json=payload,
            auth=self.auth,
        )
        r.raise_for_status()
        return r.json().get("data", r.json())

    async def get_transactions(self, search: str = "") -> list:
        r = await self._client.get(
            f"{self.base}/transactions",
            params={"company_id": self.company_id, "search": search},
            auth=self.auth,
        )
        r.raise_for_status()
        return r.json().get("data", [])


# ---------------------------------------------------------------------------
# Zammad client (for expense_request tickets)
# ---------------------------------------------------------------------------
class ZammadClient:
    def __init__(self, base_url: str, admin_token: str):
        self.base = base_url.rstrip("/") + "/api/v1"
        self.headers = {"Authorization": f"Token token={admin_token}"}
        self._client = httpx.AsyncClient(headers=self.headers, timeout=30.0)

    async def close(self):
        await self._client.aclose()

    async def create_ticket(self, title: str, body: str, customer_id: int, group: str = "Users") -> dict:
        r = await self._client.post(f"{self.base}/tickets", json={
            "title": title,
            "group": group,
            "customer_id": customer_id,
            "article": {
                "subject": title,
                "body": body,
                "type": "note",
                "internal": False,
            },
        })
        r.raise_for_status()
        return r.json()

    async def add_note(self, ticket_id: int, note: str) -> None:
        await self._client.post(f"{self.base}/ticket_articles", json={
            "ticket_id": ticket_id,
            "subject": "Approval decision",
            "body": note,
            "type": "note",
            "internal": True,
        })


# ---------------------------------------------------------------------------
# Database pool
# ---------------------------------------------------------------------------
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


# ---------------------------------------------------------------------------
# Approval policy engine (§10.2)
# SPEC_CLARIFICATIONS #3: is_lead bool derived from role_tier; longest-tenured = lead.
# ---------------------------------------------------------------------------
async def resolve_approver(
    conn: asyncpg.Connection,
    requester_id: int,
    amount: Decimal,
) -> tuple[Optional[int], bool]:
    """
    Determine who should approve an expense request.
    Returns (approver_employee_id, approver_is_principal).
    Spec §10.2 approval policy table.
    """
    requester = await conn.fetchrow(
        "SELECT id, department, role_tier, hired_at FROM employees WHERE id = $1 AND status = 'active'",
        requester_id
    )
    if requester is None:
        raise ValueError(f"Requester {requester_id} not found or not active")

    role_tier = requester["role_tier"]
    department = requester["department"]

    # Individual contributor: auto-approve ≤ IC_AUTO_APPROVE_LIMIT, else escalate to lead
    if role_tier == "ic":
        if amount <= IC_AUTO_APPROVE_LIMIT:
            return (requester_id, False)  # auto-approved by requester's own limit
        # Find the department lead (longest-tenured = earliest hired_at)
        lead = await conn.fetchrow("""
            SELECT id FROM employees
            WHERE department = $1 AND role_tier = 'lead' AND status = 'active'
            ORDER BY hired_at ASC LIMIT 1
        """, department)
        if lead is None:
            # No lead in department → escalate straight to Principal (SPEC_CLARIFICATIONS #3)
            return (None, True)
        if amount <= LEAD_AUTO_APPROVE_LIMIT:
            return (lead["id"], False)
        else:
            return (None, True)  # escalate to Principal

    # Lead: auto-approve ≤ LEAD_AUTO_APPROVE_LIMIT, else escalate to Principal
    elif role_tier == "lead":
        if amount <= LEAD_AUTO_APPROVE_LIMIT:
            return (requester_id, False)  # auto-approved by lead's own limit
        return (None, True)  # escalate to Principal

    # Principal (if an employee row exists for them): unlimited
    else:
        return (None, True)


async def submit_expense_request(
    pool: asyncpg.Pool,
    akaunting: AkauntingClient,
    zammad: ZammadClient,
    requester_id: int,
    amount: Decimal,
    description: str,
    idempotency_key: Optional[str] = None,
) -> dict:
    """
    Full expense approval workflow:
    1. Resolve approver deterministically.
    2. If auto-approved (amount ≤ requester's tier limit), post to Akaunting immediately.
    3. If needs approval, create Zammad ticket + pending_approvals row. Do NOT post yet.
    Returns dict with {status, approval_id, akaunting_transaction_id (if auto-approved)}.
    """
    if not idempotency_key:
        idempotency_key = f"expense:{requester_id}:{description[:50]}:{float(amount)}"
        idempotency_key = hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]

    async with pool.acquire() as conn:
        # Idempotency check — reject duplicate submissions
        existing = await conn.fetchrow(
            "SELECT id, status FROM pending_approvals WHERE idempotency_key = $1",
            idempotency_key
        )
        if existing:
            log.info("Expense: idempotency hit for key %s (existing id=%d)", idempotency_key, existing["id"])
            return {"status": existing["status"], "approval_id": existing["id"], "duplicate": True}

        approver_id, approver_is_principal = await resolve_approver(conn, requester_id, amount)
        is_auto_approved = (approver_id == requester_id and not approver_is_principal)

        # Create the pending_approvals row (even for auto-approved, for audit trail)
        approval_id = await conn.fetchval("""
            INSERT INTO pending_approvals
                (expense_request_ref, requester_employee_id, approver_employee_id,
                 approver_is_principal, amount, status, idempotency_key)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
        """,
            f"pending_{idempotency_key[:16]}",
            requester_id,
            approver_id,
            approver_is_principal,
            amount,
            "approved" if is_auto_approved else "pending",
            idempotency_key,
        )

        akaunting_tx_id = None
        if is_auto_approved:
            # Post to Akaunting immediately
            try:
                tx = await akaunting.post_transaction(
                    account_id=AKAUNTING_EXPENSE_ACCOUNT_ID,
                    category_id=AKAUNTING_EXPENSE_CATEGORY_ID,
                    amount=amount,
                    description=f"[AUTO-APPROVED] {description}",
                    transaction_type="expense",
                    reference=f"approval:{approval_id}",
                )
                akaunting_tx_id = str(tx.get("id", ""))
                await conn.execute(
                    "UPDATE pending_approvals SET expense_request_ref = $1 WHERE id = $2",
                    f"akaunting:{akaunting_tx_id}", approval_id
                )
                await audit_log(conn, "accounting-engine", "expense_auto_approved",
                    {"approval_id": approval_id, "amount": float(amount), "akaunting_tx": akaunting_tx_id})
                log.info("Expense auto-approved: %s $%.2f → Akaunting tx %s", description, amount, akaunting_tx_id)
            except Exception as exc:
                log.error("Failed to post to Akaunting: %s", exc)
                # Don't raise — approval row exists, retry can post later
        else:
            # Create Zammad ticket for manual approval
            if approver_is_principal:
                assignee_note = "Assigned to Principal (over-threshold)"
            else:
                approver_row = await conn.fetchrow("SELECT name FROM employees WHERE id = $1", approver_id)
                assignee_note = f"Assigned to {approver_row['name'] if approver_row else 'department lead'}"

            ticket_body = (
                f"Expense Request — ${amount:.2f}\n"
                f"Description: {description}\n"
                f"Requester ID: {requester_id}\n"
                f"Approval ID: {approval_id}\n"
                f"{assignee_note}\n"
            )
            try:
                ticket = await zammad.create_ticket(
                    title=f"Expense Request: {description[:60]} (${amount:.2f})",
                    body=ticket_body,
                    customer_id=1,  # system customer; adjust in first-boot
                )
                ticket_ref = f"zammad:{ticket['id']}"
                await conn.execute(
                    "UPDATE pending_approvals SET expense_request_ref = $1 WHERE id = $2",
                    ticket_ref, approval_id
                )
                await audit_log(conn, "accounting-engine", "expense_queued_for_approval",
                    {"approval_id": approval_id, "amount": float(amount), "zammad_ticket": ticket["id"]})
                log.info("Expense queued for approval: %s $%.2f → Zammad ticket %d", description, amount, ticket["id"])
            except Exception as exc:
                log.error("Failed to create Zammad ticket: %s", exc)

        return {
            "status": "approved" if is_auto_approved else "pending",
            "approval_id": approval_id,
            "akaunting_transaction_id": akaunting_tx_id,
            "auto_approved": is_auto_approved,
        }


async def approve_expense(
    pool: asyncpg.Pool,
    akaunting: AkauntingClient,
    approval_id: int,
    approved_by: str,  # 'principal' or employee name
    note: str = "",
) -> dict:
    """
    Final approval: post to Akaunting and mark approved.
    Only called for pending approvals (auto-approved ones already posted).
    """
    async with pool.acquire() as conn:
        approval = await conn.fetchrow(
            "SELECT * FROM pending_approvals WHERE id = $1 AND status = 'pending'",
            approval_id
        )
        if not approval:
            raise ValueError(f"Pending approval {approval_id} not found")

        async with conn.transaction():
            # Post to Akaunting
            tx = await akaunting.post_transaction(
                account_id=AKAUNTING_EXPENSE_ACCOUNT_ID,
                category_id=AKAUNTING_EXPENSE_CATEGORY_ID,
                amount=approval["amount"],
                description=f"[APPROVED by {approved_by}] {approval['expense_request_ref']}",
                transaction_type="expense",
                reference=f"approval:{approval_id}",
            )
            akaunting_tx_id = str(tx.get("id", ""))

            await conn.execute("""
                UPDATE pending_approvals
                SET status = 'approved', expense_request_ref = $1, updated_at = NOW()
                WHERE id = $2
            """, f"akaunting:{akaunting_tx_id}", approval_id)

            await audit_log(conn, approved_by, "expense_approved",
                {"approval_id": approval_id, "amount": float(approval["amount"]), "akaunting_tx": akaunting_tx_id})

    return {"status": "approved", "akaunting_transaction_id": akaunting_tx_id}


# ---------------------------------------------------------------------------
# Payroll (§10.3) — SPEC_CLARIFICATIONS #2: one aggregate transaction per cycle
# ---------------------------------------------------------------------------
async def run_payroll(
    pool: asyncpg.Pool,
    akaunting: AkauntingClient,
    idempotency_key: Optional[str] = None,
) -> dict:
    """
    Deterministic payroll run:
    1. Sum pay for all active employees.
    2. Post ONE aggregate 'Payroll Expense' transaction to Akaunting.
    3. Per-employee detail stays in Postgres referencing that transaction ID.
    4. Vacant/terminated draw no pay.

    SPEC_CLARIFICATIONS #2: employees do NOT get individual vendor/contact records in Akaunting.
    """
    if not idempotency_key:
        # Key is cycle-based: date + hour (biweekly would use week number)
        cycle_tag = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
        idempotency_key = f"payroll:{cycle_tag}"

    async with pool.acquire() as conn:
        # Idempotency: check if this exact cycle already posted
        existing = await conn.fetchrow(
            "SELECT id FROM system_audit_log WHERE action = 'payroll_posted' AND detail->>'idempotency_key' = $1",
            idempotency_key
        )
        if existing:
            log.info("Payroll: already posted for key %s", idempotency_key)
            return {"status": "already_posted", "idempotency_key": idempotency_key}

        # Fetch all active employees (vacant/terminated draw nothing)
        employees = await conn.fetch("""
            SELECT id, name, pay_rate FROM employees
            WHERE status = 'active'
        """)
        if not employees:
            log.info("Payroll: no active employees, nothing to post")
            return {"status": "no_active_employees"}

        # Deterministic sum — no LLM, no approximation
        total_pay = sum(Decimal(str(emp["pay_rate"])) for emp in employees)
        employee_count = len(employees)

        log.info("Payroll: %d active employees, total = $%.2f", employee_count, total_pay)

        # Post ONE aggregate transaction to Akaunting
        try:
            tx = await akaunting.post_transaction(
                account_id=AKAUNTING_PAYROLL_ACCOUNT_ID,
                category_id=AKAUNTING_PAYROLL_CATEGORY_ID,
                amount=total_pay,
                description=f"Payroll: {employee_count} active employees",
                transaction_type="expense",
                reference=idempotency_key,
            )
            akaunting_tx_id = str(tx.get("id", ""))
        except Exception as exc:
            log.error("Payroll: Akaunting post failed: %s", exc)
            raise

        # Record per-employee payroll detail in Postgres (not in Akaunting)
        # Using system_audit_log as the durable record (it survives all purges)
        await audit_log(conn, "accounting-engine", "payroll_posted", {
            "idempotency_key": idempotency_key,
            "akaunting_transaction_id": akaunting_tx_id,
            "total_pay": float(total_pay),
            "employee_count": employee_count,
            "employee_detail": [{"id": e["id"], "name": e["name"], "pay": float(e["pay_rate"])} for e in employees],
        })

        log.info("Payroll posted: $%.2f → Akaunting tx %s", total_pay, akaunting_tx_id)
        return {
            "status": "posted",
            "total_pay": float(total_pay),
            "employee_count": employee_count,
            "akaunting_transaction_id": akaunting_tx_id,
        }


# ---------------------------------------------------------------------------
# Revenue posting (§11.2) — called by external-world service when deals close
# ---------------------------------------------------------------------------
async def post_revenue(
    pool: asyncpg.Pool,
    akaunting: AkauntingClient,
    customer_id: int,  # customers.id in Postgres
    deal_amount: Decimal,
    description: str,
    idempotency_key: Optional[str] = None,
) -> dict:
    """
    Post a real revenue transaction to Akaunting when a deal closes.
    Deal amount read from customers.deal_size (set at thread-open time).
    NEVER invented at close time — enforced here by reading from DB.
    """
    if not idempotency_key:
        idempotency_key = f"revenue:customer:{customer_id}:{float(deal_amount)}"

    async with pool.acquire() as conn:
        # Verify deal_amount matches what was set at thread-open time
        customer = await conn.fetchrow(
            "SELECT company_name, deal_size FROM customers WHERE id = $1",
            customer_id
        )
        if customer is None:
            raise ValueError(f"Customer {customer_id} not found")
        db_deal_size = Decimal(str(customer["deal_size"]))
        if abs(db_deal_size - deal_amount) > Decimal("0.01"):
            raise ValueError(
                f"Revenue amount mismatch: passed {deal_amount}, DB has {db_deal_size}. "
                "Deal amount must come from the DB field set at thread-open time."
            )

        # Check idempotency
        existing = await conn.fetchrow(
            "SELECT id FROM system_audit_log WHERE action = 'revenue_posted' AND detail->>'idempotency_key' = $1",
            idempotency_key
        )
        if existing:
            log.info("Revenue: already posted for key %s", idempotency_key)
            return {"status": "already_posted"}

        tx = await akaunting.post_transaction(
            account_id=AKAUNTING_REVENUE_ACCOUNT_ID,
            category_id=AKAUNTING_REVENUE_CATEGORY_ID,
            amount=deal_amount,
            description=f"[REVENUE] {description} — {customer['company_name']}",
            transaction_type="income",
            reference=idempotency_key,
        )
        akaunting_tx_id = str(tx.get("id", ""))

        # Update customer record with Akaunting transaction ID
        await conn.execute(
            "UPDATE customers SET akaunting_transaction_id = $1, relationship_status = 'active' WHERE id = $2",
            akaunting_tx_id, customer_id
        )

        await audit_log(conn, "accounting-engine", "revenue_posted", {
            "idempotency_key": idempotency_key,
            "customer_id": customer_id,
            "company_name": customer["company_name"],
            "amount": float(deal_amount),
            "akaunting_transaction_id": akaunting_tx_id,
        })

        log.info("Revenue posted: $%.2f from %s → Akaunting tx %s", deal_amount, customer["company_name"], akaunting_tx_id)
        return {"status": "posted", "akaunting_transaction_id": akaunting_tx_id}


# ---------------------------------------------------------------------------
# Pay cut stub (§10.3 + SPEC_CLARIFICATIONS #4)
# Full path wired in Phase 24 (meeting simulator extension).
# ---------------------------------------------------------------------------
async def propose_pay_cut(
    pool: asyncpg.Pool,
    employee_id: int,
    proposed_pay: Decimal,
    initiated_by: str = "principal",
) -> dict:
    """
    Pay cuts are MANUAL ONLY (SPEC_CLARIFICATIONS #4).
    This function opens a pay_negotiation meeting instead of applying directly.
    Phase 15 STUB: logs the request and queues a pending_reaction for Phase 24 to wire.
    """
    async with pool.acquire() as conn:
        emp = await conn.fetchrow("SELECT name, pay_rate FROM employees WHERE id = $1", employee_id)
        if not emp:
            raise ValueError(f"Employee {employee_id} not found")
        current_pay = Decimal(str(emp["pay_rate"]))

        log.info(
            "[STUB] Pay cut proposed for employee %d (%s): $%.2f → $%.2f. "
            "Queuing pay_negotiation meeting (Phase 24 will wire this).",
            employee_id, emp["name"], current_pay, proposed_pay
        )
        # In Phase 24, this creates a pay_negotiation meeting row.
        # For now, record in system_audit_log as a pending action.
        await audit_log(conn, initiated_by, "pay_cut_proposed_stub", {
            "employee_id": employee_id,
            "employee_name": emp["name"],
            "current_pay": float(current_pay),
            "proposed_pay": float(proposed_pay),
            "note": "STUB: pay_negotiation meeting creation wired in Phase 24",
        })
        return {
            "status": "queued_for_negotiation",
            "message": "Pay cut requires a pay_negotiation meeting (spec §10.3). Meeting creation pending Phase 24.",
            "employee_id": employee_id,
            "current_pay": float(current_pay),
            "proposed_pay": float(proposed_pay),
        }


# ---------------------------------------------------------------------------
# Books Auditor (§10.4) — reconciliation and correction
# ---------------------------------------------------------------------------
async def run_books_audit(
    pool: asyncpg.Pool,
    akaunting: AkauntingClient,
) -> dict:
    """
    Deterministic books audit:
    1. Check all 'approved' pending_approvals have corresponding Akaunting transactions.
    2. Check all payroll_posted audit log entries have Akaunting references.
    3. Post clearly-tagged "audit correction" transactions for any discrepancies.
    4. Write a system_audit_log entry for every correction.
    Returns a report dict.
    """
    corrections = []
    log.info("Books Auditor: starting reconciliation run")

    async with pool.acquire() as conn:
        # Check approved expenses
        approved_expenses = await conn.fetch("""
            SELECT id, amount, expense_request_ref, idempotency_key
            FROM pending_approvals
            WHERE status = 'approved' AND expense_request_ref NOT LIKE 'akaunting:%'
        """)

        for expense in approved_expenses:
            log.warning("Auditor: approved expense %d has no Akaunting reference — posting correction", expense["id"])
            try:
                tx = await akaunting.post_transaction(
                    account_id=AKAUNTING_EXPENSE_ACCOUNT_ID,
                    category_id=AKAUNTING_EXPENSE_CATEGORY_ID,
                    amount=Decimal(str(expense["amount"])),
                    description=f"[AUDIT CORRECTION] Missed expense post — approval {expense['id']}",
                    transaction_type="expense",
                    reference=f"audit-correction:approval:{expense['id']}",
                )
                akaunting_tx_id = str(tx.get("id", ""))
                await conn.execute(
                    "UPDATE pending_approvals SET expense_request_ref = $1 WHERE id = $2",
                    f"akaunting:{akaunting_tx_id}", expense["id"]
                )
                correction = {
                    "type": "expense_correction",
                    "approval_id": expense["id"],
                    "amount": float(expense["amount"]),
                    "akaunting_tx": akaunting_tx_id,
                }
                corrections.append(correction)
                await audit_log(conn, "books-auditor", "audit_correction", correction)
            except Exception as exc:
                log.error("Auditor: correction failed for approval %d: %s", expense["id"], exc)

        # Check payroll — verify recent payroll audit log entries reference valid Akaunting IDs
        # (In production: cross-reference Akaunting /transactions endpoint)
        # Phase 15: basic check that payroll_posted entries have an akaunting_transaction_id
        payroll_logs = await conn.fetch("""
            SELECT id, detail FROM system_audit_log
            WHERE action = 'payroll_posted'
            ORDER BY created_at DESC LIMIT 10
        """)
        for pl in payroll_logs:
            import json
            detail = json.loads(pl["detail"]) if isinstance(pl["detail"], str) else dict(pl["detail"])
            if not detail.get("akaunting_transaction_id"):
                log.warning("Auditor: payroll audit log %d has no Akaunting transaction ID", pl["id"])
                corrections.append({"type": "payroll_no_akaunting_ref", "audit_log_id": pl["id"]})

        report = {
            "status": "complete",
            "corrections_made": len(corrections),
            "corrections": corrections,
        }
        await audit_log(conn, "books-auditor", "audit_run_complete", report)
        log.info("Books Auditor: complete — %d corrections made", len(corrections))
        return report


# ---------------------------------------------------------------------------
# System audit log helper (used throughout)
# ---------------------------------------------------------------------------
async def audit_log(conn: asyncpg.Connection, actor: str, action: str, detail: dict) -> None:
    """Write an immutable entry to system_audit_log. Uses wall-clock time."""
    import json
    await conn.execute(
        "INSERT INTO system_audit_log (actor, action, detail) VALUES ($1, $2, $3)",
        actor, action, json.dumps(detail)
    )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    log.info("accounting-engine: ready")
    yield
    await _pool.close()


app = FastAPI(
    title="FakeCo Accounting Engine",
    description="Deterministic accounting engine — all financial math in code, never LLM.",
    version="1.0.0",
    lifespan=lifespan,
)

PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]


def get_akaunting() -> AkauntingClient:
    return AkauntingClient(AKAUNTING_URL, AKAUNTING_EMAIL, AKAUNTING_PASSWORD, AKAUNTING_COMPANY_ID)


def get_zammad() -> ZammadClient:
    return ZammadClient(ZAMMAD_URL, ZAMMAD_ADMIN_TOKEN)


# --- API models ---
class ExpenseRequest(BaseModel):
    requester_employee_id: int
    amount: Decimal = Field(..., gt=0)
    description: str
    idempotency_key: Optional[str] = None


class PayrollRequest(BaseModel):
    idempotency_key: Optional[str] = None


class RevenueRequest(BaseModel):
    customer_id: int
    deal_amount: Decimal = Field(..., gt=0)
    description: str
    idempotency_key: Optional[str] = None


class PayCutRequest(BaseModel):
    employee_id: int
    proposed_pay: Decimal = Field(..., gt=0)
    initiated_by: str = "principal"


class ApproveExpenseRequest(BaseModel):
    approval_id: int
    approved_by: str
    note: str = ""


# --- API endpoints ---
@app.get("/health")
async def health():
    return {"status": "ok", "service": "accounting-engine"}


@app.post("/expense/submit")
async def submit_expense(req: ExpenseRequest, pool: PoolDep):
    akaunting = get_akaunting()
    zammad = get_zammad()
    try:
        result = await submit_expense_request(
            pool, akaunting, zammad,
            req.requester_employee_id, req.amount,
            req.description, req.idempotency_key
        )
        return result
    finally:
        await akaunting.close()
        await zammad.close()


@app.post("/expense/approve")
async def approve_expense_endpoint(req: ApproveExpenseRequest, pool: PoolDep):
    akaunting = get_akaunting()
    try:
        return await approve_expense(pool, akaunting, req.approval_id, req.approved_by, req.note)
    finally:
        await akaunting.close()


@app.post("/payroll/run")
async def run_payroll_endpoint(req: PayrollRequest, pool: PoolDep):
    akaunting = get_akaunting()
    try:
        return await run_payroll(pool, akaunting, req.idempotency_key)
    finally:
        await akaunting.close()


@app.post("/revenue/post")
async def post_revenue_endpoint(req: RevenueRequest, pool: PoolDep):
    akaunting = get_akaunting()
    try:
        return await post_revenue(pool, akaunting, req.customer_id, req.deal_amount, req.description, req.idempotency_key)
    finally:
        await akaunting.close()


@app.post("/payroll/propose-cut")
async def propose_pay_cut_endpoint(req: PayCutRequest, pool: PoolDep):
    return await propose_pay_cut(pool, req.employee_id, req.proposed_pay, req.initiated_by)


@app.post("/audit/run")
async def run_audit_endpoint(pool: PoolDep):
    akaunting = get_akaunting()
    try:
        return await run_books_audit(pool, akaunting)
    finally:
        await akaunting.close()


@app.post("/payroll/raise")
async def apply_raise(employee_id: int, new_pay: Decimal, reason: str, pool: PoolDep):
    """
    Raises apply immediately with no approval step (spec §10.3).
    """
    async with pool.acquire() as conn:
        emp = await conn.fetchrow("SELECT name, pay_rate FROM employees WHERE id = $1 AND status = 'active'", employee_id)
        if not emp:
            raise HTTPException(status_code=404, detail=f"Active employee {employee_id} not found")
        old_pay = emp["pay_rate"]
        if new_pay <= old_pay:
            raise HTTPException(status_code=400, detail="Raise must be to a higher pay rate. Use /payroll/propose-cut for pay cuts.")
        await conn.execute("""
            UPDATE employees
            SET pay_rate = $1, pay_last_changed_at = NOW(), pay_last_change_reason = $2
            WHERE id = $3
        """, new_pay, reason, employee_id)
        await audit_log(conn, "accounting-engine", "raise_applied", {
            "employee_id": employee_id, "old_pay": float(old_pay),
            "new_pay": float(new_pay), "reason": reason,
        })
        log.info("Raise applied: employee %d %s $%.2f → $%.2f", employee_id, emp["name"], old_pay, new_pay)
        return {"status": "applied", "old_pay": float(old_pay), "new_pay": float(new_pay)}
