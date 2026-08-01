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
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import asyncpg
import httpx
import yaml
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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

DASHBOARD_AUTH_USER = os.environ.get("DASHBOARD_AUTH_USER")
DASHBOARD_AUTH_PASSWORD = os.environ.get("DASHBOARD_AUTH_PASSWORD")

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


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Pool not initialized")
    return _pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _http
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=5)
    _http = httpx.AsyncClient(timeout=15.0)
    if not DASHBOARD_AUTH_USER or not DASHBOARD_AUTH_PASSWORD:
        log.warning(
            "DASHBOARD_AUTH_USER / DASHBOARD_AUTH_PASSWORD not set — dashboard will "
            "refuse all requests (503) until both are configured."
        )
    log.info("dashboard: service ready")
    yield
    await _http.aclose()
    await _pool.close()
    log.info("dashboard: shutdown complete")


app = FastAPI(
    title="FakeCo Control Dashboard",
    description="Phase 33: shell + Simulation / LLM Status / Narrative tabs.",
    version="1.0.0",
    lifespan=lifespan,
)


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
# Settings tab — Phase 33 reserves the nav slot + an empty page shell only.
# The full-purge "nuclear launch" control is Phase 36/38's job (2026-08-01
# sign-off) — nothing destructive is wired up here.
# ---------------------------------------------------------------------------
@app.get("/api/settings/placeholder")
async def settings_placeholder(_user: str = Depends(require_basic_auth)):
    return {
        "status": "reserved",
        "message": "Settings tab is a navigation placeholder as of Phase 33. "
                    "The full-purge control lands in Phase 36/38.",
    }


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
