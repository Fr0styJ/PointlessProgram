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
import json
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
