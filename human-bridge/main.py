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
import base64
import json
import logging
import os
import smtplib
import traceback
from datetime import datetime, timezone
from decimal import Decimal
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from typing import Optional

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
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

# Narrative-driven appliance content creation (Feature added alongside migration 012)
WORDPRESS_URL = os.environ.get("WORDPRESS_URL", "http://wordpress")
WORDPRESS_ADMIN_USER = os.environ.get("WORDPRESS_ADMIN_USER", "principal")
WORDPRESS_ADMIN_APP_PASSWORD = os.environ.get("WORDPRESS_ADMIN_APP_PASSWORD", "")
NEXTCLOUD_URL = os.environ.get("NEXTCLOUD_URL", "http://nextcloud")
NEXTCLOUD_ADMIN_USER = os.environ.get("NEXTCLOUD_ADMIN_USER", "admin")
NEXTCLOUD_ADMIN_PASSWORD = os.environ.get("NEXTCLOUD_ADMIN_PASSWORD", "placeholder")
LITELLM_URL = os.environ.get("LITELLM_URL", "http://litellm:4000")
LITELLM_API_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
DELIVERABLE_POLL_INTERVAL_SECONDS = float(os.environ.get("DELIVERABLE_POLL_INTERVAL_SECONDS", "30"))
DELIVERABLE_MAX_ATTEMPTS = int(os.environ.get("DELIVERABLE_MAX_ATTEMPTS", "5"))
DELIVERABLE_RETRY_BASE_SECONDS = float(os.environ.get("DELIVERABLE_RETRY_BASE_SECONDS", "30"))
DELIVERABLE_RETRY_MAX_SECONDS = float(os.environ.get("DELIVERABLE_RETRY_MAX_SECONDS", "3600"))

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

        # Revoke the ephemeral token.
        # BUG FOUND during Phase 19 verification: Mattermost has no `DELETE
        # /users/{user_id}/tokens/{token_id}` route (404s silently since this call's result was
        # never checked) — the real revoke endpoint is `POST /users/tokens/revoke` with a
        # `{"token_id": ...}` body. This means every ephemeral impersonation token created here
        # since Phase 17 has been leaking (never actually revoked). Fixed.
        token_id = r.json()["id"]
        await http.post(
            f"{MATTERMOST_URL}/api/v4/users/tokens/revoke",
            headers={"Authorization": f"Bearer {MATTERMOST_ADMIN_TOKEN}"},
            json={"token_id": token_id},
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
# Narrative-driven appliance content creation
# Feature (added with migration 012_deliverable_action_items.sql)
#
# Motivation: meeting-simulator's LLM output can flag a specific action_item
# as requiring a real artifact (deliverable_type='wordpress_post' or
# 'nextcloud_file'). This fulfillment loop picks up those items, calls LiteLLM
# to generate narrative-grounded content (using the action item description
# + thread context), and posts to the real appliance. Zero random or periodic
# content — every artifact is attributable to a specific meeting outcome.
#
# WordPress: REST API via Application Password auth (Basic Auth with
#   username:app_password, requires the mu-plugin that bypasses HTTPS-only
#   restriction — see fix_wp_app_passwords.php notes).
# Nextcloud:  WebDAV PUT to /remote.php/dav/files/{user}/{path}.
# ---------------------------------------------------------------------------

class _LLMClient:
    """Minimal LiteLLM chat client for content generation (cheap tier)."""
    def __init__(self, base_url: str, api_key: str):
        self.base = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async def chat(self, messages: list[dict], model: str = "cheap", max_tokens: int = 1500) -> str:
        async with httpx.AsyncClient(headers=self.headers, timeout=90.0) as http:
            r = await http.post(f"{self.base}/chat/completions", json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.7,
            })
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

    async def is_available(self) -> bool:
        """Return whether LiteLLM is reachable, without invoking a paid model."""
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=5.0) as http:
                r = await http.get(f"{self.base}/health/liveliness")
                return r.status_code < 500
        except httpx.HTTPError:
            return False


class _WordPressClient:
    """
    WordPress REST API client using Application Password auth.
    The Authorization header is passed as Basic auth (user:app_password).
    Application Passwords require the mu-plugin that allows them over HTTP
    (see fix_wp_app_passwords.php: wp_is_application_passwords_available filter).
    """
    def __init__(self, base_url: str, username: str, app_password: str):
        self.base = base_url.rstrip("/")
        raw = f"{username}:{app_password}"
        self._auth = "Basic " + base64.b64encode(raw.encode()).decode()
        self.headers = {"Authorization": self._auth, "Content-Type": "application/json"}

    async def create_post(self, title: str, content: str, excerpt: str = "") -> dict:
        """
        Create a published WordPress post. Returns the full post object from the
        REST API including 'id', 'link', and 'slug'.
        """
        async with httpx.AsyncClient(headers=self.headers, timeout=30.0) as http:
            r = await http.post(f"{self.base}/wp-json/wp/v2/posts", json={
                "title": title,
                "content": content,
                "excerpt": excerpt,
                "status": "publish",
            })
            r.raise_for_status()
            return r.json()


class _NextcloudClient:
    """
    Nextcloud WebDAV client for file creation.
    Uses Basic auth with the admin credentials.
    Path convention: FakeCo-Docs/{department}/{filename}.md
    """
    def __init__(self, base_url: str, username: str, password: str):
        self.dav_base = base_url.rstrip("/") + f"/remote.php/dav/files/{username}"
        raw = f"{username}:{password}"
        self._auth = "Basic " + base64.b64encode(raw.encode()).decode()
        self.headers = {"Authorization": self._auth}

    async def put_file(self, path: str, content: str) -> str:
        """
        PUT a file at {dav_base}/{path}, explicitly creating every missing
        parent collection first. WebDAV PUT does not create parent folders.
        Returns the full WebDAV URL of the created file.
        """
        clean_path = path.strip("/")
        parts = [part for part in clean_path.split("/") if part]
        if len(parts) < 2:
            raise ValueError("Nextcloud deliverable path must include a parent folder")

        url = f"{self.dav_base}/{clean_path}"
        async with httpx.AsyncClient(headers=self.headers, timeout=30.0) as http:
            for depth in range(1, len(parts)):
                collection_url = f"{self.dav_base}/{'/'.join(parts[:depth])}"
                r = await http.request("MKCOL", collection_url)
                # 201 = created; 405 = collection already exists.
                if r.status_code not in (201, 405):
                    r.raise_for_status()
            r = await http.put(url, content=content.encode("utf-8"), headers={
                **self.headers,
                "Content-Type": "text/markdown; charset=utf-8",
            })
            # WebDAV PUT returns 201 (Created) or 204 (No Content / overwrite)
            if r.status_code not in (201, 204):
                r.raise_for_status()
        return url


async def _generate_content_for_action_item(
    llm: _LLMClient,
    action_description: str,
    thread_summary: str,
    employee_name: str,
    deliverable_type: str,
    sim_time: datetime,
) -> dict:
    """
    Call LiteLLM to generate narrative-grounded content for a deliverable action
    item. Returns {"title": str, "content": str, "excerpt": str}.
    Content is derived from the action item's description and thread context,
    NOT randomly generated — the LLM has explicit context to work from.
    """
    if deliverable_type == "wordpress_post":
        format_instructions = (
            "Write a professional, publishable company blog post or news announcement "
            "for FakeCo's public-facing website. Use plain text with simple paragraph "
            "breaks (no markdown headers). Length: 3–4 paragraphs. Tone: professional "
            "but approachable. Do NOT invent facts — only use what is in the context below."
        )
    else:  # nextcloud_file
        format_instructions = (
            "Write an internal business document in Markdown format. Use headers (##), "
            "bullet lists, and a clear structure. Length: 4–6 sections. Tone: professional, "
            "concise, direct. Do NOT invent facts — only use what is in the context below."
        )

    system_msg = (
        f"You are a content writer at FakeCo, a B2B software company. "
        f"The simulation date is {sim_time.strftime('%B %d, %Y')}.\n"
        f"Your job is to produce real business content based on actual events — never filler text."
    )
    user_msg = (
        f"The following action item was assigned to {employee_name} as an outcome of a FakeCo meeting:\n"
        f"Action: {action_description}\n\n"
        f"Narrative context (meeting thread summary): {thread_summary or 'No additional context.'}\n\n"
        f"{format_instructions}\n\n"
        f"Respond with a JSON object containing:\n"
        f"  title: short, descriptive title (max 80 chars)\n"
        f"  content: the full document/post body\n"
        f"  excerpt: one-sentence summary (for WordPress excerpt / Nextcloud metadata)\n"
        f"Respond with ONLY valid JSON, no markdown fences."
    )
    messages = [{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}]

    def parse_and_validate(raw: str) -> dict:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[1:])
        if cleaned.endswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[:-1])
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("LLM response is not a JSON object")
        title = str(parsed.get("title") or "").strip()
        content = str(parsed.get("content") or "").strip()
        excerpt = str(parsed.get("excerpt") or "").strip()
        if not title:
            raise ValueError("generated title is empty")
        if len(content) < 120:
            raise ValueError(f"generated content is too short ({len(content)} chars)")
        if not excerpt:
            raise ValueError("generated excerpt is empty")
        return {"title": title[:80], "content": content, "excerpt": excerpt}

    first_error: Optional[Exception] = None
    for attempt in range(2):
        raw = await llm.chat(messages=messages, model="cheap", max_tokens=1200 if attempt == 0 else 1800)
        try:
            return parse_and_validate(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            if attempt == 1:
                raise ValueError(f"LLM returned invalid deliverable content twice: {exc}") from exc
            first_error = exc
            log.warning("human-bridge: invalid generated deliverable (%s); retrying once", exc)
            messages.extend([
                {"role": "assistant", "content": raw},
                {"role": "user", "content": (
                    "The response was unusable because it was invalid JSON or had empty/too-short fields. "
                    "Return the complete deliverable again as ONLY valid JSON. Ensure title and excerpt "
                    "are non-empty and content contains the full requested document."
                )},
            ])
    raise ValueError(f"Could not generate valid deliverable content: {first_error}")


async def _record_deliverable_failure(
    conn: asyncpg.Connection,
    item_id: int,
    error: Exception,
) -> None:
    """Persist exponential backoff and terminal failure state for one item."""
    row = await conn.fetchrow(
        "SELECT deliverable_attempts FROM action_items WHERE id = $1 FOR UPDATE", item_id
    )
    attempts = int(row["deliverable_attempts"] if row else 0) + 1
    terminal = attempts >= DELIVERABLE_MAX_ATTEMPTS
    delay = min(
        DELIVERABLE_RETRY_BASE_SECONDS * (2 ** max(0, attempts - 1)),
        DELIVERABLE_RETRY_MAX_SECONDS,
    )
    error_text = f"{type(error).__name__}: {error}"[:2000]
    await conn.execute("""
        UPDATE action_items
        SET deliverable_attempts = $2,
            deliverable_last_error = $3,
            deliverable_next_retry_at = CASE
                WHEN $4 THEN NULL
                ELSE NOW() + ($5 * INTERVAL '1 second')
            END,
            deliverable_failed_at = CASE WHEN $4 THEN NOW() ELSE NULL END,
            status = CASE WHEN $4 THEN 'failed' ELSE status END
        WHERE id = $1
    """, item_id, attempts, error_text, terminal, delay)
    if terminal:
        log.error(
            "human-bridge: action_item %d permanently failed after %d attempts: %s",
            item_id, attempts, error_text,
        )
    else:
        log.warning(
            "human-bridge: action_item %d failed attempt %d/%d; retrying in %.0fs: %s",
            item_id, attempts, DELIVERABLE_MAX_ATTEMPTS, delay, error_text,
        )


async def _fulfill_one_deliverable(
    conn: asyncpg.Connection,
    row: asyncpg.Record,
    llm: _LLMClient,
    wp: _WordPressClient,
    nc: _NextcloudClient,
    sim_time: datetime,
) -> bool:
    """
    Fulfill a single open action_item with a non-null deliverable_type.
    Steps:
      1. Fetch context (thread summary, employee name).
      2. Call LiteLLM to generate narrative content from that context.
      3. POST to WordPress or PUT to Nextcloud.
      4. Mark action_item done, write deliverable_url + fulfilled_at.
      5. Insert a narrative_event(origin='ai', source_type='wiki'/'external')
         so the fulfillment is traceable in the narrative backlog.
      6. Write a system_audit_log entry.
    All side effects happen in a single logical sequence; if the appliance call
    fails the action_item row is left open so the next poll cycle retries.
    """
    item_id: int = row["id"]
    description: str = row["description"]
    deliverable_type: str = row["deliverable_type"]
    thread_id = row["thread_id"]
    owner_id = row["owner_employee_id"]

    # 1. Fetch context
    thread = await conn.fetchrow(
        "SELECT summary, topic, department FROM narrative_threads WHERE id = $1", thread_id
    ) if thread_id else None
    thread_summary = (thread["summary"] or thread["topic"] if thread else "") or ""

    employee = await conn.fetchrow(
        "SELECT name, department FROM employees WHERE id = $1", owner_id
    )
    employee_name = employee["name"] if employee else "Unknown"
    department = (employee["department"] if employee else None) or "General"

    # 2. Generate content via LLM
    try:
        generated = await _generate_content_for_action_item(
            llm=llm,
            action_description=description,
            thread_summary=thread_summary,
            employee_name=employee_name,
            deliverable_type=deliverable_type,
            sim_time=sim_time,
        )
    except Exception as exc:
        log.error("human-bridge: LLM content generation failed for action_item %d: %s", item_id, exc)
        await _record_deliverable_failure(conn, item_id, exc)
        return False

    title = generated["title"]
    content = generated["content"]
    excerpt = generated["excerpt"]
    deliverable_url: Optional[str] = None

    # 3. Post to the real appliance
    try:
        if deliverable_type == "wordpress_post":
            post = await wp.create_post(title=title, content=content, excerpt=excerpt)
            # The 'link' field is the public-facing URL for this post
            deliverable_url = post.get("link") or f"{WORDPRESS_URL}/wp-json/wp/v2/posts/{post.get('id')}"
            log.info(
                "human-bridge: published WordPress post '%s' (id=%s) for action_item %d",
                title, post.get("id"), item_id,
            )
        elif deliverable_type == "nextcloud_file":
            # Path: FakeCo-Docs/{department}/{sim_date}-{item_id}-{slug}.md
            safe_title = title[:50].replace(" ", "-").replace("/", "-")
            nc_path = (
                f"FakeCo-Docs/{department}/"
                f"{sim_time.strftime('%Y-%m-%d')}-ai-{item_id}-{safe_title}.md"
            )
            # Prepend a YAML front matter block for metadata
            file_content = (
                f"---\n"
                f"title: {title}\n"
                f"author: {employee_name}\n"
                f"date: {sim_time.strftime('%Y-%m-%d')}\n"
                f"context: action_item:{item_id}\n"
                f"thread_id: {thread_id or 'n/a'}\n"
                f"---\n\n"
                f"{content}"
            )
            deliverable_url = await nc.put_file(nc_path, file_content)
            log.info(
                "human-bridge: created Nextcloud file '%s' for action_item %d",
                nc_path, item_id,
            )
    except Exception as exc:
        log.error(
            "human-bridge: appliance call failed for action_item %d (%s): %s",
            item_id, deliverable_type, exc,
        )
        await _record_deliverable_failure(conn, item_id, exc)
        return False

    # 4. Mark done, write deliverable_url and fulfilled_at
    await conn.execute("""
        UPDATE action_items
        SET status = 'done',
            deliverable_url = $2,
            deliverable_fulfilled_at = $3,
            deliverable_last_error = NULL,
            deliverable_next_retry_at = NULL,
            deliverable_failed_at = NULL
        WHERE id = $1
    """, item_id, deliverable_url, datetime.now(timezone.utc))

    # 5. narrative_event so the fulfillment appears in the thread timeline
    source_type = "wiki" if deliverable_type == "nextcloud_file" else "external"
    await conn.execute("""
        INSERT INTO narrative_events
            (thread_id, employee_id, origin, source_type, source_ref, short_summary, created_at)
        VALUES ($1, $2, 'ai', $3, $4, $5, $6)
    """,
        thread_id, owner_id,
        source_type,
        f"{deliverable_type}:action_item:{item_id}",
        f"{employee_name} fulfilled deliverable: '{title}' "
        f"({deliverable_type.replace('_', ' ')}) — {excerpt[:200]}",
        sim_time,
    )

    # 6. system_audit_log
    await audit_log(conn, "human-bridge", "deliverable_fulfilled", {
        "action_item_id": item_id,
        "deliverable_type": deliverable_type,
        "deliverable_url": deliverable_url,
        "title": title,
        "thread_id": thread_id,
        "employee_id": owner_id,
    })
    return True


async def _deliverable_fulfillment_loop(pool: asyncpg.Pool) -> None:
    """
    Background loop: polls for open action_items with deliverable_type set,
    generates narrative content via LiteLLM, and posts to WordPress or Nextcloud.

    Design invariants:
    - Only acts on action_items that have deliverable_type != NULL (set by
      meeting-simulator based on explicit LLM output requesting a document).
    - Every piece of content is grounded in that action item's description +
      thread context — no random or periodic content generation.
    - Failures use persistent exponential backoff and become terminal after
      DELIVERABLE_MAX_ATTEMPTS; no item can retry every poll forever.
    - Skips items with deliverable_url already set (already fulfilled).
    """
    # Allow a startup grace period before the first poll
    await asyncio.sleep(15.0)

    if not WORDPRESS_ADMIN_APP_PASSWORD:
        log.warning(
            "human-bridge: WORDPRESS_ADMIN_APP_PASSWORD not set — "
            "deliverable fulfillment loop will skip wordpress_post items"
        )
    if not LITELLM_API_KEY:
        log.warning(
            "human-bridge: LITELLM_MASTER_KEY not set — "
            "deliverable fulfillment loop will not generate content"
        )

    llm = _LLMClient(LITELLM_URL, LITELLM_API_KEY)
    wp  = _WordPressClient(WORDPRESS_URL, WORDPRESS_ADMIN_USER, WORDPRESS_ADMIN_APP_PASSWORD)
    nc  = _NextcloudClient(NEXTCLOUD_URL, NEXTCLOUD_ADMIN_USER, NEXTCLOUD_ADMIN_PASSWORD)

    log.info(
        "human-bridge: deliverable fulfillment loop started (interval=%.0fs)",
        DELIVERABLE_POLL_INTERVAL_SECONDS,
    )

    while True:
        try:
            # A deliberately stopped LiteLLM pauses fulfillment without consuming
            # item retry attempts. Retry state is reserved for actual generation
            # or appliance failures, not operator-controlled provider downtime.
            if not await llm.is_available():
                log.info("human-bridge: LiteLLM unavailable; deliverable fulfillment paused")
                await asyncio.sleep(DELIVERABLE_POLL_INTERVAL_SECONDS)
                continue
            async with pool.acquire() as conn:
                # Fetch open deliverable action_items that haven't been fulfilled yet.
                # The deliverable_url IS NULL guard prevents re-processing items that
                # were previously fulfilled but for some reason still have status='open'.
                rows = await conn.fetch("""
                    SELECT id, description, deliverable_type, thread_id, owner_employee_id
                    FROM action_items
                    WHERE deliverable_type IS NOT NULL
                      AND status = 'open'
                      AND deliverable_url IS NULL
                      AND COALESCE(deliverable_next_retry_at, NOW()) <= NOW()
                    ORDER BY id
                    LIMIT 10
                """)

            if rows:
                log.info(
                    "human-bridge: deliverable loop found %d pending item(s)", len(rows)
                )
                # Fetch sim time once per poll cycle (saves one HTTP call per item)
                try:
                    sim_time_resp = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: __import__('urllib.request', fromlist=['urlopen']).urlopen(
                            "http://sim-clock:8000/sim_time", timeout=5
                        ).read()
                    )
                    sim_time = datetime.fromisoformat(
                        json.loads(sim_time_resp)["sim_time"]
                    )
                except Exception:
                    sim_time = datetime.now(timezone.utc)

                for row in rows:
                    try:
                        async with pool.acquire() as conn:
                            await _fulfill_one_deliverable(conn, row, llm, wp, nc, sim_time)
                    except Exception as exc:
                        log.error(
                            "human-bridge: deliverable fulfillment error for item %d: %s",
                            row["id"], exc,
                        )
        except Exception as exc:
            log.error("human-bridge: deliverable fulfillment loop error: %s", exc)

        await asyncio.sleep(DELIVERABLE_POLL_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    detection_task = asyncio.create_task(_detection_loop(_pool))
    # Deliverable fulfillment: polls open action_items with deliverable_type set
    # and creates real WordPress posts / Nextcloud files via LLM-generated content.
    deliverable_task = asyncio.create_task(_deliverable_fulfillment_loop(_pool))
    log.info("human-bridge: ready")
    yield
    detection_task.cancel()
    deliverable_task.cancel()
    try:
        await detection_task
    except (asyncio.CancelledError, Exception):
        pass
    try:
        await deliverable_task
    except (asyncio.CancelledError, Exception):
        pass
    await _pool.close()


app = FastAPI(
    title="FakeCo Human Bridge",
    description="Principal control panel backend — inject actions into the simulation as any employee.",
    version="1.0.0",
    lifespan=lifespan,
)


# Bug fix (2026-08-01): uncaught ASGI/Starlette-level 500s previously logged
# as plaintext uvicorn traceback lines that promtail's `level` extraction
# can't parse, so real unhandled crashes were invisible to the Errors panel.
# This handler re-logs any otherwise-unhandled exception via the app's own
# JSON logger (same format/level label as every other log line) before
# returning a 500. HTTPException is matched by FastAPI's own default
# handler first (exact-class lookup in Starlette's exception middleware),
# so explicit 4xx/5xx responses are unaffected and not double-logged here.
@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc().replace("\n", " | ").replace('"', "'")
    log.error(
        "Unhandled exception on %s %s: %s: %s | %s",
        request.method, request.url.path, type(exc).__name__, exc, tb,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


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


COMPANY_DIRECTIVE_WIKI_PATH = os.environ.get("COMPANY_DIRECTIVE_WIKI_PATH", "company-direction")


async def _sync_directive_to_wikijs(content: str, version: int) -> dict:
    """
    Phase 35: pinned Wiki.js page sync for company_directives, previously a TODO
    left by this same endpoint (see the old docstring). Real create-or-update:
    list pages to find an existing page at COMPANY_DIRECTIVE_WIKI_PATH, then
    `pages.update` if found, `pages.create` otherwise. `pages.update` needs
    nearly the full field set even when only content/description changes
    (important.md gotcha #3) — send them all every time.
    """
    headers = {"Authorization": f"Bearer {WIKIJS_ADMIN_TOKEN}", "Content-Type": "application/json"}
    title = "Company Direction"
    description = f"Current company directive (version {version}) — synced from the dashboard."
    async with httpx.AsyncClient(timeout=30.0) as http:
        # `pages.list` takes no reliable path-filter arg across Wiki.js versions
        # (unlike `pages.single(id)`) — fetch the full list and filter client-side,
        # same approach kpi-engine's WikiJSClient uses (small page count, cheap).
        list_resp = await http.post(f"{WIKIJS_URL}/graphql", headers=headers, json={
            "query": "{ pages { list { id path } } }"
        })
        list_resp.raise_for_status()
        pages = ((list_resp.json().get("data") or {}).get("pages") or {}).get("list") or []
        existing = next((p for p in pages if p["path"] == COMPANY_DIRECTIVE_WIKI_PATH), None)

        if existing:
            r = await http.post(f"{WIKIJS_URL}/graphql", headers=headers, json={
                "query": """
                    mutation($id: Int!, $content: String!, $description: String!, $editor: String!,
                             $isPrivate: Boolean!, $isPublished: Boolean!, $locale: String!,
                             $path: String!, $tags: [String]!, $title: String!) {
                        pages {
                            update(id: $id, content: $content, description: $description, editor: $editor,
                                   isPrivate: $isPrivate, isPublished: $isPublished, locale: $locale,
                                   path: $path, tags: $tags, title: $title) {
                                responseResult { succeeded errorCode message }
                            }
                        }
                    }
                """,
                "variables": {
                    "id": existing["id"], "content": content, "description": description,
                    "editor": "markdown", "isPrivate": False, "isPublished": True,
                    "locale": "en", "path": COMPANY_DIRECTIVE_WIKI_PATH, "tags": ["company-direction", "pinned"],
                    "title": title,
                },
            })
        else:
            r = await http.post(f"{WIKIJS_URL}/graphql", headers=headers, json={
                "query": """
                    mutation($content: String!, $description: String!, $editor: String!, $isPrivate: Boolean!,
                             $isPublished: Boolean!, $locale: String!, $path: String!, $tags: [String]!, $title: String!) {
                        pages {
                            create(content: $content, description: $description, editor: $editor,
                                   isPrivate: $isPrivate, isPublished: $isPublished, locale: $locale,
                                   path: $path, tags: $tags, title: $title) {
                                responseResult { succeeded errorCode message }
                                page { id path }
                            }
                        }
                    }
                """,
                "variables": {
                    "content": content, "description": description, "editor": "markdown",
                    "isPrivate": False, "isPublished": True, "locale": "en", "path": COMPANY_DIRECTIVE_WIKI_PATH,
                    "tags": ["company-direction", "pinned"], "title": title,
                },
            })
        r.raise_for_status()
        return r.json()


@app.post("/action/update-directive")
async def action_update_directive(req: UpdateDirectiveRequest, pool: PoolDep):
    """
    Update the company directive. Previous version marked is_current=FALSE.
    Spec §8: directive synced to a pinned Wiki.js page — Phase 35 implements the
    sync for real (previously a TODO left here since Phase 17/30).
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

    wiki_sync_error = None
    try:
        await _sync_directive_to_wikijs(req.content, new_version)
    except Exception as exc:
        # Wiki.js sync failure should not roll back the directive update itself
        # (the Postgres row is the source of truth) — surface the error to the
        # caller instead so the dashboard can show it, but don't fail the save.
        wiki_sync_error = str(exc)
        log.error("Wiki.js sync failed for directive v%d: %s", new_version, exc)

    return {
        "status": "updated",
        "version": new_version,
        "directive_id": directive_id,
        "wiki_sync_error": wiki_sync_error,
    }


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


@app.post("/action/deliverables/poll-now")
async def action_poll_deliverables_now(pool: PoolDep):
    """Manually trigger a single fulfillment check of all open deliverable action items."""
    if not WORDPRESS_ADMIN_APP_PASSWORD:
        log.warning("WordPress admin application password is not set.")
    
    llm = _LLMClient(LITELLM_URL, LITELLM_API_KEY)
    wp  = _WordPressClient(WORDPRESS_URL, WORDPRESS_ADMIN_USER, WORDPRESS_ADMIN_APP_PASSWORD)
    nc  = _NextcloudClient(NEXTCLOUD_URL, NEXTCLOUD_ADMIN_USER, NEXTCLOUD_ADMIN_PASSWORD)
    if not await llm.is_available():
        raise HTTPException(
            status_code=503,
            detail="LiteLLM is unavailable; deliverable retry state was not changed",
        )
    
    # Fetch sim time
    try:
        sim_time_resp = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: __import__('urllib.request', fromlist=['urlopen']).urlopen(
                "http://sim-clock:8000/sim_time", timeout=5
            ).read()
        )
        sim_time = datetime.fromisoformat(json.loads(sim_time_resp)["sim_time"])
    except Exception:
        sim_time = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, description, deliverable_type, thread_id, owner_employee_id
            FROM action_items
            WHERE deliverable_type IS NOT NULL
              AND status = 'open'
              AND deliverable_url IS NULL
              AND COALESCE(deliverable_next_retry_at, NOW()) <= NOW()
            ORDER BY id
        """)
        
        fulfilled_count = 0
        for row in rows:
            try:
                # Runs each fulfillment in its own transaction context
                async with conn.transaction():
                    fulfilled = await _fulfill_one_deliverable(conn, row, llm, wp, nc, sim_time)
                if fulfilled:
                    fulfilled_count += 1
            except Exception as exc:
                log.error("human-bridge: manual poll fulfillment failed for action_item %d: %s", row["id"], exc)

    return {"status": "ok", "found": len(rows), "fulfilled": fulfilled_count}


@app.get("/action/deliverables/pending")
async def action_get_pending_deliverables(pool: PoolDep):
    """Get all open action items requiring a deliverable that have not been fulfilled yet."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, meeting_id, thread_id, owner_employee_id, description, due_at, status,
                   deliverable_type, deliverable_attempts, deliverable_next_retry_at,
                   deliverable_last_error, deliverable_failed_at
            FROM action_items
            WHERE deliverable_type IS NOT NULL
              AND status IN ('open', 'failed')
              AND deliverable_url IS NULL
            ORDER BY id
        """)
        return [dict(r) for r in rows]

