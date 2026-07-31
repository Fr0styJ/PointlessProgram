"""
external-world/main.py — FakeCo "Real Appliances"
Phases 21 + 22: External world generators.

Phase 21 — BetaCorp rival (spec §11.1):
  - Periodic check: compare each active employee's pay to market_benchmark
  - Probabilistic job-offer email injection (real SMTP delivery to mailbox)
  - Deterministic resignation logic if gap unaddressed too long
  - Pending_reactions flag for near-misses (Principal visibility)
  - market_benchmark table managed here (seeded in migration 003)

Phase 22 — Customers & revenue (spec §11.2):
  - Generate customer prospect interactions (Zammad tickets, emails)
  - Support ticket SLA check → deterministic churn if exceeded
  - Sales thread lifecycle → revenue posting via accounting-engine
  - Customer emails use externally-styled From addresses (local injection display artifacts)
    SPEC_CLARIFICATIONS #5: server actually restricts relay; "external" senders are cosmetic

No LLM is called for the deterministic decision paths (job offer probability, churn check).
LLM is called ONCE (cheap tier) for the email body generation only.
"""
import asyncio
import json
import logging
import os
import random
import smtplib
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from email.mime.text import MIMEText
from typing import Optional

import asyncpg
import httpx
from fastapi import FastAPI, Depends
from pydantic import BaseModel, Field
from typing import Annotated
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","service":"external-world","msg":"%(message)s"}'
)
log = logging.getLogger("external_world")

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
LITELLM_URL = os.environ.get("LITELLM_URL", "http://litellm:4000")
LITELLM_API_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
MAILSERVER_HOST = os.environ.get("MAILSERVER_HOST", "mailserver")
MAILSERVER_PORT = int(os.environ.get("MAILSERVER_SMTP_PORT", "587"))
MAILSERVER_DOMAIN = os.environ.get("MAILSERVER_DOMAIN", "fakecorp.internal")
ACCOUNTING_ENGINE_URL = os.environ.get("ACCOUNTING_ENGINE_URL", "http://accounting-engine:8000")
ZAMMAD_URL = os.environ.get("ZAMMAD_URL", "http://zammad-nginx:8080")
ZAMMAD_ADMIN_TOKEN = os.environ.get("ZAMMAD_ADMIN_TOKEN", "")
SIM_CLOCK_URL = os.environ.get("SIM_CLOCK_URL", "http://sim-clock:8000")

# BetaCorp rival config
BETACORP_DOMAIN = os.environ.get("BETACORP_DOMAIN", "betacorp.com")
BETACORP_RECRUITER_NAME = os.environ.get("BETACORP_RECRUITER_NAME", "Alex Rivera")
BETACORP_RECRUITER_EMAIL = os.environ.get("BETACORP_RECRUITER_EMAIL", "alex.rivera@betacorp.com")

# Thresholds
JOB_OFFER_BASE_PROBABILITY = float(os.environ.get("JOB_OFFER_BASE_PROBABILITY", "0.3"))
# At MAX_GAP_PCT, probability = 1.0; interpolated linearly between 0 and MAX_GAP_PCT
JOB_OFFER_MAX_GAP_PCT = float(os.environ.get("JOB_OFFER_MAX_GAP_PCT", "0.25"))
RESIGNATION_GAP_THRESHOLD_PCT = float(os.environ.get("RESIGNATION_GAP_PCT", "0.20"))
RESIGNATION_GRACE_SIM_DAYS = int(os.environ.get("RESIGNATION_GRACE_SIM_DAYS", "14"))
SUPPORT_SLA_CHURN_HOURS = int(os.environ.get("SUPPORT_SLA_CHURN_HOURS", "48"))

# Mailserver bot secret (same as provisioning)
import hashlib
MAILSERVER_BOT_SECRET = os.environ.get("MAILSERVER_BOT_SECRET", "fakeco-bot-mail-secret-change-me")


def derive_mail_password(email: str) -> str:
    return hashlib.sha256(f"{MAILSERVER_BOT_SECRET}:{email}".encode()).hexdigest()[:24]


# ---------------------------------------------------------------------------
# LLM client (cheap tier — for email body generation only)
# ---------------------------------------------------------------------------
class LLMClient:
    def __init__(self, base_url: str, api_key: str):
        self.base = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self._client = httpx.AsyncClient(headers=self.headers, timeout=60.0)

    async def close(self):
        await self._client.aclose()

    async def chat(self, messages: list[dict], model: str = "cheap") -> str:
        r = await self._client.post(f"{self.base}/chat/completions", json={
            "model": model,
            "messages": messages,
            "max_tokens": 500,
            "temperature": 0.9,
        })
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Helper: deliver email via SMTP injection
# "External" sender appears in From header but is injected locally (closed relay)
# SPEC_CLARIFICATIONS #5: this is a display artifact, not real inbound from internet
# ---------------------------------------------------------------------------
async def inject_email(
    to_email: str,
    from_display_name: str,
    from_display_email: str,   # e.g. alex.rivera@betacorp.com (cosmetic only)
    subject: str,
    body: str,
    relay_email: str,          # actual authenticated sender on our mailserver
) -> None:
    """
    Injects an email into a local mailbox making it appear to come from an external address.
    The server never actually relays outbound — from_display_email is cosmetic.
    """
    relay_password = derive_mail_password(relay_email)
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"{from_display_name} <{from_display_email}>"
    msg["To"] = to_email
    msg["Reply-To"] = from_display_email
    msg["X-Sim-Origin"] = "external-world"

    def _send():
        with smtplib.SMTP(MAILSERVER_HOST, MAILSERVER_PORT) as s:
            s.ehlo()
            try:
                s.starttls()
                s.ehlo()
            except Exception:
                pass
            s.login(relay_email, relay_password)
            s.sendmail(relay_email, [to_email], msg.as_string())

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send)


async def get_sim_time(http: httpx.AsyncClient) -> datetime:
    try:
        r = await http.get(f"{SIM_CLOCK_URL}/sim_time", timeout=5.0)
        return datetime.fromisoformat(r.json()["sim_time"])
    except Exception:
        return datetime.now(timezone.utc)


async def audit_log(conn: asyncpg.Connection, actor: str, action: str, detail: dict) -> None:
    await conn.execute(
        "INSERT INTO system_audit_log (actor, action, detail) VALUES ($1, $2, $3)",
        actor, action, json.dumps(detail)
    )


# ---------------------------------------------------------------------------
# Phase 21: BetaCorp rival — job offer check
# ---------------------------------------------------------------------------
def compute_offer_probability(employee_pay: Decimal, benchmark_pay: Decimal) -> float:
    """
    Deterministic probability of receiving a BetaCorp job offer.
    0% if employee_pay >= benchmark_pay.
    Scales linearly from JOB_OFFER_BASE_PROBABILITY at 1% gap to 1.0 at JOB_OFFER_MAX_GAP_PCT gap.
    """
    if benchmark_pay <= 0:
        return 0.0
    gap_pct = float((benchmark_pay - employee_pay) / benchmark_pay)
    if gap_pct <= 0:
        return 0.0
    if gap_pct >= JOB_OFFER_MAX_GAP_PCT:
        return 1.0
    # Linear interpolation
    return JOB_OFFER_BASE_PROBABILITY + (1.0 - JOB_OFFER_BASE_PROBABILITY) * (gap_pct / JOB_OFFER_MAX_GAP_PCT)


async def run_betacorp_check(pool: asyncpg.Pool, llm: LLMClient, sim_time: datetime) -> dict:
    """
    Check all active employees against market_benchmark.
    Fire job offer emails, flag near-misses, and handle resignation determinism.
    """
    results = {"offers_sent": 0, "resignations": 0, "flags_raised": 0}
    rng = random.Random(int(sim_time.timestamp()))  # deterministic seed per sim-time

    async with pool.acquire() as conn:
        # Load all active employees + their benchmark
        employees = await conn.fetch("""
            SELECT e.id, e.name, e.email, e.department, e.role_tier, e.pay_rate, e.hired_at,
                   m.benchmark_pay
            FROM employees e
            LEFT JOIN market_benchmark m ON m.department = e.department AND m.role_tier = e.role_tier
            WHERE e.status = 'active'
        """)

        for emp in employees:
            pay = Decimal(str(emp["pay_rate"]))
            benchmark = Decimal(str(emp["benchmark_pay"])) if emp["benchmark_pay"] else None
            if benchmark is None:
                continue

            gap_pct = float((benchmark - pay) / benchmark) if benchmark > 0 else 0.0
            if gap_pct <= 0.01:
                continue  # Within 1% — no risk

            probability = compute_offer_probability(pay, benchmark)
            roll = rng.random()

            if gap_pct >= RESIGNATION_GAP_THRESHOLD_PCT:
                # Check if an unaddressed offer was sent > RESIGNATION_GRACE_SIM_DAYS ago
                last_offer = await conn.fetchrow("""
                    SELECT created_at FROM system_audit_log
                    WHERE action = 'betacorp_offer_sent'
                      AND detail->>'employee_id' = $1
                    ORDER BY created_at DESC LIMIT 1
                """, str(emp["id"]))

                if last_offer:
                    offer_age_days = (sim_time - last_offer["created_at"].replace(tzinfo=timezone.utc)).days
                    if offer_age_days >= RESIGNATION_GRACE_SIM_DAYS:
                        # Check if pay was raised since the offer
                        pay_change = await conn.fetchrow("""
                            SELECT created_at FROM system_audit_log
                            WHERE action IN ('raise_applied', 'pay_cut_applied')
                              AND detail->>'employee_id' = $1
                              AND created_at > $2
                            LIMIT 1
                        """, str(emp["id"]), last_offer["created_at"])

                        if not pay_change:
                            # Employee resigns
                            log.info("BetaCorp: employee %d (%s) resigns due to unaddressed pay gap", emp["id"], emp["name"])
                            await conn.execute(
                                "UPDATE employees SET status = 'resigned', terminated_at = $1 WHERE id = $2",
                                sim_time, emp["id"]
                            )
                            await audit_log(conn, "external-world", "employee_resigned_betacorp", {
                                "employee_id": emp["id"],
                                "name": emp["name"],
                                "gap_pct": round(gap_pct * 100, 1),
                            })
                            results["resignations"] += 1
                            continue

            if roll < probability:
                # Send a BetaCorp job offer email
                relay_sender = f"external.relay@{MAILSERVER_DOMAIN}"

                # Generate the email body via LLM (cheap tier)
                try:
                    email_body = await llm.chat([
                        {"role": "system", "content":
                            "You are writing a realistic recruiting email from a competitor company. "
                            "Keep it professional, specific to the recipient's role, and enticing but not over-the-top. "
                            "Do not invent numbers — don't mention salary in the email. "
                            "2-3 short paragraphs. No subject line in body."},
                        {"role": "user", "content":
                            f"Write a job offer email to {emp['name']}, a {emp['role_tier'].upper()} "
                            f"in {emp['department']} at FakeCo. "
                            f"The recruiting company is BetaCorp. Recruiter is {BETACORP_RECRUITER_NAME}."},
                    ], model="cheap")
                except Exception as exc:
                    log.warning("LLM email generation failed, using fallback: %s", exc)
                    email_body = (
                        f"Hi {emp['name'].split()[0]},\n\n"
                        f"I've been following your career and I think you'd be a great fit for a role here at BetaCorp. "
                        f"We're growing fast and looking for experienced {emp['department']} professionals.\n\n"
                        f"Would you be open to a quick call?\n\n"
                        f"Best,\n{BETACORP_RECRUITER_NAME}\nBetaCorp"
                    )

                try:
                    await inject_email(
                        to_email=emp["email"],
                        from_display_name=f"{BETACORP_RECRUITER_NAME} (BetaCorp)",
                        from_display_email=BETACORP_RECRUITER_EMAIL,
                        subject=f"Exciting opportunity at BetaCorp — {emp['department']} {emp['role_tier'].upper()} role",
                        body=email_body,
                        relay_email=relay_sender,
                    )
                    await audit_log(conn, "external-world", "betacorp_offer_sent", {
                        "employee_id": emp["id"],
                        "name": emp["name"],
                        "gap_pct": round(gap_pct * 100, 1),
                        "probability": round(probability, 3),
                    })
                    results["offers_sent"] += 1
                except Exception as exc:
                    log.error("Failed to inject BetaCorp offer email for %s: %s", emp["name"], exc)

            elif gap_pct >= 0.10 and probability >= 0.5:
                # Near-miss: flag for Principal via pending_reactions
                existing_flag = await conn.fetchrow("""
                    SELECT id FROM pending_reactions
                    WHERE target_employee_id = $1 AND status = 'pending'
                    LIMIT 1
                """, emp["id"])
                if not existing_flag:
                    # Get or create a thread for this
                    thread_id = await conn.fetchval("""
                        INSERT INTO narrative_threads (topic, department, status, summary)
                        VALUES ($1, $2, 'open', $3)
                        RETURNING id
                    """,
                        f"Pay gap risk: {emp['name']}",
                        emp["department"],
                        f"{emp['name']} is {gap_pct*100:.0f}% below market benchmark. High BetaCorp risk.",
                    )
                    await conn.execute("""
                        INSERT INTO pending_reactions (thread_id, target_employee_id, status)
                        VALUES ($1, $2, 'pending')
                    """, thread_id, emp["id"])
                    await audit_log(conn, "external-world", "pay_gap_flag_raised", {
                        "employee_id": emp["id"],
                        "name": emp["name"],
                        "gap_pct": round(gap_pct * 100, 1),
                    })
                    results["flags_raised"] += 1

    return results


# ---------------------------------------------------------------------------
# Phase 22: Customer & revenue management
# ---------------------------------------------------------------------------
async def run_customer_check(pool: asyncpg.Pool, llm: LLMClient, sim_time: datetime) -> dict:
    """
    Check active customers for SLA violations.
    Deterministic churn if support ticket open too long.
    Spec §11.2.
    """
    results = {"churned": 0, "at_risk": 0}

    async with pool.acquire() as conn:
        # Find active customers with open Zammad tickets older than SLA threshold
        active_customers = await conn.fetch("""
            SELECT id, company_name, assigned_support_rep_id, support_sla_hours
            FROM customers
            WHERE relationship_status = 'active'
        """)

        for customer in active_customers:
            # Check Zammad for open tickets from this customer
            try:
                async with httpx.AsyncClient(timeout=10.0) as http:
                    r = await http.get(
                        f"{ZAMMAD_URL}/api/v1/tickets/search?query=note:{customer['company_name']}&state=open",
                        headers={"Authorization": f"Token token={ZAMMAD_ADMIN_TOKEN}"},
                    )
                    if r.status_code != 200:
                        continue
                    tickets = r.json()
            except Exception:
                continue

            for ticket in (tickets if isinstance(tickets, list) else []):
                created_at = ticket.get("created_at", "")
                if not created_at:
                    continue
                try:
                    ticket_age_hours = (
                        sim_time - datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    ).total_seconds() / 3600
                except Exception:
                    continue

                if ticket_age_hours > customer["support_sla_hours"]:
                    log.info("Customer %s: SLA exceeded (%dh) — churning", customer["company_name"], int(ticket_age_hours))
                    await conn.execute(
                        "UPDATE customers SET relationship_status = 'churned' WHERE id = $1",
                        customer["id"]
                    )
                    await audit_log(conn, "external-world", "customer_churned_sla", {
                        "customer_id": customer["id"],
                        "company_name": customer["company_name"],
                        "ticket_age_hours": round(ticket_age_hours, 1),
                    })
                    results["churned"] += 1
                    break
                elif ticket_age_hours > customer["support_sla_hours"] * 0.75:
                    # At-risk: mark in DB and create pending reaction
                    await conn.execute(
                        "UPDATE customers SET relationship_status = 'at_risk' WHERE id = $1",
                        customer["id"]
                    )
                    results["at_risk"] += 1

    return results


async def generate_prospect_activity(pool: asyncpg.Pool, llm: LLMClient, sim_time: datetime) -> None:
    """
    Generate occasional prospect-to-active customer activity.
    Creates Zammad tickets (as inbound support/sales queries) for prospects.
    Business-hours gated: fires only Mon-Fri 9am-6pm sim-time.
    """
    # Business-hours gate (spec §19.4)
    if sim_time.weekday() >= 5:  # Weekend
        return
    if not (9 <= sim_time.hour < 18):  # Outside 9am-6pm
        return

    async with pool.acquire() as conn:
        prospects = await conn.fetch(
            "SELECT id, company_name, contact_name, contact_email, assigned_sales_rep_id FROM customers WHERE relationship_status = 'prospect' ORDER BY RANDOM() LIMIT 2"
        )

        for prospect in prospects:
            try:
                # Generate a realistic inquiry email body via LLM (cheap)
                inquiry = await llm.chat([
                    {"role": "system", "content": "Write a short 2-sentence email from a prospect company to a B2B software vendor's sales team. Professional, specific, asking about pricing or a demo."},
                    {"role": "user", "content": f"Prospect: {prospect['company_name']} ({prospect['contact_name']}). Vendor: FakeCo."},
                ], model="cheap")
            except Exception:
                inquiry = f"Hi, I'm {prospect['contact_name']} from {prospect['company_name']}. We're evaluating vendors and would love to learn more about your product. Can we schedule a demo?"

            try:
                async with httpx.AsyncClient(timeout=10.0) as http:
                    await http.post(f"{ZAMMAD_URL}/api/v1/tickets",
                        headers={"Authorization": f"Token token={ZAMMAD_ADMIN_TOKEN}"},
                        json={
                            "title": f"[PROSPECT] {prospect['company_name']}: inquiry",
                            "group": "Users",
                            # `customer_id` is a hard-required field on ticket creation — Zammad
                            # accepts a "guess:<email>" shorthand that resolves to (or auto-creates) that customer.
                            "customer_id": f"guess:{prospect['contact_email']}",
                            "article": {
                                "subject": f"Inquiry from {prospect['contact_name']} at {prospect['company_name']}",
                                "body": inquiry,
                                # "email" article type requires the group to have an outgoing
                                # email channel configured, which this sim environment doesn't
                                # provision — "phone" simulates the inbound contact without that
                                # dependency (matches human-bridge's ticket-creation pattern).
                                "type": "phone",
                                "internal": False,
                            },
                        }
                    )
                await audit_log(conn, "external-world", "prospect_inquiry_generated", {
                    "customer_id": prospect["id"],
                    "company_name": prospect["company_name"],
                })
            except Exception as exc:
                log.warning("Failed to create prospect Zammad ticket: %s", exc)


# ---------------------------------------------------------------------------
# FastAPI app + combined tick loop
# ---------------------------------------------------------------------------
_pool: asyncpg.Pool | None = None
_llm: LLMClient | None = None
_http: httpx.AsyncClient | None = None
EXTERNAL_WORLD_TICK_INTERVAL = float(os.environ.get("EXTERNAL_WORLD_TICK_INTERVAL", "300"))  # 5 min default


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _llm, _http
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    _llm = LLMClient(LITELLM_URL, LITELLM_API_KEY)
    _http = httpx.AsyncClient(timeout=10.0)
    task = asyncio.create_task(external_world_tick_loop())
    log.info("external-world: ready")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await _llm.close()
    await _http.aclose()
    await _pool.close()


async def external_world_tick_loop():
    while True:
        try:
            sim_time = await get_sim_time(_http)
            await run_betacorp_check(_pool, _llm, sim_time)
            await run_customer_check(_pool, _llm, sim_time)
            await generate_prospect_activity(_pool, _llm, sim_time)
        except Exception as exc:
            log.error("External world tick error: %s", exc)
        await asyncio.sleep(EXTERNAL_WORLD_TICK_INTERVAL)


app = FastAPI(
    title="FakeCo External World",
    description="BetaCorp rival (Phase 21) and customer/revenue generator (Phase 22).",
    version="1.0.0",
    lifespan=lifespan,
)

PoolDep = Annotated[asyncpg.Pool, Depends(lambda: _pool)]


@app.get("/health")
async def health():
    return {"status": "ok", "service": "external-world"}


@app.post("/betacorp/check")
async def manual_betacorp_check(pool: PoolDep = None):
    """Manually trigger a BetaCorp pay-gap check."""
    sim_time = await get_sim_time(_http)
    return await run_betacorp_check(_pool, _llm, sim_time)


@app.post("/customers/check")
async def manual_customer_check(pool: PoolDep = None):
    """Manually trigger a customer SLA check."""
    sim_time = await get_sim_time(_http)
    return await run_customer_check(_pool, _llm, sim_time)
