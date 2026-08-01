"""
dashboard/main.py — FakeCo "Real Appliances"
Phase 33: Control Dashboard — shell + Simulation / LLM Status / Narrative tabs.

This is a thin FastAPI backend-for-frontend (BFF): it serves the built React/Vite
static bundle and exposes a small set of aggregation endpoints per tab, proxying
to each owning service's existing API rather than duplicating business logic
(per PLAN_PHASES_33_38_DASHBOARD.md §1).

2026-08-01 sign-off: the ENTIRE dashboard (API + static SPA) sits behind HTTP
Basic Auth from this phase onward — a single Principal user/password read from
DASHBOARD_AUTH_USER / DASHBOARD_AUTH_PASSWORD (no default — required to be set,
matching this repo's existing convention for other required secrets, e.g.
LITELLM_MASTER_KEY's `:?` compose syntax).
"""
import asyncio
import json
import logging
import os
import secrets
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import asyncpg
import aiomysql
import httpx
import yaml
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi import Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from decimal import Decimal

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","service":"dashboard","msg":"%(message)s"}'
)
log = logging.getLogger("dashboard")

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
SIM_CLOCK_URL = os.environ.get("SIM_CLOCK_URL", "http://sim-clock:8000")
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8000")
LITELLM_CONFIG_PATH = os.environ.get("LITELLM_CONFIG_PATH", "/litellm-config/config.yaml")
# Phase 34: HR tab's Fire/Hire proxies to provisioning's new HTTP endpoints
# (provisioning was CLI-only through Phase 14 — see provisioning/main.py's
# "serve" mode). Payroll/Accounting tabs proxy to accounting-engine's existing
# (and two new Phase 34) endpoints. Both services already share net_clients/
# net_data with this container, so no new network/compose wiring was needed.
PROVISIONING_URL = os.environ.get("PROVISIONING_URL", "http://provisioning:8000")
ACCOUNTING_ENGINE_URL = os.environ.get("ACCOUNTING_ENGINE_URL", "http://accounting-engine:8000")
# Static deep link — Akaunting's own SPA routes reports under /{company_id}/reports/...;
# resolved via the browser's own DNS (Technitium, already configured for other appliances)
# against the Traefik-routed hostname, matching every other deep-link pattern in this repo.
AKAUNTING_COMPANY_ID = os.environ.get("AKAUNTING_COMPANY_ID", "1")
AKAUNTING_PUBLIC_URL = os.environ.get("AKAUNTING_PUBLIC_URL", "http://accounting.fakecorp.internal")

# Phase 35: External World / KPI / Company Direction tabs.
EXTERNAL_WORLD_URL = os.environ.get("EXTERNAL_WORLD_URL", "http://external-world:8000")
KPI_ENGINE_URL = os.environ.get("KPI_ENGINE_URL", "http://kpi-engine:8000")
HUMAN_BRIDGE_URL = os.environ.get("HUMAN_BRIDGE_URL", "http://human-bridge:8000")

# Phase 36: Chaos / Data Management / Branding tabs + Settings' full-purge
# "nuclear launch" flow. All three owning services already exist (Phases
# 27/28/29/30) — this BFF only proxies to their existing endpoints, per the
# plan's "reuse, don't duplicate" pattern used everywhere else in this file.
PURGE_MANAGER_URL = os.environ.get("PURGE_MANAGER_URL", "http://purge-manager:8000")
SNAPSHOT_MANAGER_URL = os.environ.get("SNAPSHOT_MANAGER_URL", "http://snapshot-manager:8000")
BRANDING_MANAGER_URL = os.environ.get("BRANDING_MANAGER_URL", "http://branding-manager:8000")
# The exact typed-confirmation phrases live server-side in purge-manager
# (SCOPE_PHRASES / FULL_PURGE_PHRASE) — mirrored here ONLY for the UI to show
# the user what to type; the BFF and purge-manager both still validate the
# real value server-side, this is not a client-trusted shortcut.
DATA_MANAGEMENT_SCOPES = [
    {"scope": "emails", "label": "Emails", "confirm_phrase": "PURGE EMAILS"},
    {"scope": "chat", "label": "Chat", "confirm_phrase": "PURGE CHAT"},
    {"scope": "tickets", "label": "Tickets", "confirm_phrase": "PURGE TICKETS"},
    {"scope": "wiki", "label": "Wiki", "confirm_phrase": "PURGE WIKI"},
    {"scope": "meetings_narrative", "label": "Meetings & narrative memory",
     "confirm_phrase": "PURGE MEETINGS AND NARRATIVE MEMORY"},
    {"scope": "accounting", "label": "Accounting ledger", "confirm_phrase": "PURGE ACCOUNTING LEDGER"},
    {"scope": "external_world", "label": "External world", "confirm_phrase": "PURGE EXTERNAL WORLD"},
    {"scope": "kpi_history", "label": "KPI history", "confirm_phrase": "PURGE KPI HISTORY"},
    {"scope": "roster", "label": "Roster", "confirm_phrase": "PURGE ROSTER"},
    {"scope": "company_direction", "label": "Company direction", "confirm_phrase": "PURGE COMPANY DIRECTION"},
]
FULL_PURGE_CONFIRM_PHRASE = "PURGE EVERYTHING"

# Revenue-by-customer chart reads Akaunting's MariaDB directly, same
# credentials/host purge-manager and snapshot-manager already use.
AKAUNTING_DB_HOST = os.environ.get("AKAUNTING_DB_HOST", "akaunting-db")
AKAUNTING_DB_NAME = os.environ.get("AKAUNTING_DB_NAME", "akaunting")
AKAUNTING_DB_USER = os.environ.get("AKAUNTING_DB_USER", "akaunting")
AKAUNTING_DB_PASSWORD = os.environ.get("AKAUNTING_DB_PASSWORD", "")

DASHBOARD_AUTH_USER = os.environ.get("DASHBOARD_AUTH_USER")
DASHBOARD_AUTH_PASSWORD = os.environ.get("DASHBOARD_AUTH_PASSWORD")

# Phase 37: TV wall (chat/ticket feeds), Errors panel + log tail (Loki proxy),
# Deep Links panel.
LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
MATTERMOST_URL = os.environ.get("MATTERMOST_URL", "http://mattermost:8065")
MATTERMOST_ADMIN_TOKEN = os.environ.get("MATTERMOST_ADMIN_TOKEN", "")
MATTERMOST_TEAM_ID = os.environ.get("MATTERMOST_TEAM_ID", "")
ZAMMAD_URL = os.environ.get("ZAMMAD_URL", "http://zammad-nginx:8080")
ZAMMAD_ADMIN_TOKEN = os.environ.get("ZAMMAD_ADMIN_TOKEN", "")

# Every custom service container the Errors panel covers (spec §25's
# Errors-panel line, verbatim list).
ERROR_PANEL_SERVICES = [
    "fakeco-accounting-engine", "fakeco-meeting-simulator", "fakeco-human-bridge",
    "fakeco-orchestrator", "fakeco-external-world", "fakeco-kpi-engine",
    "fakeco-branding-manager", "fakeco-snapshot-manager", "fakeco-purge-manager",
]

# Deep Links panel (2026-08-01 sign-off, amended — no iframe embedding, direct
# links + visible Principal credentials only). Each entry's user/password is
# read from .env at boot, reusing exactly the same env vars every earlier
# phase already uses for that appliance's Principal/admin credential — no new
# secrets minted here. Wiki.js's admin account IS the Principal's own account
# (WIKIJS_ADMIN_EMAIL == PRINCIPAL_EMAIL, per provisioning/main.py's
# provision-principal command). Roundcube has no stored password in .env at
# all — its mailbox password is deterministically derived from
# MAILSERVER_BOT_SECRET, the exact same derivation
# provisioning/main.py's MailClient._derive_password() already uses to create
# the Principal's own mailbox — reproduced here (not a new secret) so the
# panel can show the real, working password rather than a placeholder.
PRINCIPAL_EMAIL = os.environ.get("PRINCIPAL_EMAIL", "principal@fakecorp.internal")
MAILSERVER_BOT_SECRET = os.environ.get("MAILSERVER_BOT_SECRET", "fakeco-bot-mail-secret-change-me")


def _derive_mailbox_password(email: str) -> str:
    import hashlib
    return hashlib.sha256(f"{MAILSERVER_BOT_SECRET}:{email}".encode()).hexdigest()[:24]


def _build_deep_links() -> list[dict]:
    return [
        {
            "name": "Mattermost",
            "url": "http://chat.fakecorp.internal/login",
            "username": os.environ.get("MATTERMOST_ADMIN_EMAIL") or os.environ.get("MATTERMOST_ADMIN_USER", ""),
            "password": os.environ.get("MATTERMOST_ADMIN_PASSWORD", ""),
        },
        {
            "name": "Zammad",
            "url": "http://tickets.fakecorp.internal/#login",
            "username": os.environ.get("ZAMMAD_ADMIN_EMAIL", ""),
            "password": os.environ.get("ZAMMAD_ADMIN_PASSWORD", ""),
        },
        {
            "name": "Wiki.js",
            "url": "http://wiki.fakecorp.internal/login",
            "username": os.environ.get("WIKIJS_ADMIN_EMAIL", PRINCIPAL_EMAIL),
            "password": os.environ.get("WIKIJS_ADMIN_PASSWORD", ""),
        },
        {
            "name": "Nextcloud",
            "url": "http://portal.fakecorp.internal/login",
            "username": os.environ.get("NEXTCLOUD_ADMIN_USER", "admin"),
            "password": os.environ.get("NEXTCLOUD_ADMIN_PASSWORD", ""),
        },
        {
            "name": "WordPress",
            "url": "http://www.fakecorp.internal/wp-login.php",
            "username": os.environ.get("WORDPRESS_ADMIN_USER", ""),
            "password": os.environ.get("WORDPRESS_ADMIN_PASSWORD", ""),
        },
        {
            "name": "Akaunting",
            "url": "http://accounting.fakecorp.internal/auth/login",
            "username": os.environ.get("AKAUNTING_ADMIN_EMAIL", ""),
            "password": os.environ.get("AKAUNTING_ADMIN_PASSWORD", ""),
        },
        {
            "name": "Roundcube",
            "url": "http://mail.fakecorp.internal",
            "username": PRINCIPAL_EMAIL,
            "password": _derive_mailbox_password(PRINCIPAL_EMAIL),
        },
        {
            "name": "Grafana",
            "url": "http://grafana.fakecorp.internal:3000/login",
            "username": os.environ.get("GRAFANA_ADMIN_USER", "admin"),
            "password": os.environ.get("GRAFANA_ADMIN_PASSWORD", ""),
        },
    ]

STATIC_DIR = Path(__file__).parent / "static"

# ---------------------------------------------------------------------------
# HTTP Basic Auth — protects EVERY route (API + static SPA), per 2026-08-01
# sign-off. No default credentials are baked in; if the env vars aren't set,
# the service refuses all requests (fails safe, not open).
# ---------------------------------------------------------------------------
_security = HTTPBasic()


def require_basic_auth(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    if not DASHBOARD_AUTH_USER or not DASHBOARD_AUTH_PASSWORD:
        # Fail safe: refuse to serve anything rather than silently allowing
        # unauthenticated access because an operator forgot to set the env vars.
        raise HTTPException(
            status_code=503,
            detail="Dashboard auth is not configured — set DASHBOARD_AUTH_USER and "
                   "DASHBOARD_AUTH_PASSWORD in .env before starting this service.",
        )
    user_ok = secrets.compare_digest(credentials.username, DASHBOARD_AUTH_USER)
    pass_ok = secrets.compare_digest(credentials.password, DASHBOARD_AUTH_PASSWORD)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ---------------------------------------------------------------------------
# Shared DB pool + HTTP client
# ---------------------------------------------------------------------------
_pool: Optional[asyncpg.Pool] = None
_http: Optional[httpx.AsyncClient] = None
_mysql_pool: Optional[aiomysql.Pool] = None


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Pool not initialized")
    return _pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _http, _mysql_pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=5)
    _http = httpx.AsyncClient(timeout=15.0)
    try:
        _mysql_pool = await aiomysql.create_pool(
            host=AKAUNTING_DB_HOST, port=3306, user=AKAUNTING_DB_USER,
            password=AKAUNTING_DB_PASSWORD, db=AKAUNTING_DB_NAME,
            minsize=1, maxsize=3, autocommit=True,
        )
    except Exception as exc:
        # Same degrade-gracefully posture as every other optional integration
        # here — the External World tab's revenue-by-customer chart will show
        # an error banner rather than crash the whole BFF at boot.
        log.warning("Could not connect to Akaunting MariaDB at boot: %s", exc)
        _mysql_pool = None
    if not DASHBOARD_AUTH_USER or not DASHBOARD_AUTH_PASSWORD:
        log.warning(
            "DASHBOARD_AUTH_USER / DASHBOARD_AUTH_PASSWORD not set — dashboard will "
            "refuse all requests (503) until both are configured."
        )
    log.info("dashboard: service ready")
    yield
    await _http.aclose()
    await _pool.close()
    if _mysql_pool is not None:
        _mysql_pool.close()
        await _mysql_pool.wait_closed()
    log.info("dashboard: shutdown complete")


app = FastAPI(
    title="FakeCo Control Dashboard",
    description="Phase 33: shell + Simulation / LLM Status / Narrative tabs.",
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


# /health is intentionally NOT behind auth — Docker's own healthcheck (run
# inside the container, never reaches the browser/network) needs to hit it
# unauthenticated, matching every other custom service's pattern in this repo.
@app.get("/health")
async def health():
    return {"status": "ok", "service": "dashboard"}


# ---------------------------------------------------------------------------
# Simulation tab
# ---------------------------------------------------------------------------
@app.get("/api/simulation/status")
async def simulation_status(_user: str = Depends(require_basic_auth)):
    """Sim-time + speed (live from sim-clock) and tick-loop pause state (live
    from orchestrator's Phase 33 /tick/status endpoint)."""
    result = {"sim_clock": None, "sim_clock_error": None, "tick": None, "tick_error": None}
    try:
        r = await _http.get(f"{SIM_CLOCK_URL}/clock", timeout=10.0)
        r.raise_for_status()
        result["sim_clock"] = r.json()
    except Exception as exc:
        result["sim_clock_error"] = str(exc)

    try:
        r = await _http.get(f"{ORCHESTRATOR_URL}/tick/status", timeout=10.0)
        r.raise_for_status()
        result["tick"] = r.json()
    except Exception as exc:
        result["tick_error"] = str(exc)

    return result


@app.post("/api/simulation/tick/pause")
async def simulation_tick_pause(_user: str = Depends(require_basic_auth)):
    try:
        r = await _http.post(f"{ORCHESTRATOR_URL}/tick/pause", timeout=10.0)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"orchestrator unreachable: {exc}")


@app.post("/api/simulation/tick/resume")
async def simulation_tick_resume(_user: str = Depends(require_basic_auth)):
    try:
        r = await _http.post(f"{ORCHESTRATOR_URL}/tick/resume", timeout=10.0)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"orchestrator unreachable: {exc}")


# ---------------------------------------------------------------------------
# LLM Status tab
#
# Provider/fallback chain: parsed from the same litellm/config.yaml the
# litellm container mounts (no live config-introspection endpoint proven to
# exist without extra API-key plumbing — parsing the mounted file is the
# plan's own documented fallback). Usage/cost: reuses the EXACT SQL from
# Phase 31's monitoring/grafana/dashboards/llm-spend.json panel, verbatim,
# against the same LiteLLM_SpendLogs table in the shared Postgres instance.
# ---------------------------------------------------------------------------
def _parse_litellm_config() -> dict:
    try:
        with open(LITELLM_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except Exception as exc:
        return {"error": f"could not read litellm config at {LITELLM_CONFIG_PATH}: {exc}"}

    model_list = cfg.get("model_list", []) or []
    tiers: dict[str, list[str]] = {}
    for entry in model_list:
        name = entry.get("model_name", "")
        tier = name.split("-")[0] if "-" in name else name
        tiers.setdefault(tier, []).append(name)

    router = cfg.get("router_settings", {}) or {}
    return {
        "tiers": tiers,
        "model_group_alias": router.get("model_group_alias", {}),
        "fallbacks": router.get("fallbacks", []),
        "num_retries": router.get("num_retries"),
    }


@app.get("/api/llm/status")
async def llm_status(_user: str = Depends(require_basic_auth), pool: asyncpg.Pool = Depends(get_pool)):
    config_info = _parse_litellm_config()

    speed_multiplier = 1.0
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT speed_multiplier FROM sim_clock WHERE id = 1")
            if row:
                speed_multiplier = float(row["speed_multiplier"])
    except Exception as exc:
        log.warning("llm_status: could not read sim_clock.speed_multiplier: %s", exc)

    return {"provider_config": config_info, "speed_multiplier": speed_multiplier}


@app.get("/api/llm/spend")
async def llm_spend(_user: str = Depends(require_basic_auth), pool: asyncpg.Pool = Depends(get_pool)):
    """Reuses the exact query logic from monitoring/grafana/dashboards/llm-spend.json
    (Phase 31) — same LiteLLM_SpendLogs table, same aggregations, no re-derivation."""
    async with pool.acquire() as conn:
        total_spend = await conn.fetchval('SELECT COALESCE(SUM(spend), 0) FROM "LiteLLM_SpendLogs"')
        total_tokens = await conn.fetchval('SELECT COALESCE(SUM(total_tokens), 0) FROM "LiteLLM_SpendLogs"')
        spend_last_hour = await conn.fetchval(
            'SELECT COALESCE(SUM(spend), 0) FROM "LiteLLM_SpendLogs" '
            "WHERE \"startTime\" >= now() - interval '1 hour'"
        )
        by_model = await conn.fetch(
            'SELECT model, COUNT(*) AS calls, SUM(total_tokens) AS tokens, SUM(spend) AS spend '
            'FROM "LiteLLM_SpendLogs" GROUP BY model ORDER BY spend DESC'
        )
        speed_multiplier = await conn.fetchval("SELECT speed_multiplier FROM sim_clock WHERE id = 1") or 1.0

    spend_per_wallclock_hour = float(spend_last_hour or 0)
    speed_multiplier = float(speed_multiplier)
    # Speed-adjusted burn rate: at speed_multiplier > 1, each wall-clock hour represents
    # more sim-hours, so true burn-per-sim-hour = spend_per_wallclock_hour / speed_multiplier.
    # (Same annotation as the Grafana panel's own description — see llm-spend.json.)
    burn_per_sim_hour = spend_per_wallclock_hour / speed_multiplier if speed_multiplier else spend_per_wallclock_hour

    return {
        "total_spend": float(total_spend or 0),
        "total_tokens": int(total_tokens or 0),
        "spend_per_wallclock_hour": spend_per_wallclock_hour,
        "speed_multiplier": speed_multiplier,
        "burn_per_sim_hour": burn_per_sim_hour,
        "by_model": [dict(r) for r in by_model],
    }


# ---------------------------------------------------------------------------
# Narrative tab
#
# narrative_threads / action_items / pending_reactions / pending_approvals /
# meetings / pending_actions have no dedicated owning microservice (orchestrator
# itself reads/writes them via raw SQL against the shared Postgres instance) —
# consistent with that existing pattern, the dashboard reads them directly too
# rather than inventing a proxy service with no real logic of its own.
# ---------------------------------------------------------------------------
@app.get("/api/narrative/summary")
async def narrative_summary(_user: str = Depends(require_basic_auth), pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        threads = await conn.fetch("""
            SELECT id, topic, department, status, summary, priority, created_at, updated_at
            FROM narrative_threads
            WHERE status IN ('open', 'in_progress')
            ORDER BY priority DESC, updated_at DESC
            LIMIT 100
        """)
        action_items = await conn.fetch("""
            SELECT id, meeting_id, thread_id, owner_employee_id, description, due_at, status
            FROM action_items
            ORDER BY (status = 'open') DESC, due_at NULLS LAST
            LIMIT 100
        """)
        pending_reactions = await conn.fetch("""
            SELECT id, thread_id, target_employee_id, triggering_event_id, status
            FROM pending_reactions
            WHERE status = 'pending'
            ORDER BY id DESC
            LIMIT 100
        """)
        pending_approvals = await conn.fetch("""
            SELECT id, expense_request_ref, requester_employee_id, approver_employee_id,
                   approver_is_principal, amount, status, created_at
            FROM pending_approvals
            WHERE status = 'pending'
            ORDER BY created_at DESC
            LIMIT 100
        """)
        meetings = await conn.fetch("""
            SELECT id, thread_id, meeting_type, attendees, created_at
            FROM meetings
            ORDER BY created_at DESC
            LIMIT 50
        """)
        pending_actions_depth = await conn.fetchval("""
            SELECT COUNT(*) FROM pending_actions WHERE status IN ('pending', 'retrying')
        """)
        pending_actions_recent = await conn.fetch("""
            SELECT id, action_type, target_service, status, attempts, next_retry_at, last_error
            FROM pending_actions
            ORDER BY id DESC
            LIMIT 20
        """)

    def row_to_dict(r):
        d = dict(r)
        for k, v in d.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        return d

    return {
        "threads": [row_to_dict(r) for r in threads],
        "action_items": [row_to_dict(r) for r in action_items],
        "pending_reactions": [row_to_dict(r) for r in pending_reactions],
        "pending_approvals": [row_to_dict(r) for r in pending_approvals],
        "meetings": [row_to_dict(r) for r in meetings],
        "pending_actions": {
            "retry_queue_depth": int(pending_actions_depth or 0),
            "recent": [row_to_dict(r) for r in pending_actions_recent],
        },
    }


# ---------------------------------------------------------------------------
# Phase 34: HR / Org Chart tab
#
# Roster + relationships have no dedicated owning microservice for *reads*
# (same pattern as narrative_threads etc. in Phase 33) — direct SQL. Fire/Hire
# are real side-effecting actions across 4 appliances, so those proxy to
# provisioning's new HTTP endpoints rather than duplicating that logic here.
# ---------------------------------------------------------------------------
@app.get("/api/hr/roster")
async def hr_roster(_user: str = Depends(require_basic_auth), pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT e.id, e.name, e.department, e.role, e.role_tier, e.status,
                   e.hired_at, e.terminated_at, e.pay_rate, e.pay_frequency,
                   EXISTS (
                       SELECT 1 FROM pto_calendar p
                       WHERE p.employee_id = e.id
                         AND p.start_sim_time <= NOW() AND p.end_sim_time > NOW()
                   ) AS on_pto
            FROM employees e
            ORDER BY e.department, e.role_tier DESC, e.hired_at
        """)

    def to_dict(r):
        d = dict(r)
        # Phase 19's pto_calendar is sim-time keyed; NOW() above is wall-clock,
        # which is an approximation — good enough for an at-a-glance dashboard
        # badge, not used for any functional gating.
        display_status = d["status"]
        if d["status"] == "active" and d["on_pto"]:
            display_status = "on-PTO"
        d["display_status"] = display_status
        for k, v in d.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
            elif isinstance(v, Decimal):
                d[k] = float(v)
        return d

    return {"employees": [to_dict(r) for r in rows]}


@app.get("/api/hr/relationships")
async def hr_relationships(_user: str = Depends(require_basic_auth), pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        edges = await conn.fetch("""
            SELECT r.employee_a_id, r.employee_b_id, r.relationship_type, r.affinity_score,
                   ea.name AS a_name, eb.name AS b_name
            FROM employee_relationships r
            JOIN employees ea ON ea.id = r.employee_a_id
            JOIN employees eb ON eb.id = r.employee_b_id
        """)
        nodes = await conn.fetch("SELECT id, name, department, status FROM employees")

    return {
        "nodes": [dict(n) for n in nodes],
        "edges": [dict(e) for e in edges],
    }


class HireBody(BaseModel):
    name: str
    department: str
    title: str
    role_tier: str = "ic"


@app.post("/api/hr/employees/hire")
async def hr_hire(body: HireBody, _user: str = Depends(require_basic_auth)):
    try:
        r = await _http.post(f"{PROVISIONING_URL}/hire", json=body.model_dump(), timeout=60.0)
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"provisioning unreachable: {exc}")


@app.post("/api/hr/employees/{employee_id}/fire")
async def hr_fire(employee_id: int, _user: str = Depends(require_basic_auth)):
    try:
        r = await _http.post(f"{PROVISIONING_URL}/fire", json={"employee_id": employee_id}, timeout=60.0)
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"provisioning unreachable: {exc}")


# ---------------------------------------------------------------------------
# Phase 34: Payroll tab
#
# Raise path: proxies accounting-engine's existing /payroll/raise (applies
# immediately, spec §10.3). Cut path: Phase 24 (pay negotiation meetings)
# doesn't exist yet — accounting-engine's own /payroll/propose-cut is a STUB
# that only logs and queues, per that file's own header comment. Per the
# 2026-08-01 sign-off and PHASES.md line 735 ("never applying directly"), the
# dashboard does NOT call any cut-applying path from the Save button at all —
# it's disabled client-side, and this BFF exposes no endpoint that would let a
# cut bypass that. Payroll history reads system_audit_log directly (no
# dedicated payroll_history table exists — raise/cut events are already
# durably logged there by accounting-engine, same pattern as Phase 33's
# narrative tab reusing tables with no owning service for reads).
# ---------------------------------------------------------------------------
@app.get("/api/payroll/roster")
async def payroll_roster(_user: str = Depends(require_basic_auth), pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, name, department, role, role_tier, status, pay_rate, pay_frequency,
                   pay_last_changed_at, pay_last_change_reason
            FROM employees
            WHERE status = 'active'
            ORDER BY department, role_tier DESC, name
        """)

    def to_dict(r):
        d = dict(r)
        for k, v in d.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
            elif isinstance(v, Decimal):
                d[k] = float(v)
        return d

    return {"employees": [to_dict(r) for r in rows]}


@app.get("/api/payroll/history")
async def payroll_history(_user: str = Depends(require_basic_auth), pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, actor, action, detail, created_at
            FROM system_audit_log
            WHERE action IN ('raise_applied', 'pay_cut_proposed_stub')
            ORDER BY created_at DESC
            LIMIT 200
        """)

    def to_dict(r):
        d = dict(r)
        d["created_at"] = d["created_at"].isoformat()
        detail = d["detail"]
        d["detail"] = json.loads(detail) if isinstance(detail, str) else dict(detail)
        return d

    return {"history": [to_dict(r) for r in rows]}


class RaiseBody(BaseModel):
    employee_id: int
    new_pay: float
    reason: str = "manual raise via dashboard"


@app.post("/api/payroll/raise")
async def payroll_raise(body: RaiseBody, _user: str = Depends(require_basic_auth)):
    """Increase-only — accounting-engine's /payroll/raise itself 400s on a
    decrease (belt-and-suspenders; the frontend Save button is also disabled
    client-side for a decrease so this rejection should never normally fire)."""
    try:
        r = await _http.post(
            f"{ACCOUNTING_ENGINE_URL}/payroll/raise",
            params={"employee_id": body.employee_id, "new_pay": body.new_pay, "reason": body.reason},
            timeout=30.0,
        )
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"accounting-engine unreachable: {exc}")


# ---------------------------------------------------------------------------
# Phase 34: Accounting tab
# ---------------------------------------------------------------------------
@app.get("/api/accounting/summary")
async def accounting_summary(_user: str = Depends(require_basic_auth), pool: asyncpg.Pool = Depends(get_pool)):
    cash = {"cash_balance": None, "accounts": [], "error": None}
    try:
        r = await _http.get(f"{ACCOUNTING_ENGINE_URL}/accounting/cash-balance", timeout=15.0)
        r.raise_for_status()
        cash = {**r.json(), "error": None}
    except Exception as exc:
        cash["error"] = str(exc)

    async with pool.acquire() as conn:
        approvals = await conn.fetch("""
            SELECT id, expense_request_ref, requester_employee_id, approver_employee_id,
                   approver_is_principal, amount, status, created_at
            FROM pending_approvals
            WHERE status = 'pending'
            ORDER BY created_at DESC
            LIMIT 100
        """)
        audit_entries = await conn.fetch("""
            SELECT id, actor, action, detail, created_at
            FROM system_audit_log
            WHERE action IN ('audit_correction', 'audit_run_complete', 'payroll_no_akaunting_ref')
            ORDER BY created_at DESC
            LIMIT 100
        """)

    def row_to_dict(r):
        d = dict(r)
        for k, v in d.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        if "detail" in d:
            d["detail"] = json.loads(d["detail"]) if isinstance(d["detail"], str) else dict(d["detail"])
        return d

    return {
        "cash": cash,
        "akaunting_deep_link": f"{AKAUNTING_PUBLIC_URL}/{AKAUNTING_COMPANY_ID}/reports/profit-loss",
        "pending_approvals": [row_to_dict(r) for r in approvals],
        "audit_log": [row_to_dict(r) for r in audit_entries],
    }


@app.post("/api/accounting/audit/run")
async def accounting_run_audit(_user: str = Depends(require_basic_auth)):
    try:
        r = await _http.post(f"{ACCOUNTING_ENGINE_URL}/audit/run", timeout=60.0)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"accounting-engine unreachable: {exc}")


class ApprovalBody(BaseModel):
    approval_id: int
    actor: str = "principal"
    note: str = ""


@app.post("/api/accounting/expense/approve")
async def accounting_approve(body: ApprovalBody, _user: str = Depends(require_basic_auth)):
    try:
        r = await _http.post(
            f"{ACCOUNTING_ENGINE_URL}/expense/approve",
            json={"approval_id": body.approval_id, "approved_by": body.actor, "note": body.note},
            timeout=30.0,
        )
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"accounting-engine unreachable: {exc}")


@app.post("/api/accounting/expense/reject")
async def accounting_reject(body: ApprovalBody, _user: str = Depends(require_basic_auth)):
    try:
        r = await _http.post(
            f"{ACCOUNTING_ENGINE_URL}/expense/reject",
            json={"approval_id": body.approval_id, "rejected_by": body.actor, "note": body.note},
            timeout=30.0,
        )
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"accounting-engine unreachable: {exc}")


# ---------------------------------------------------------------------------
# Phase 35: External World tab
#
# BetaCorp news + customer pipeline read narrative-db's system_audit_log /
# customers tables directly (same "no owning service for reads" pattern as
# Phase 33/34's other direct-SQL endpoints). Revenue-by-customer joins that
# Postgres customers row to Akaunting's ak_transactions via
# customers.akaunting_transaction_id (set once by accounting-engine's
# post_revenue() when a deal closes) — reads Akaunting's MariaDB directly,
# same data source as Phase 31's customer-pipeline-revenue.json Grafana panel.
# ---------------------------------------------------------------------------
BETACORP_ACTIONS = ("betacorp_offer_sent", "employee_resigned_betacorp", "pay_gap_flag_raised")
JOB_OFFER_RESIGNATION_ACTIONS = ("betacorp_offer_sent", "employee_resigned_betacorp")


@app.get("/api/external-world/news")
async def external_world_news(_user: str = Depends(require_basic_auth), pool: asyncpg.Pool = Depends(get_pool)):
    """
    BetaCorp news feed: every BetaCorp-related system_audit_log entry, tagged
    with a `category` so the frontend can show the full feed AND filter down
    to just the job-offer/resignation subset without a second round-trip.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, actor, action, detail, created_at
            FROM system_audit_log
            WHERE action = ANY($1::text[])
            ORDER BY created_at DESC
            LIMIT 200
        """, list(BETACORP_ACTIONS))

    def to_dict(r):
        d = dict(r)
        d["created_at"] = d["created_at"].isoformat()
        d["detail"] = json.loads(d["detail"]) if isinstance(d["detail"], str) else dict(d["detail"])
        d["category"] = "job_offer_resignation" if d["action"] in JOB_OFFER_RESIGNATION_ACTIONS else "pay_gap_flag"
        return d

    return {"news": [to_dict(r) for r in rows]}


@app.get("/api/external-world/customers")
async def external_world_customers(_user: str = Depends(require_basic_auth), pool: asyncpg.Pool = Depends(get_pool)):
    """Customer pipeline / at-risk list — sortable client-side by status/risk."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT c.id, c.company_name, c.contact_name, c.contact_email, c.relationship_status,
                   c.deal_size, c.akaunting_transaction_id, c.support_sla_hours, c.created_at,
                   sr.name AS sales_rep, sp.name AS support_rep
            FROM customers c
            LEFT JOIN employees sr ON sr.id = c.assigned_sales_rep_id
            LEFT JOIN employees sp ON sp.id = c.assigned_support_rep_id
            ORDER BY c.relationship_status, c.created_at DESC
        """)

    def to_dict(r):
        d = dict(r)
        d["created_at"] = d["created_at"].isoformat()
        if d["deal_size"] is not None:
            d["deal_size"] = float(d["deal_size"])
        return d

    return {"customers": [to_dict(r) for r in rows]}


@app.get("/api/external-world/revenue-by-customer")
async def external_world_revenue_by_customer(
    _user: str = Depends(require_basic_auth), pool: asyncpg.Pool = Depends(get_pool)
):
    """
    One bar per customer: joins narrative-db's customers table to Akaunting's
    ak_transactions via customers.akaunting_transaction_id — the same revenue
    data Phase 31's customer-pipeline-revenue.json panel reads (that panel
    only shows an aggregate total; this is its per-customer breakdown using
    the identical MySQLAkaunting data source and 'income'/deleted_at=NULL
    filter, not a re-derivation of different numbers).
    """
    async with pool.acquire() as conn:
        customers = await conn.fetch("""
            SELECT id, company_name, relationship_status, akaunting_transaction_id
            FROM customers
            WHERE akaunting_transaction_id IS NOT NULL
        """)

    if not customers:
        return {"revenue_by_customer": [], "error": None}
    if _mysql_pool is None:
        return {"revenue_by_customer": [], "error": "Akaunting MariaDB connection not available"}

    tx_ids = [c["akaunting_transaction_id"] for c in customers]
    result = []
    try:
        async with _mysql_pool.acquire() as mysql_conn:
            async with mysql_conn.cursor(aiomysql.DictCursor) as cur:
                placeholders = ",".join(["%s"] * len(tx_ids))
                await cur.execute(
                    f"SELECT id, amount FROM ak_transactions "
                    f"WHERE id IN ({placeholders}) AND type = 'income' AND deleted_at IS NULL",
                    tx_ids,
                )
                rows = await cur.fetchall()
        amounts_by_tx_id = {str(r["id"]): float(r["amount"]) for r in rows}
        for c in customers:
            amount = amounts_by_tx_id.get(str(c["akaunting_transaction_id"]))
            if amount is not None:
                result.append({
                    "customer_id": c["id"],
                    "company_name": c["company_name"],
                    "relationship_status": c["relationship_status"],
                    "revenue": amount,
                })
        result.sort(key=lambda r: r["revenue"], reverse=True)
        return {"revenue_by_customer": result, "error": None}
    except Exception as exc:
        return {"revenue_by_customer": [], "error": str(exc)}


# ---------------------------------------------------------------------------
# Phase 35: KPI/Performance tab
#
# Scoreboards read kpi_snapshots directly (same no-owning-service-for-reads
# pattern as every other tab). Review-mode toggle proxies kpi-engine's new
# Phase 35 /config/review-mode endpoints (backed by the kpi_engine_config
# table added in migration 011) rather than duplicating that logic here.
# ---------------------------------------------------------------------------
KPI_SCOREBOARD_LOOKBACK_DAYS = int(os.environ.get("KPI_SCOREBOARD_LOOKBACK_DAYS", "30"))


@app.get("/api/kpi/department-scoreboard")
async def kpi_department_scoreboard(_user: str = Depends(require_basic_auth), pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT entity_id AS department, metric, SUM(value) AS total, AVG(value) AS avg_value
            FROM kpi_snapshots
            WHERE entity_type = 'department'
              AND snapshot_date >= NOW() - INTERVAL '{KPI_SCOREBOARD_LOOKBACK_DAYS} days'
            GROUP BY entity_id, metric
            ORDER BY entity_id, metric
        """)
    return {
        "lookback_days": KPI_SCOREBOARD_LOOKBACK_DAYS,
        "rows": [
            {"department": r["department"], "metric": r["metric"],
             "total": float(r["total"]), "avg": float(r["avg_value"])}
            for r in rows
        ],
    }


@app.get("/api/kpi/employee-scoreboard")
async def kpi_employee_scoreboard(_user: str = Depends(require_basic_auth), pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT e.id AS employee_id, e.name, e.department, k.metric,
                   SUM(k.value) AS total, AVG(k.value) AS avg_value
            FROM kpi_snapshots k
            JOIN employees e ON e.id::text = k.entity_id
            WHERE k.entity_type = 'employee'
              AND k.snapshot_date >= NOW() - INTERVAL '{KPI_SCOREBOARD_LOOKBACK_DAYS} days'
            GROUP BY e.id, e.name, e.department, k.metric
            ORDER BY e.department, e.name, k.metric
        """)
    return {
        "lookback_days": KPI_SCOREBOARD_LOOKBACK_DAYS,
        "rows": [
            {"employee_id": r["employee_id"], "name": r["name"], "department": r["department"],
             "metric": r["metric"], "total": float(r["total"]), "avg": float(r["avg_value"])}
            for r in rows
        ],
    }


@app.get("/api/kpi/review-log")
async def kpi_review_log(_user: str = Depends(require_basic_auth), pool: asyncpg.Pool = Depends(get_pool)):
    """
    Past raises applied via Phase 23's formula. Tier isn't a separate audit-log
    column — kpi-engine's reason string already embeds it
    ("performance_review: top_quartile in Engineering (rank 1/5)") — parse it
    out here so the UI can show a clean tier badge without re-deriving the
    formula.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, actor, action, detail, created_at
            FROM system_audit_log
            WHERE action IN ('review_raise_applied', 'review_raise_queued')
            ORDER BY created_at DESC
            LIMIT 200
        """)

    def to_dict(r):
        d = dict(r)
        d["created_at"] = d["created_at"].isoformat()
        detail = json.loads(d["detail"]) if isinstance(d["detail"], str) else dict(d["detail"])
        d["detail"] = detail
        reason = detail.get("reason", "")
        tier = "unknown"
        for candidate in ("top_quartile", "second_quartile", "rest"):
            if candidate in reason:
                tier = candidate
                break
        d["tier"] = tier
        return d

    return {"reviews": [to_dict(r) for r in rows]}


@app.get("/api/kpi/review-mode")
async def kpi_review_mode(_user: str = Depends(require_basic_auth)):
    try:
        r = await _http.get(f"{KPI_ENGINE_URL}/config/review-mode", timeout=10.0)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"kpi-engine unreachable: {exc}")


class ReviewModeBody(BaseModel):
    enabled: bool


@app.post("/api/kpi/review-mode")
async def kpi_set_review_mode(body: ReviewModeBody, _user: str = Depends(require_basic_auth)):
    try:
        r = await _http.post(
            f"{KPI_ENGINE_URL}/config/review-mode",
            json={"enabled": body.enabled, "actor": "principal"},
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"kpi-engine unreachable: {exc}")


# ---------------------------------------------------------------------------
# Phase 35: Company Direction tab
#
# company_directives is already versioned/append-only (Phase 13's migration
# 002 gave it version/is_current/created_at/created_by columns from day one) —
# no new migration needed here, confirmed by reading that migration and
# human-bridge's existing /action/update-directive writer before building this.
# Save proxies to human-bridge, which now also performs the Wiki.js
# pinned-page sync (added in this same phase — see human-bridge/main.py).
# ---------------------------------------------------------------------------
@app.get("/api/company-direction/current")
async def company_direction_current(_user: str = Depends(require_basic_auth), pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, content, version, created_at, created_by
            FROM company_directives WHERE is_current = TRUE
            ORDER BY version DESC LIMIT 1
        """)
    if row is None:
        return {"current": None}
    d = dict(row)
    d["created_at"] = d["created_at"].isoformat()
    return {"current": d}


@app.get("/api/company-direction/history")
async def company_direction_history(_user: str = Depends(require_basic_auth), pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, content, version, is_current, created_at, created_by
            FROM company_directives
            ORDER BY version DESC
            LIMIT 100
        """)

    def to_dict(r):
        d = dict(r)
        d["created_at"] = d["created_at"].isoformat()
        return d

    return {"history": [to_dict(r) for r in rows]}


class SaveDirectiveBody(BaseModel):
    content: str


@app.post("/api/company-direction/save")
async def company_direction_save(body: SaveDirectiveBody, _user: str = Depends(require_basic_auth)):
    try:
        r = await _http.post(
            f"{HUMAN_BRIDGE_URL}/action/update-directive",
            json={"content": body.content, "created_by": "principal"},
            timeout=30.0,
        )
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"human-bridge unreachable: {exc}")


# ---------------------------------------------------------------------------
# Phase 36: Chaos tab
#
# Per-appliance status/outages/trigger-event all proxy orchestrator's existing
# Phase 27/28 endpoints — no duplicated logic here.
# ---------------------------------------------------------------------------
@app.get("/api/chaos/status")
async def chaos_status(_user: str = Depends(require_basic_auth)):
    try:
        r = await _http.get(f"{ORCHESTRATOR_URL}/chaos/appliances/status", timeout=15.0)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"orchestrator unreachable: {exc}")


@app.get("/api/chaos/outages")
async def chaos_outages(_user: str = Depends(require_basic_auth)):
    try:
        r = await _http.get(f"{ORCHESTRATOR_URL}/chaos/outages", timeout=15.0)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"orchestrator unreachable: {exc}")


@app.post("/api/chaos/appliances/{name}/{action}")
async def chaos_appliance_action(name: str, action: str, _user: str = Depends(require_basic_auth)):
    if action not in ("stop", "start", "restart"):
        raise HTTPException(status_code=400, detail="action must be stop, start, or restart")
    try:
        r = await _http.post(f"{ORCHESTRATOR_URL}/chaos/appliances/{name}/{action}", timeout=30.0)
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"orchestrator unreachable: {exc}")


class TriggerEventBody(BaseModel):
    scenario: str
    custom_text: Optional[str] = None


@app.post("/api/chaos/trigger-event")
async def chaos_trigger_event(body: TriggerEventBody, _user: str = Depends(require_basic_auth)):
    try:
        r = await _http.post(
            f"{ORCHESTRATOR_URL}/chaos/trigger-event",
            json=body.model_dump(),
            timeout=120.0,
        )
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"orchestrator unreachable: {exc}")


# ---------------------------------------------------------------------------
# Phase 36: Data Management tab — SCOPED purge + snapshots only. Full purge
# is deliberately NOT here (2026-08-01 sign-off moved it to Settings, below).
# ---------------------------------------------------------------------------
@app.get("/api/data-management/scopes")
async def data_management_scopes(_user: str = Depends(require_basic_auth)):
    return {"scopes": DATA_MANAGEMENT_SCOPES}


class ScopePurgeBody(BaseModel):
    scope: str
    confirm: str


@app.post("/api/data-management/purge-scope")
async def data_management_purge_scope(body: ScopePurgeBody, _user: str = Depends(require_basic_auth)):
    valid_scopes = {s["scope"] for s in DATA_MANAGEMENT_SCOPES}
    if body.scope not in valid_scopes:
        raise HTTPException(status_code=400, detail=f"unknown scope '{body.scope}'")
    try:
        r = await _http.post(
            f"{PURGE_MANAGER_URL}/purge/{body.scope}",
            json={"confirm": body.confirm},
            timeout=180.0,
        )
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"purge-manager unreachable: {exc}")


@app.get("/api/data-management/snapshots")
async def data_management_snapshots(_user: str = Depends(require_basic_auth)):
    try:
        r = await _http.get(f"{SNAPSHOT_MANAGER_URL}/snapshot/list", timeout=15.0)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"snapshot-manager unreachable: {exc}")


class SnapshotSaveBody(BaseModel):
    label: Optional[str] = None


@app.post("/api/data-management/snapshots/save")
async def data_management_snapshot_save(body: SnapshotSaveBody, _user: str = Depends(require_basic_auth)):
    try:
        r = await _http.post(
            f"{SNAPSHOT_MANAGER_URL}/snapshot/save",
            json={"label": body.label},
            timeout=180.0,
        )
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"snapshot-manager unreachable: {exc}")


class SnapshotRestoreBody(BaseModel):
    snapshot_name: str
    confirm: str


@app.post("/api/data-management/snapshots/restore")
async def data_management_snapshot_restore(body: SnapshotRestoreBody, _user: str = Depends(require_basic_auth)):
    try:
        r = await _http.post(
            f"{SNAPSHOT_MANAGER_URL}/snapshot/restore",
            json=body.model_dump(),
            timeout=300.0,
        )
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"snapshot-manager unreachable: {exc}")


@app.delete("/api/data-management/snapshots/{snapshot_name}")
async def data_management_snapshot_delete(snapshot_name: str, _user: str = Depends(require_basic_auth)):
    try:
        r = await _http.delete(f"{SNAPSHOT_MANAGER_URL}/snapshot/{snapshot_name}", timeout=30.0)
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"snapshot-manager unreachable: {exc}")


# ---------------------------------------------------------------------------
# Phase 36: Branding tab
# ---------------------------------------------------------------------------
@app.get("/api/branding/asset-proxy/avatars/{asset_id}.png")
async def branding_asset_proxy_avatar(asset_id: str, _user: str = Depends(require_basic_auth)):
    """branding-manager isn't on net_mgmt (no browser-reachable network) — this
    streams its image bytes through the BFF so the asset library grid can
    actually render, rather than duplicating the asset files here."""
    try:
        r = await _http.get(f"{BRANDING_MANAGER_URL}/assets/avatars/{asset_id}.png", timeout=15.0)
        r.raise_for_status()
        return Response(content=r.content, media_type="image/png")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"branding-manager unreachable: {exc}")


@app.get("/api/branding/asset-proxy/emoji/{asset_id}.png")
async def branding_asset_proxy_emoji(asset_id: str, _user: str = Depends(require_basic_auth)):
    try:
        r = await _http.get(f"{BRANDING_MANAGER_URL}/assets/emoji/{asset_id}.png", timeout=15.0)
        r.raise_for_status()
        return Response(content=r.content, media_type="image/png")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"branding-manager unreachable: {exc}")


@app.get("/api/branding/assets")
async def branding_assets(_user: str = Depends(require_basic_auth)):
    try:
        r = await _http.get(f"{BRANDING_MANAGER_URL}/assets", timeout=15.0)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"branding-manager unreachable: {exc}")


@app.get("/api/branding/employee/{employee_id}")
async def branding_employee(employee_id: int, _user: str = Depends(require_basic_auth)):
    try:
        r = await _http.get(f"{BRANDING_MANAGER_URL}/branding/employee/{employee_id}", timeout=15.0)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"branding-manager unreachable: {exc}")


class ApplyAvatarBody(BaseModel):
    employee_id: int
    asset_id: str


@app.post("/api/branding/apply")
async def branding_apply(body: ApplyAvatarBody, _user: str = Depends(require_basic_auth)):
    try:
        r = await _http.post(f"{BRANDING_MANAGER_URL}/branding/apply", json=body.model_dump(), timeout=60.0)
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"branding-manager unreachable: {exc}")


class BulkApplyBody(BaseModel):
    employee_ids: list[int]
    mode: str
    asset_id: Optional[str] = None


@app.post("/api/branding/bulk-apply")
async def branding_bulk_apply(body: BulkApplyBody, _user: str = Depends(require_basic_auth)):
    try:
        r = await _http.post(f"{BRANDING_MANAGER_URL}/branding/bulk-apply", json=body.model_dump(), timeout=180.0)
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"branding-manager unreachable: {exc}")


# ---------------------------------------------------------------------------
# Settings tab — Phase 36/38: the "nuclear launch" full-purge control.
#
# 2026-08-01 sign-off (PLAN_PHASES_33_38_DASHBOARD.md §Decisions #3): this is
# the ONLY place in the whole dashboard the full-purge control lives — it is
# NOT on the Data Management tab. Requires the user to confirm no fewer than
# 3 separate times (enforced client-side by the SPA's step sequence; this BFF
# is the last of those steps, and purge-manager's own confirm-phrase check is
# an entirely separate, additional server-side gate — see purge-manager's own
# module docstring on the mandatory pre-purge snapshot + phrase match).
# ---------------------------------------------------------------------------
@app.get("/api/settings/full-purge/last-snapshot")
async def settings_last_snapshot(_user: str = Depends(require_basic_auth)):
    """So the 'nuclear launch' control can show 'Last snapshot taken: ...'
    prominently next to itself, per the sign-off — the user should be able to
    see whether a safety net exists before ever clicking step 1."""
    try:
        r = await _http.get(f"{SNAPSHOT_MANAGER_URL}/snapshot/list", timeout=15.0)
        r.raise_for_status()
        snapshots = r.json().get("snapshots", [])
    except Exception as exc:
        return {"last_snapshot": None, "error": f"snapshot-manager unreachable: {exc}"}
    if not snapshots:
        return {"last_snapshot": None, "error": None}
    latest = max(snapshots, key=lambda s: s.get("wall_clock_captured_at", ""))
    return {"last_snapshot": latest, "error": None}


class FullPurgeBody(BaseModel):
    confirm: str


@app.post("/api/settings/full-purge")
async def settings_full_purge(body: FullPurgeBody, _user: str = Depends(require_basic_auth)):
    """The actual destructive call. The SPA only ever reaches this after its
    own full multi-step confirmation sequence completes — this endpoint does
    not know or care about that client-side sequence, it simply forwards to
    purge-manager's own /purge/full, which re-validates the typed phrase and
    performs its own mandatory pre-purge snapshot regardless of what the
    client already did. Two independent gates, not one gate trusted twice."""
    try:
        r = await _http.post(
            f"{PURGE_MANAGER_URL}/purge/full",
            json={"confirm": body.confirm},
            timeout=600.0,
        )
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"purge-manager unreachable: {exc}")


# ---------------------------------------------------------------------------
# Phase 37: TV wall — live chat/ticket feeds
#
# Reuses the exact same Mattermost/Zammad admin-token read pattern already
# proven in human-bridge/main.py's _poll_mattermost_once / _poll_zammad_once
# (team channels -> per-channel recent posts; ticket list -> per-ticket
# articles) rather than re-deriving a new approach. This is read-only and has
# no cursor/state (unlike human-bridge's polling, which tracks "already
# reacted to" state) — the TV wall just wants "what's recent right now".
# ---------------------------------------------------------------------------
@app.get("/api/tv/chat-feed")
async def tv_chat_feed(_user: str = Depends(require_basic_auth)):
    if not MATTERMOST_ADMIN_TOKEN:
        raise HTTPException(status_code=502, detail="MATTERMOST_ADMIN_TOKEN not configured")
    headers = {"Authorization": f"Bearer {MATTERMOST_ADMIN_TOKEN}"}
    team_id = MATTERMOST_TEAM_ID
    try:
        if not team_id:
            tr = await _http.get(f"{MATTERMOST_URL}/api/v4/teams", headers=headers, timeout=10.0)
            tr.raise_for_status()
            teams = tr.json()
            if not teams:
                return {"posts": []}
            team_id = teams[0]["id"]

        cr = await _http.get(f"{MATTERMOST_URL}/api/v4/teams/{team_id}/channels", headers=headers, timeout=10.0)
        cr.raise_for_status()
        channels = {c["id"]: c["display_name"] for c in cr.json()}

        posts: list[dict] = []
        user_cache: dict[str, str] = {}
        for channel_id, channel_name in channels.items():
            pr = await _http.get(
                f"{MATTERMOST_URL}/api/v4/channels/{channel_id}/posts",
                headers=headers, params={"page": 0, "per_page": 5}, timeout=10.0,
            )
            if pr.status_code != 200:
                continue
            posts_data = pr.json().get("posts", {})
            for post_id, post in posts_data.items():
                user_id = post.get("user_id", "")
                if user_id not in user_cache:
                    ur = await _http.get(f"{MATTERMOST_URL}/api/v4/users/{user_id}", headers=headers, timeout=10.0)
                    user_cache[user_id] = ur.json().get("username", user_id) if ur.status_code == 200 else user_id
                posts.append({
                    "id": post_id,
                    "channel": channel_name,
                    "username": user_cache[user_id],
                    "message": (post.get("message") or "")[:280],
                    "create_at": post.get("create_at"),
                })
        posts.sort(key=lambda p: p["create_at"] or 0, reverse=True)
        return {"posts": posts[:20]}
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"mattermost unreachable: {exc}")


@app.get("/api/tv/ticket-feed")
async def tv_ticket_feed(_user: str = Depends(require_basic_auth)):
    if not ZAMMAD_ADMIN_TOKEN:
        raise HTTPException(status_code=502, detail="ZAMMAD_ADMIN_TOKEN not configured")
    headers = {"Authorization": f"Token token={ZAMMAD_ADMIN_TOKEN}"}
    try:
        r = await _http.get(f"{ZAMMAD_URL}/api/v1/tickets", headers=headers, timeout=15.0)
        r.raise_for_status()
        tickets = r.json()
        tickets.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        return {
            "tickets": [
                {
                    "id": t.get("id"),
                    "number": t.get("number"),
                    "title": t.get("title"),
                    "state_id": t.get("state_id"),
                    "created_at": t.get("created_at"),
                }
                for t in tickets[:20]
            ]
        }
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"zammad unreachable: {exc}")


# ---------------------------------------------------------------------------
# Phase 37: Errors panel — Loki query proxy
#
# No dedicated exceptions table/endpoint exists anywhere (per the plan's own
# framing) — Loki already aggregates every fakeco-* container's stdout
# (Phase 11) with `level` promoted to a real stream label by promtail's own
# pipeline_stages (see monitoring/promtail-config.yaml), so `{level="ERROR"}`
# is a real, cheap label-matched query, not a full-text scan.
# ---------------------------------------------------------------------------
@app.get("/api/errors/services")
async def errors_services(_user: str = Depends(require_basic_auth)):
    return {"services": ERROR_PANEL_SERVICES}


@app.get("/api/errors/recent")
async def errors_recent(
    service: Optional[str] = None,
    limit: int = 200,
    _user: str = Depends(require_basic_auth),
):
    if service and service not in ERROR_PANEL_SERVICES:
        raise HTTPException(status_code=400, detail=f"unknown service '{service}'")
    container_match = service if service else "|".join(ERROR_PANEL_SERVICES)
    query = f'{{container=~"{container_match}", level="ERROR"}}'
    try:
        r = await _http.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params={"query": query, "limit": limit, "direction": "backward"},
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"loki unreachable: {exc}")

    rows = []
    for stream in data.get("data", {}).get("result", []):
        container = stream.get("stream", {}).get("container", "unknown")
        for ts_ns, line in stream.get("values", []):
            rows.append({
                "container": container,
                "timestamp": datetime.fromtimestamp(int(ts_ns) / 1e9, tz=timezone.utc).isoformat(),
                "line": line,
            })
    rows.sort(key=lambda r: r["timestamp"], reverse=True)
    return {"errors": rows[:limit], "query": query}


# ---------------------------------------------------------------------------
# Phase 37: Deep Links panel (2026-08-01 sign-off, amended — no iframe, direct
# links + visible Principal credentials only). See _build_deep_links() above
# for the credential-sourcing rationale per appliance.
# ---------------------------------------------------------------------------
@app.get("/api/deep-links")
async def deep_links(_user: str = Depends(require_basic_auth)):
    return {"links": _build_deep_links()}


# ---------------------------------------------------------------------------
# Phase 37: Log tail — live SSE stream of Traefik + Technitium logs via Loki.
# Reuses the EXACT LogQL query from Phase 31's traffic-and-activity.json
# panel #5 ("Live Traefik + Technitium Log Tail"), verbatim, not re-derived.
# ---------------------------------------------------------------------------
LOG_TAIL_QUERY = '{container=~"fakeco-traefik|fakeco-dns"}'


@app.get("/api/logs/tail")
async def logs_tail(_user: str = Depends(require_basic_auth)):
    async def event_stream():
        last_ns = int(datetime.now(timezone.utc).timestamp() * 1e9) - 30_000_000_000  # start 30s back
        while True:
            try:
                r = await _http.get(
                    f"{LOKI_URL}/loki/api/v1/query_range",
                    params={
                        "query": LOG_TAIL_QUERY,
                        "start": last_ns,
                        "limit": 200,
                        "direction": "forward",
                    },
                    timeout=15.0,
                )
                r.raise_for_status()
                data = r.json()
                lines = []
                for stream in data.get("data", {}).get("result", []):
                    container = stream.get("stream", {}).get("container", "unknown")
                    for ts_ns, line in stream.get("values", []):
                        ts_ns_int = int(ts_ns)
                        if ts_ns_int <= last_ns:
                            continue
                        lines.append({
                            "container": container,
                            "timestamp": datetime.fromtimestamp(ts_ns_int / 1e9, tz=timezone.utc).isoformat(),
                            "line": line,
                        })
                        last_ns = max(last_ns, ts_ns_int)
                lines.sort(key=lambda l: l["timestamp"])
                for line in lines:
                    yield f"data: {json.dumps(line)}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Static SPA — served last so /api/* and /health are matched first.
# Every static request (including index.html) is gated by the same Basic Auth
# dependency, per the 2026-08-01 sign-off ("the entire dashboard").
# ---------------------------------------------------------------------------
if STATIC_DIR.exists():
    @app.get("/{full_path:path}")
    async def spa_catch_all(full_path: str, _user: str = Depends(require_basic_auth)):
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
else:
    log.warning("Static bundle directory %s does not exist — SPA will 404 (dev mode?)", STATIC_DIR)
