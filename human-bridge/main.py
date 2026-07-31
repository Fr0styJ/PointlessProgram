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
from email.utils import formatdate, make_msgid
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
MAILSERVER_PORT = int(os.environ.get("MAILSERVER_SMTP_PORT", "587"))
MATTERMOST_URL = os.environ.get("MATTERMOST_URL", "http://mattermost:8065")
MATTERMOST_ADMIN_TOKEN = os.environ.get("MATTERMOST_ADMIN_TOKEN", "")
ZAMMAD_URL = os.environ.get("ZAMMAD_URL", "http://zammad-nginx:8080")
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
# Phase 17 detection layer config
# ---------------------------------------------------------------------------
MATTERMOST_TEAM_ID = os.environ.get("MATTERMOST_TEAM_ID", "")
MAILSERVER_IMAP_PORT = int(os.environ.get("MAILSERVER_IMAP_PORT", "143"))
DETECTION_POLL_INTERVAL_SECONDS = float(os.environ.get("DETECTION_POLL_INTERVAL_SECONDS", "8"))

# In-memory cache of the Principal's resolved account IDs on each appliance.
# provision-principal doesn't persist these anywhere, so we resolve at runtime
# and cache for the life of the process (refreshed on a cache miss).
_principal_ids: dict[str, str] = {}


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
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
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

        # Ensure the bot is actually a member of the target channel first — team membership
        # (granted at provisioning time) does not imply channel membership, and Mattermost
        # returns a bare 403 "You do not have the appropriate permissions" on /posts otherwise,
        # not a more specific "not a channel member" error. Idempotent: 201 if newly added,
        # error ignored if already a member.
        await http.post(
            f"{MATTERMOST_URL}/api/v4/channels/{channel_id}/members",
            headers={"Authorization": f"Bearer {MATTERMOST_ADMIN_TOKEN}"},
            json={"user_id": mattermost_id},
        )

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
# Phase 17: DETECTION layer
#
# The Principal is a real human who can act directly in the Mattermost,
# Zammad, Wiki.js and webmail UIs (not through the /action/* injection API
# above). This section detects that human-authored activity and converts it
# into narrative_events(origin='human') + pending_reactions rows so the
# orchestrator's continuity loop (Phase 18) knows an employee owes a reaction.
#
# Implementation choice — polling, not webhooks: Mattermost outgoing webhooks
# only fire on trigger words (not full-message capture), Zammad/Wiki.js don't
# have first-class outbound webhook registration flows that are simpler than
# polling here, and the spec's own phrasing ("via native webhooks... or IMAP
# polling") already treats polling as an accepted mechanism for at least one
# of the four sources. We extend that same pragmatic choice to all four: an
# asyncio background task per source, each polling its appliance's REST/
# GraphQL API every DETECTION_POLL_INTERVAL_SECONDS. See BUILD_LOG.md Phase 17
# entry for the full trade-off writeup.
# ---------------------------------------------------------------------------

async def _ensure_detection_tables(conn: asyncpg.Connection) -> None:
    """Small cursor-tracking table so polling survives a human-bridge restart
    without reprocessing already-seen posts/articles/pages/emails."""
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS human_bridge_cursors (
            source TEXT PRIMARY KEY,
            cursor_value TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


async def _get_cursor(conn: asyncpg.Connection, source: str) -> str:
    val = await conn.fetchval("SELECT cursor_value FROM human_bridge_cursors WHERE source = $1", source)
    return val or ""


async def _set_cursor(conn: asyncpg.Connection, source: str, value: str) -> None:
    await conn.execute("""
        INSERT INTO human_bridge_cursors (source, cursor_value, updated_at) VALUES ($1, $2, NOW())
        ON CONFLICT (source) DO UPDATE SET cursor_value = $2, updated_at = NOW()
    """, source, str(value))


async def _get_or_create_thread(conn: asyncpg.Connection, employee: asyncpg.Record) -> int:
    """Reuse the most recently active open thread for the employee's department,
    matching the convention meeting-simulator uses (narrative_threads keyed by
    topic/department/status), or open a new one."""
    thread_id = await conn.fetchval("""
        SELECT id FROM narrative_threads
        WHERE department = $1 AND status = 'open'
        ORDER BY updated_at DESC LIMIT 1
    """, employee["department"])
    if thread_id:
        return thread_id
    return await conn.fetchval("""
        INSERT INTO narrative_threads (topic, department, status, summary)
        VALUES ($1, $2, 'open', '')
        RETURNING id
    """, f"Human interaction — {employee['name']}", employee["department"])


async def _record_human_event(
    conn: asyncpg.Connection,
    employee: asyncpg.Record,
    source_type: str,
    source_ref: str,
    summary: str,
) -> None:
    """Write narrative_events(origin='human') + pending_reactions targeting the
    employee, per Phase 17 exit criteria. Skips duplicates on source_ref."""
    dup = await conn.fetchval(
        "SELECT id FROM narrative_events WHERE source_type = $1 AND source_ref = $2",
        source_type, source_ref,
    )
    if dup:
        return
    thread_id = await _get_or_create_thread(conn, employee)
    event_id = await conn.fetchval("""
        INSERT INTO narrative_events (thread_id, employee_id, origin, source_type, source_ref, short_summary)
        VALUES ($1, $2, 'human', $3, $4, $5)
        RETURNING id
    """, thread_id, employee["id"], source_type, source_ref, summary[:500])
    await conn.execute("""
        INSERT INTO pending_reactions (thread_id, target_employee_id, triggering_event_id, status)
        VALUES ($1, $2, $3, 'pending')
    """, thread_id, employee["id"], event_id)
    await audit_log(conn, "principal", "human_activity_detected", {
        "employee_id": employee["id"], "source_type": source_type, "source_ref": source_ref,
    })
    log.info("Detected human activity (%s) addressed to %s -> event %d, pending_reactions created",
              source_type, employee["name"], event_id)


def _mattermost_username_for(email: str) -> str:
    return email.split("@")[0].replace(".", "_").lower()


async def _resolve_employee_by_mattermost_mention(conn: asyncpg.Connection, text: str) -> Optional[asyncpg.Record]:
    employees = await conn.fetch("SELECT * FROM employees WHERE status = 'active'")
    for emp in employees:
        uname = _mattermost_username_for(emp["email"])
        if f"@{uname}" in text:
            return emp
    return None


async def _resolve_employee_by_email(conn: asyncpg.Connection, address: str) -> Optional[asyncpg.Record]:
    address = address.strip().lower()
    return await conn.fetchrow(
        "SELECT * FROM employees WHERE status = 'active' AND (lower(email) = $1 OR lower(mailbox_address) = $1)",
        address,
    )


async def _resolve_employee_by_zammad_agent(conn: asyncpg.Connection, agent_id) -> Optional[asyncpg.Record]:
    if agent_id is None:
        return None
    return await conn.fetchrow(
        "SELECT * FROM employees WHERE status = 'active' AND zammad_agent_id = $1", str(agent_id)
    )


async def _resolve_employee_by_wiki_tag(conn: asyncpg.Connection, tags: list[str]) -> Optional[asyncpg.Record]:
    """Convention established here (no prior tagging convention existed):
    a wiki page "related to" an employee carries a tag 'emp-<employee_id>'."""
    for tag in tags or []:
        if tag.startswith("emp-"):
            try:
                emp_id = int(tag[len("emp-"):])
            except ValueError:
                continue
            emp = await conn.fetchrow("SELECT * FROM employees WHERE id = $1 AND status = 'active'", emp_id)
            if emp:
                return emp
    return None


# --- Principal identity resolution (cached in-memory) -----------------------

async def _resolve_principal_mattermost_id(http: httpx.AsyncClient) -> Optional[str]:
    if "mattermost" in _principal_ids:
        return _principal_ids["mattermost"]
    username = _mattermost_username_for(PRINCIPAL_EMAIL)
    r = await http.get(
        f"{MATTERMOST_URL}/api/v4/users/username/{username}",
        headers={"Authorization": f"Bearer {MATTERMOST_ADMIN_TOKEN}"},
    )
    if r.status_code == 200:
        uid = r.json()["id"]
        _principal_ids["mattermost"] = uid
        return uid
    log.warning("human-bridge: could not resolve Principal Mattermost id (status=%s)", r.status_code)
    return None


async def _resolve_principal_zammad_id(http: httpx.AsyncClient) -> Optional[int]:
    if "zammad" in _principal_ids:
        return _principal_ids["zammad"]
    r = await http.get(
        f"{ZAMMAD_URL}/api/v1/users/search",
        headers={"Authorization": f"Token token={ZAMMAD_ADMIN_TOKEN}"},
        params={"query": PRINCIPAL_EMAIL},
    )
    if r.status_code == 200:
        users = r.json()
        for u in users:
            if u.get("email", "").lower() == PRINCIPAL_EMAIL.lower():
                _principal_ids["zammad"] = u["id"]
                return u["id"]
    log.warning("human-bridge: could not resolve Principal Zammad id (status=%s)", r.status_code)
    return None


async def _resolve_principal_wiki_id(http: httpx.AsyncClient) -> Optional[int]:
    if "wiki" in _principal_ids:
        return _principal_ids["wiki"]
    r = await http.post(
        f"{WIKIJS_URL}/graphql",
        headers={"Authorization": f"Bearer {WIKIJS_ADMIN_TOKEN}"},
        json={"query": """
            query {
              users { list { id email } }
            }
        """},
    )
    if r.status_code == 200:
        data = r.json()
        for u in data.get("data", {}).get("users", {}).get("list", []) or []:
            if (u.get("email") or "").lower() == PRINCIPAL_EMAIL.lower():
                _principal_ids["wiki"] = u["id"]
                return u["id"]
    log.warning("human-bridge: could not resolve Principal Wiki.js id (status=%s)", r.status_code)
    return None


# --- Mattermost polling ------------------------------------------------------

async def _poll_mattermost_once(pool: asyncpg.Pool) -> None:
    async with httpx.AsyncClient(timeout=15.0) as http:
        principal_id = await _resolve_principal_mattermost_id(http)
        if not principal_id:
            return
        headers = {"Authorization": f"Bearer {MATTERMOST_ADMIN_TOKEN}"}
        r = await http.get(f"{MATTERMOST_URL}/api/v4/users/{principal_id}/teams/{MATTERMOST_TEAM_ID}/channels",
                            headers=headers)
        if r.status_code != 200:
            log.warning("human-bridge: mattermost channel list failed (%s)", r.status_code)
            return
        channels = r.json()

        async with pool.acquire() as conn:
            for ch in channels:
                channel_id = ch["id"]
                cursor_key = f"mattermost:{channel_id}"
                since = await _get_cursor(conn, cursor_key)
                params = {"page": 0, "per_page": 50}
                if since:
                    params["since"] = since
                pr = await http.get(f"{MATTERMOST_URL}/api/v4/channels/{channel_id}/posts", headers=headers, params=params)
                if pr.status_code != 200:
                    continue
                posts_data = pr.json()
                posts = posts_data.get("posts", {})
                latest_update = int(since) if since else 0
                for post_id, post in posts.items():
                    latest_update = max(latest_update, int(post.get("update_at", 0)))
                    if post.get("user_id") != principal_id:
                        continue
                    message = post.get("message", "") or ""
                    emp = await _resolve_employee_by_mattermost_mention(conn, message)
                    if emp:
                        await _record_human_event(
                            conn, emp, "chat", f"mattermost:{post_id}",
                            f"Principal posted in Mattermost mentioning {emp['name']}: {message[:200]}",
                        )
                if latest_update:
                    await _set_cursor(conn, cursor_key, latest_update)


# --- Zammad polling -----------------------------------------------------------

async def _poll_zammad_once(pool: asyncpg.Pool) -> None:
    async with httpx.AsyncClient(timeout=15.0) as http:
        principal_id = await _resolve_principal_zammad_id(http)
        if not principal_id:
            return
        headers = {"Authorization": f"Token token={ZAMMAD_ADMIN_TOKEN}"}
        # /api/v1/ticket_articles (bare list) 403s under a plain token-auth
        # Agent account — but /api/v1/tickets + per-ticket
        # /api/v1/ticket_articles/by_ticket/{id} both work, so we walk tickets
        # and pull articles per-ticket instead.
        tr_list = await http.get(f"{ZAMMAD_URL}/api/v1/tickets", headers=headers)
        if tr_list.status_code != 200:
            log.warning("human-bridge: zammad ticket list failed (%s)", tr_list.status_code)
            return
        tickets = tr_list.json()

        async with pool.acquire() as conn:
            cursor_key = "zammad:article"
            since_id = int(await _get_cursor(conn, cursor_key) or 0)
            max_id = since_id
            for ticket in tickets:
                ticket_id = ticket.get("id")
                ar = await http.get(f"{ZAMMAD_URL}/api/v1/ticket_articles/by_ticket/{ticket_id}", headers=headers)
                if ar.status_code != 200:
                    continue
                for art in ar.json():
                    art_id = art.get("id", 0)
                    max_id = max(max_id, art_id)
                    if art_id <= since_id:
                        continue
                    if art.get("created_by_id") != principal_id:
                        continue
                    agent_id = ticket.get("owner_id")
                    emp = await _resolve_employee_by_zammad_agent(conn, agent_id)
                    if emp:
                        body = (art.get("body") or "")[:200]
                        await _record_human_event(
                            conn, emp, "ticket", f"zammad:{art_id}",
                            f"Principal commented on Zammad ticket #{ticket_id} assigned to {emp['name']}: {body}",
                        )
            if max_id > since_id:
                await _set_cursor(conn, cursor_key, max_id)


# --- Wiki.js polling ----------------------------------------------------------

async def _poll_wikijs_once(pool: asyncpg.Pool) -> None:
    async with httpx.AsyncClient(timeout=15.0) as http:
        principal_id = await _resolve_principal_wiki_id(http)
        if not principal_id:
            return
        r = await http.post(
            f"{WIKIJS_URL}/graphql",
            headers={"Authorization": f"Bearer {WIKIJS_ADMIN_TOKEN}"},
            # Wiki.js's `pages.list` PageListItem type doesn't expose authorId/tags
            # (confirmed live — only pages.single does), so list gives us candidate
            # ids+updatedAt cheaply, then we fetch full detail per-page below.
            json={"query": """
                query { pages { list(limit: 50) { id path title updatedAt } } }
            """},
        )
        if r.status_code != 200:
            log.warning("human-bridge: wikijs page list failed (%s)", r.status_code)
            return
        pages = r.json().get("data", {}).get("pages", {}).get("list", []) or []

        async with pool.acquire() as conn:
            cursor_key = "wikijs:page"
            since = await _get_cursor(conn, cursor_key)
            latest = since
            for page in pages:
                updated_at = page.get("updatedAt", "")
                if since and updated_at <= since:
                    continue
                if updated_at > latest:
                    latest = updated_at
                sr = await http.post(
                    f"{WIKIJS_URL}/graphql",
                    headers={"Authorization": f"Bearer {WIKIJS_ADMIN_TOKEN}"},
                    json={"query": "query($id: Int!) { pages { single(id: $id) { authorId tags { tag } } } }",
                          "variables": {"id": page["id"]}},
                )
                if sr.status_code != 200:
                    continue
                detail = sr.json().get("data", {}).get("pages", {}).get("single", {}) or {}
                if detail.get("authorId") != principal_id:
                    continue
                tags = [t["tag"] for t in (detail.get("tags") or [])]
                emp = await _resolve_employee_by_wiki_tag(conn, tags)
                if emp:
                    await _record_human_event(
                        conn, emp, "wiki", f"wikijs:{page['id']}:{updated_at}",
                        f"Principal edited Wiki.js page '{page['title']}' related to {emp['name']}",
                    )
            if latest and latest != since:
                await _set_cursor(conn, cursor_key, latest)


# --- Mail (IMAP) polling ------------------------------------------------------
# Original plan was to IMAP-login as the Principal (their mailbox uses the
# same derive_mail_password() scheme — confirmed: provision-principal's
# mail.create_account(PRINCIPAL_EMAIL) hits the identical MailserverClient
# path as employee accounts) and poll their Sent folder for replies. Verified
# live against the real mailserver that this does NOT work: docker-mailserver
# doesn't do sender-side archiving on SMTP submission — mail sent via raw SMTP
# (or by a real MUA that doesn't itself IMAP-APPEND a copy) never lands in the
# sender's Sent folder; that folder stays empty. So instead we poll every
# active employee's own INBOX (using that employee's already-working derived
# password — this is exactly how send_as_employee's login already works) and
# filter for messages From: the Principal's address — a reply from the
# Principal to an employee always lands in the employee's INBOX regardless of
# how it was sent. Tracked per-employee via human_bridge_cursors.

import email as email_lib
import imaplib


def _imap_fetch_inbox_from_principal(mailbox: str, last_uid: int) -> list[tuple[int, bytes]]:
    """Blocking IMAP call — always run via asyncio.to_thread."""
    password = derive_mail_password(mailbox)
    results: list[tuple[int, bytes]] = []
    conn = imaplib.IMAP4(MAILSERVER_HOST, MAILSERVER_IMAP_PORT)
    try:
        conn.login(mailbox, password)
        status, _ = conn.select("INBOX", readonly=True)
        if status != "OK":
            return results
        typ, data = conn.uid("search", None, f"UID {last_uid + 1}:*", "FROM", f'"{PRINCIPAL_EMAIL}"')
        if typ != "OK":
            return results
        uids = [int(u) for u in data[0].split()] if data and data[0] else []
        for uid in uids:
            if uid <= last_uid:
                continue
            typ, msg_data = conn.uid("fetch", str(uid), "(RFC822)")
            if typ == "OK" and msg_data and msg_data[0]:
                results.append((uid, msg_data[0][1]))
    finally:
        try:
            conn.logout()
        except Exception:
            pass
    return results


async def _poll_mail_once(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        employees = await conn.fetch(
            "SELECT * FROM employees WHERE status = 'active' AND mailbox_address IS NOT NULL"
        )

    for emp in employees:
        mailbox = emp["mailbox_address"]
        cursor_key = f"mail:{mailbox}"
        async with pool.acquire() as conn:
            last_uid = int(await _get_cursor(conn, cursor_key) or 0)

        try:
            messages = await asyncio.to_thread(_imap_fetch_inbox_from_principal, mailbox, last_uid)
        except Exception as exc:
            log.warning("human-bridge: IMAP poll failed for %s: %s", mailbox, exc)
            continue
        if not messages:
            continue

        async with pool.acquire() as conn:
            max_uid = last_uid
            for uid, raw in messages:
                max_uid = max(max_uid, uid)
                msg = email_lib.message_from_bytes(raw)
                subject = msg.get("Subject", "")
                await _record_human_event(
                    conn, emp, "email", f"mail:{mailbox}:{uid}",
                    f"Principal emailed {emp['name']}: {subject}",
                )
            await _set_cursor(conn, cursor_key, max_uid)


# --- Polling supervisor -------------------------------------------------------

async def _detection_loop(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await _ensure_detection_tables(conn)
    while True:
        for poller in (_poll_mattermost_once, _poll_zammad_once, _poll_wikijs_once, _poll_mail_once):
            try:
                await poller(pool)
            except Exception as exc:
                log.error("human-bridge: detection poller %s failed: %s", poller.__name__, exc)
        await asyncio.sleep(DETECTION_POLL_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    detection_task = asyncio.create_task(_detection_loop(_pool))
    log.info("human-bridge: ready")
    yield
    detection_task.cancel()
    try:
        await detection_task
    except (asyncio.CancelledError, Exception):
        pass
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


@app.post("/detection/poll-now")
async def detection_poll_now(pool: PoolDep):
    """Manually trigger one round of all detection pollers immediately
    (verification helper — the background loop already runs this on its own
    schedule every DETECTION_POLL_INTERVAL_SECONDS)."""
    results = {}
    for poller in (_poll_mattermost_once, _poll_zammad_once, _poll_wikijs_once, _poll_mail_once):
        try:
            await poller(pool)
            results[poller.__name__] = "ok"
        except Exception as exc:
            results[poller.__name__] = f"error: {exc}"
    return results


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
                # `customer_id` is a hard-required field on ticket creation — Zammad accepts a
                # "guess:<email>" shorthand that resolves to (or auto-creates) that customer.
                "customer_id": f"guess:{PRINCIPAL_EMAIL}",
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
