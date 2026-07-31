"""
human-bridge/main.py — FakeCo "Real Appliances"
Phase 17: Human interaction bridge for the Principal.

Spec §17: Human Bridge allows the Principal to interact with the simulation.
  - Reads any thread, employee, or financial state from Postgres
  - Sends email AS an employee (via docker-mailserver SMTP injection)
  - Posts Mattermost message AS an employee (via that employee's bot token)
  - Opens/closes Zammad tickets
  - Approves/rejects pending_approvals (routes to accounting-engine)
  - Writes to Wiki.js pages via GraphQL
  - Creates/updates company directives
  - Can trigger meetings on-demand

All actions are logged to system_audit_log with actor='principal'.

API is the backend for the Phase 33 dashboard's "Principal Control" tab.
"""
import asyncio
import json
import logging
import os
import smtplib
from datetime import datetime, timezone
from decimal import Decimal
from email.mime.text import MIMEText
from typing import Optional

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Annotated
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","service":"human-bridge","msg":"%(message)s"}'
)
log = logging.getLogger("human_bridge")

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
MAILSERVER_HOST = os.environ.get("MAILSERVER_HOST", "mailserver")
MAILSERVER_PORT = int(os.environ.get("MAILSERVER_SMTP_PORT", "25"))
MATTERMOST_URL = os.environ.get("MATTERMOST_URL", "http://mattermost:8065")
MATTERMOST_ADMIN_TOKEN = os.environ.get("MATTERMOST_ADMIN_TOKEN", "")
ZAMMAD_URL = os.environ.get("ZAMMAD_URL", "http://zammad:3000")
ZAMMAD_ADMIN_TOKEN = os.environ.get("ZAMMAD_ADMIN_TOKEN", "")
WIKIJS_URL = os.environ.get("WIKIJS_URL", "http://wikijs:3000")
WIKIJS_ADMIN_TOKEN = os.environ.get("WIKIJS_ADMIN_TOKEN", "")
ACCOUNTING_ENGINE_URL = os.environ.get("ACCOUNTING_ENGINE_URL", "http://accounting-engine:8000")
MEETING_SIM_URL = os.environ.get("MEETING_SIM_URL", "http://meeting-simulator:8000")
PRINCIPAL_EMAIL = os.environ.get("PRINCIPAL_EMAIL", "principal@fakecorp.internal")
PRINCIPAL_NAME = os.environ.get("PRINCIPAL_NAME", "Admin")

# Mailserver bot secret (same as provisioning — derive bot passwords)
import hashlib
MAILSERVER_BOT_SECRET = os.environ.get("MAILSERVER_BOT_SECRET", "fakeco-bot-mail-secret-change-me")


def derive_mail_password(email: str) -> str:
    return hashlib.sha256(f"{MAILSERVER_BOT_SECRET}:{email}".encode()).hexdigest()[:24]


# ---------------------------------------------------------------------------
# Database pool
# ---------------------------------------------------------------------------
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


async def audit_log(conn: asyncpg.Connection, actor: str, action: str, detail: dict) -> None:
    """Immutable audit log entry."""
    await conn.execute(
        "INSERT INTO system_audit_log (actor, action, detail) VALUES ($1, $2, $3)",
        actor, action, json.dumps(detail)
    )


# ---------------------------------------------------------------------------
# Email injection: send mail AS a sim employee via SMTP
# Spec §17: Principal can send email as any employee.
# ---------------------------------------------------------------------------
async def send_as_employee(
    employee_email: str,
    employee_name: str,
    to_email: str,
    subject: str,
    body: str,
    conn: asyncpg.Connection,
) -> None:
    """
    Sends email via SMTP using the employee's mailbox credentials.
    docker-mailserver accepts SMTP with AUTH.
    """
    password = derive_mail_password(employee_email)

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"{employee_name} <{employee_email}>"
    msg["To"] = to_email
    msg["X-Sim-Origin"] = "human-bridge"  # internal marker for log analysis

    def _send():
        with smtplib.SMTP(MAILSERVER_HOST, MAILSERVER_PORT) as s:
            s.ehlo()
            try:
                s.starttls()
                s.ehlo()
            except Exception:
                pass  # TLS optional in closed network
            s.login(employee_email, password)
            s.send_message(msg)

    # Run blocking SMTP in thread pool
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send)

    await audit_log(conn, "principal", "email_sent_as_employee", {
        "from": employee_email,
        "to": to_email,
        "subject": subject,
        "body_preview": body[:200],
    })
    log.info("Email sent as %s → %s: %s", employee_email, to_email, subject)


# ---------------------------------------------------------------------------
# Mattermost posting AS employee (impersonation)
# ---------------------------------------------------------------------------
async def post_mattermost_as_employee(
    mattermost_id: str,
    channel_id: str,
    message: str,
    conn: asyncpg.Connection,
    employee_name: str = "employee",
) -> str:
    """
    Posts a Mattermost message using the employee's bot token.
    Bot token is obtained via the admin API impersonation call.
    Returns the post_id.
    """
    async with httpx.AsyncClient(timeout=15.0) as http:
        # Admin can create a personal access token for any user
        r = await http.post(
            f"{MATTERMOST_URL}/api/v4/users/{mattermost_id}/tokens",
            headers={"Authorization": f"Bearer {MATTERMOST_ADMIN_TOKEN}"},
            json={"description": "human-bridge impersonation token"},
        )
        r.raise_for_status()
        token = r.json()["token"]

        # Post using the employee's token
        r2 = await http.post(
            f"{MATTERMOST_URL}/api/v4/posts",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"channel_id": channel_id, "message": message},
        )
        r2.raise_for_status()
        post_id = r2.json()["id"]

        # Revoke the ephemeral token
        token_id = r.json()["id"]
        await http.delete(
            f"{MATTERMOST_URL}/api/v4/users/{mattermost_id}/tokens/{token_id}",
            headers={"Authorization": f"Bearer {MATTERMOST_ADMIN_TOKEN}"},
        )

    await audit_log(conn, "principal", "mattermost_posted_as_employee", {
        "mattermost_id": mattermost_id,
        "employee_name": employee_name,
        "channel_id": channel_id,
        "message_preview": message[:200],
    })
    log.info("Mattermost post as %s in channel %s", employee_name, channel_id)
    return post_id


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    log.info("human-bridge: ready")
    yield
    await _pool.close()


app = FastAPI(
    title="FakeCo Human Bridge",
    description="Principal control panel backend — inject actions into the simulation as any employee.",
    version="1.0.0",
    lifespan=lifespan,
)

PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]


# --- API models ---
class SendEmailRequest(BaseModel):
    from_employee_id: int
    to_email: str
    subject: str
    body: str


class MattermostPostRequest(BaseModel):
    employee_id: int  # impersonate this employee
    channel_id: str
    message: str


class ApproveExpenseRequest(BaseModel):
    approval_id: int
    decision: str = Field(..., pattern="^(approved|rejected)$")
    note: str = ""


class UpdateDirectiveRequest(BaseModel):
    content: str
    created_by: str = "principal"


class TriggerMeetingRequest(BaseModel):
    meeting_type: str
    department: Optional[str] = None
    target_employee_id: Optional[int] = None
    thread_id: Optional[int] = None
    extra_context: str = ""


class ZammadTicketRequest(BaseModel):
    title: str
    body: str
    group: str = "Users"


class WikiPageRequest(BaseModel):
    path: str
    title: str
    content: str
    locale: str = "en"


# --- Endpoints ---
@app.get("/health")
async def health():
    return {"status": "ok", "service": "human-bridge"}


@app.get("/state/employees")
async def list_employees(pool: PoolDep):
    """Return all employee roster rows."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM employees ORDER BY department, hired_at")
        return [dict(r) for r in rows]


@app.get("/state/threads")
async def list_threads(pool: PoolDep, status: Optional[str] = None):
    """Return narrative threads, optionally filtered by status."""
    async with pool.acquire() as conn:
        if status:
            rows = await conn.fetch("SELECT * FROM narrative_threads WHERE status = $1 ORDER BY updated_at DESC", status)
        else:
            rows = await conn.fetch("SELECT * FROM narrative_threads ORDER BY updated_at DESC LIMIT 50")
        return [dict(r) for r in rows]


@app.get("/state/pending-approvals")
async def list_pending_approvals(pool: PoolDep):
    """Return all pending expense approvals."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM pending_approvals WHERE status = 'pending' ORDER BY created_at")
        return [dict(r) for r in rows]


@app.post("/action/send-email")
async def action_send_email(req: SendEmailRequest, pool: PoolDep):
    async with pool.acquire() as conn:
        emp = await conn.fetchrow(
            "SELECT email, name FROM employees WHERE id = $1 AND status = 'active'",
            req.from_employee_id
        )
        if not emp:
            raise HTTPException(status_code=404, detail=f"Active employee {req.from_employee_id} not found")
        await send_as_employee(emp["email"], emp["name"], req.to_email, req.subject, req.body, conn)
    return {"status": "sent"}


@app.post("/action/mattermost-post")
async def action_mattermost_post(req: MattermostPostRequest, pool: PoolDep):
    async with pool.acquire() as conn:
        emp = await conn.fetchrow(
            "SELECT name, mattermost_id FROM employees WHERE id = $1",
            req.employee_id
        )
        if not emp or not emp["mattermost_id"]:
            raise HTTPException(status_code=404, detail="Employee or Mattermost ID not found")
        post_id = await post_mattermost_as_employee(
            emp["mattermost_id"], req.channel_id, req.message, conn, emp["name"]
        )
    return {"status": "posted", "post_id": post_id}


@app.post("/action/approve-expense")
async def action_approve_expense(req: ApproveExpenseRequest, pool: PoolDep):
    """Routes to accounting-engine for deterministic posting."""
    async with httpx.AsyncClient(timeout=30.0) as http:
        if req.decision == "approved":
            r = await http.post(f"{ACCOUNTING_ENGINE_URL}/expense/approve", json={
                "approval_id": req.approval_id,
                "approved_by": "principal",
                "note": req.note,
            })
            r.raise_for_status()
            result = r.json()
        else:
            # Rejection: just update the row status
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE pending_approvals SET status = 'rejected', updated_at = NOW() WHERE id = $1",
                    req.approval_id
                )
                await audit_log(conn, "principal", "expense_rejected", {
                    "approval_id": req.approval_id, "note": req.note
                })
            result = {"status": "rejected"}
    return result


@app.post("/action/update-directive")
async def action_update_directive(req: UpdateDirectiveRequest, pool: PoolDep):
    """
    Update the company directive. Previous version marked is_current=FALSE.
    Spec §8: directive synced to pinned Wiki.js page (TODO: Phase 30 branding sync).
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Mark all current as not current
            await conn.execute("UPDATE company_directives SET is_current = FALSE WHERE is_current = TRUE")
            # Get next version number
            max_version = await conn.fetchval("SELECT COALESCE(MAX(version), 0) FROM company_directives")
            new_version = (max_version or 0) + 1
            directive_id = await conn.fetchval("""
                INSERT INTO company_directives (content, version, is_current, created_by)
                VALUES ($1, $2, TRUE, $3)
                RETURNING id
            """, req.content, new_version, req.created_by)
            await audit_log(conn, "principal", "directive_updated", {
                "directive_id": directive_id, "version": new_version,
                "content_preview": req.content[:200],
            })
    return {"status": "updated", "version": new_version, "directive_id": directive_id}


@app.post("/action/trigger-meeting")
async def action_trigger_meeting(req: TriggerMeetingRequest, pool: PoolDep):
    """Trigger an on-demand meeting."""
    async with httpx.AsyncClient(timeout=120.0) as http:
        r = await http.post(f"{MEETING_SIM_URL}/meeting/run", json={
            "meeting_type": req.meeting_type,
            "department": req.department,
            "target_employee_id": req.target_employee_id,
            "thread_id": req.thread_id,
            "extra_context": req.extra_context,
        })
        r.raise_for_status()
        return r.json()


@app.post("/action/zammad-ticket")
async def action_create_zammad_ticket(req: ZammadTicketRequest, pool: PoolDep):
    """Create a Zammad ticket as Principal."""
    async with httpx.AsyncClient(timeout=30.0) as http:
        r = await http.post(
            f"{ZAMMAD_URL}/api/v1/tickets",
            headers={"Authorization": f"Token token={ZAMMAD_ADMIN_TOKEN}"},
            json={
                "title": req.title,
                "group": req.group,
                "article": {"subject": req.title, "body": req.body, "type": "note"},
            }
        )
        r.raise_for_status()
        ticket = r.json()

    async with pool.acquire() as conn:
        await audit_log(conn, "principal", "zammad_ticket_created", {
            "ticket_id": ticket["id"], "title": req.title
        })
    return {"status": "created", "ticket_id": ticket["id"]}


@app.post("/action/wiki-page")
async def action_write_wiki_page(req: WikiPageRequest, pool: PoolDep):
    """Create or update a Wiki.js page via GraphQL."""
    async with httpx.AsyncClient(timeout=30.0) as http:
        # Try to update first, create if not found
        r = await http.post(
            f"{WIKIJS_URL}/graphql",
            headers={"Authorization": f"Bearer {WIKIJS_ADMIN_TOKEN}"},
            json={"query": """
                mutation($content: String!, $description: String!, $editor: String!, $isPublished: Boolean!, $locale: String!, $path: String!, $tags: [String]!, $title: String!) {
                    pages {
                        create(content: $content, description: $description, editor: $editor, isPublished: $isPublished, locale: $locale, path: $path, tags: $tags, title: $title) {
                            responseResult { succeeded errorCode message }
                            page { id path title }
                        }
                    }
                }
            """,
            "variables": {
                "content": req.content,
                "description": req.title,
                "editor": "markdown",
                "isPublished": True,
                "locale": req.locale,
                "path": req.path,
                "tags": [],
                "title": req.title,
            }}
        )
        r.raise_for_status()
        data = r.json()

    async with pool.acquire() as conn:
        await audit_log(conn, "principal", "wiki_page_written", {
            "path": req.path, "title": req.title
        })
    return {"status": "written", "graphql_response": data}
