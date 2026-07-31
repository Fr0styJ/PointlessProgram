"""
orchestrator/main.py — FakeCo "Real Appliances"
Phase 18: Central simulation orchestrator — the heartbeat of FakeCo.

Spec §18: On every tick (configurable interval reading sim_time from Postgres),
the orchestrator checks what needs to happen and fires the right services.

Primary schedule (per sim-time day):
  - Standup meetings: every weekday, per department (§6.1)
  - Cross-functional: every 14 sim-days (§6.2)
  - Performance reviews: monthly per eligible employee (§6.3)
  - Payroll: biweekly (§10.3)
  - KPI rollup: daily (§12.1) — wired in Phase 23
  - Books audit: daily (§10.4)
  - External world generator: per-tick flavor events (§13) — wired in Phase 21

Reactive triggers (per tick, checked every tick):
  - Open narrative threads with no activity in 2+ sim-days → escalate to crisis_response
  - pending_reactions rows → trigger appropriate meeting or action
  - pending_approvals older than 1 sim-day → reminder Mattermost message

Spec §18 design: orchestrator makes NO LLM calls. It only schedules other services.
All state checks are SQL reads. All decisions are rule-based Python.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import asyncpg
import httpx
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from typing import Annotated
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","service":"orchestrator","msg":"%(message)s"}'
)
log = logging.getLogger("orchestrator")

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
MEETING_SIM_URL = os.environ.get("MEETING_SIM_URL", "http://meeting-simulator:8000")
ACCOUNTING_ENGINE_URL = os.environ.get("ACCOUNTING_ENGINE_URL", "http://accounting-engine:8000")
KPI_ENGINE_URL = os.environ.get("KPI_ENGINE_URL", "http://kpi-engine:8000")
EXTERNAL_WORLD_URL = os.environ.get("EXTERNAL_WORLD_URL", "http://external-world:8000")

TICK_INTERVAL_SECONDS = float(os.environ.get("ORCHESTRATOR_TICK_INTERVAL", "60.0"))
STANDUP_HOUR = int(os.environ.get("STANDUP_SIM_HOUR", "9"))     # fire standup at 9am sim-time
CROSS_DEPT_INTERVAL_SIM_DAYS = int(os.environ.get("CROSS_DEPT_INTERVAL_DAYS", "14"))
PERF_REVIEW_INTERVAL_SIM_DAYS = int(os.environ.get("PERF_REVIEW_INTERVAL_DAYS", "30"))
PAYROLL_INTERVAL_SIM_DAYS = int(os.environ.get("PAYROLL_INTERVAL_DAYS", "14"))  # biweekly
STALE_THREAD_THRESHOLD_SIM_DAYS = int(os.environ.get("STALE_THREAD_DAYS", "2"))
APPROVAL_REMINDER_SIM_DAYS = float(os.environ.get("APPROVAL_REMINDER_DAYS", "1.0"))

DEPARTMENTS = [
    "Engineering", "Sales", "Support", "Operations", "HR", "Finance", "Marketing"
]


# ---------------------------------------------------------------------------
# Shared HTTP client and DB pool
# ---------------------------------------------------------------------------
_pool: asyncpg.Pool | None = None
_http: httpx.AsyncClient | None = None


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Pool not initialized")
    return _pool


async def get_sim_time() -> datetime:
    try:
        r = await _http.get(f"{SIM_CLOCK_URL}/sim_time", timeout=5.0)
        r.raise_for_status()
        return datetime.fromisoformat(r.json()["sim_time"])
    except Exception:
        log.warning("Could not reach sim-clock; using wall time")
        return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Orchestrator state tracking (persisted in Postgres)
# ---------------------------------------------------------------------------
async def get_last_run(conn: asyncpg.Connection, job_name: str) -> Optional[datetime]:
    """Get the last time a scheduled job ran (sim-time)."""
    row = await conn.fetchrow("""
        SELECT detail->>'sim_time' as sim_time
        FROM system_audit_log
        WHERE action = 'orchestrator_job_ran' AND detail->>'job_name' = $1
        ORDER BY created_at DESC LIMIT 1
    """, job_name)
    if row and row["sim_time"]:
        return datetime.fromisoformat(row["sim_time"])
    return None


async def record_run(conn: asyncpg.Connection, job_name: str, sim_time: datetime, detail: dict = None) -> None:
    """Record that an orchestrator job ran."""
    await conn.execute(
        "INSERT INTO system_audit_log (actor, action, detail) VALUES ($1, $2, $3)",
        "orchestrator",
        "orchestrator_job_ran",
        json.dumps({"job_name": job_name, "sim_time": sim_time.isoformat(), **(detail or {})}),
    )


# ---------------------------------------------------------------------------
# Meeting triggers
# ---------------------------------------------------------------------------
async def maybe_run_standups(conn: asyncpg.Connection, sim_time: datetime) -> None:
    """Fire standup meetings for all departments on weekdays at STANDUP_HOUR."""
    if sim_time.weekday() >= 5:  # Weekend
        return

    for dept in DEPARTMENTS:
        job_name = f"standup:{dept}:{sim_time.date()}"
        last_run = await get_last_run(conn, job_name)
        if last_run is not None:
            continue  # Already ran for this department today

        log.info("Orchestrator: firing standup for %s", dept)
        try:
            r = await _http.post(f"{MEETING_SIM_URL}/meeting/run", json={
                "meeting_type": "standup",
                "department": dept,
            }, timeout=120.0)
            r.raise_for_status()
            result = r.json()
            await record_run(conn, job_name, sim_time, {"meeting_id": result.get("meeting_id")})
        except Exception as exc:
            log.error("Standup for %s failed: %s", dept, exc)


async def maybe_run_cross_functional(conn: asyncpg.Connection, sim_time: datetime) -> None:
    """Fire cross-functional meeting every CROSS_DEPT_INTERVAL_SIM_DAYS."""
    job_name = "cross_functional"
    last_run = await get_last_run(conn, job_name)
    if last_run is not None:
        days_since = (sim_time - last_run).days
        if days_since < CROSS_DEPT_INTERVAL_SIM_DAYS:
            return

    log.info("Orchestrator: firing cross-functional meeting")
    try:
        r = await _http.post(f"{MEETING_SIM_URL}/meeting/run", json={
            "meeting_type": "cross_functional",
        }, timeout=120.0)
        r.raise_for_status()
        result = r.json()
        await record_run(conn, job_name, sim_time, {"meeting_id": result.get("meeting_id")})
    except Exception as exc:
        log.error("Cross-functional meeting failed: %s", exc)


async def maybe_run_performance_reviews(conn: asyncpg.Connection, sim_time: datetime) -> None:
    """
    Run performance reviews for eligible employees monthly.
    SPEC_CLARIFICATIONS #6: skip < 1 full cycle tenure or dept < 2 members.
    """
    try:
        r = await _http.get(f"{MEETING_SIM_URL}/meetings/pending-performance-reviews", timeout=15.0)
        r.raise_for_status()
        eligible = r.json()
    except Exception as exc:
        log.error("Could not fetch eligible performance reviews: %s", exc)
        return

    for emp in eligible:
        job_name = f"performance_review:{emp['id']}:{sim_time.year}-{sim_time.month}"
        last_run = await get_last_run(conn, job_name)
        if last_run is not None:
            continue  # Already ran this month for this employee

        log.info("Orchestrator: firing performance_review for employee %d (%s)", emp["id"], emp["name"])
        try:
            r = await _http.post(f"{MEETING_SIM_URL}/meeting/run", json={
                "meeting_type": "performance_review",
                "department": emp["department"],
                "target_employee_id": emp["id"],
            }, timeout=120.0)
            r.raise_for_status()
            result = r.json()
            await record_run(conn, job_name, sim_time, {"meeting_id": result.get("meeting_id")})
        except Exception as exc:
            log.error("Performance review for %d failed: %s", emp["id"], exc)


async def maybe_handle_stale_threads(conn: asyncpg.Connection, sim_time: datetime) -> None:
    """
    Find open threads with no activity in STALE_THREAD_THRESHOLD_SIM_DAYS.
    Trigger crisis_response meeting for each.
    """
    threshold = sim_time - timedelta(days=STALE_THREAD_THRESHOLD_SIM_DAYS)
    stale_threads = await conn.fetch("""
        SELECT id, topic, department FROM narrative_threads
        WHERE status IN ('open', 'in_progress')
          AND updated_at < $1
    """, threshold)

    for thread in stale_threads:
        job_name = f"crisis_response:thread:{thread['id']}:{sim_time.date()}"
        last_run = await get_last_run(conn, job_name)
        if last_run is not None:
            continue

        log.info("Orchestrator: stale thread %d ('%s') — triggering crisis_response", thread["id"], thread["topic"])
        try:
            r = await _http.post(f"{MEETING_SIM_URL}/meeting/run", json={
                "meeting_type": "crisis_response",
                "thread_id": thread["id"],
                "extra_context": f"Thread '{thread['topic']}' has had no activity in {STALE_THREAD_THRESHOLD_SIM_DAYS}+ days.",
            }, timeout=120.0)
            r.raise_for_status()
            result = r.json()
            await record_run(conn, job_name, sim_time, {"meeting_id": result.get("meeting_id")})
        except Exception as exc:
            log.error("Crisis response for thread %d failed: %s", thread["id"], exc)


async def maybe_run_payroll(conn: asyncpg.Connection, sim_time: datetime) -> None:
    """Run payroll every PAYROLL_INTERVAL_SIM_DAYS."""
    job_name = "payroll"
    last_run = await get_last_run(conn, job_name)
    if last_run is not None:
        days_since = (sim_time - last_run).days
        if days_since < PAYROLL_INTERVAL_SIM_DAYS:
            return

    cycle_tag = sim_time.strftime("%Y-W%V")  # ISO week
    log.info("Orchestrator: triggering payroll run for cycle %s", cycle_tag)
    try:
        r = await _http.post(f"{ACCOUNTING_ENGINE_URL}/payroll/run", json={
            "idempotency_key": f"payroll:{cycle_tag}"
        }, timeout=60.0)
        r.raise_for_status()
        result = r.json()
        await record_run(conn, job_name, sim_time, result)
    except Exception as exc:
        log.error("Payroll run failed: %s", exc)


async def maybe_run_books_audit(conn: asyncpg.Connection, sim_time: datetime) -> None:
    """Run books audit once per sim-day."""
    job_name = f"books_audit:{sim_time.date()}"
    last_run = await get_last_run(conn, job_name)
    if last_run is not None:
        return

    log.info("Orchestrator: running daily books audit")
    try:
        r = await _http.post(f"{ACCOUNTING_ENGINE_URL}/audit/run", timeout=60.0)
        r.raise_for_status()
        result = r.json()
        await record_run(conn, job_name, sim_time, result)
    except Exception as exc:
        log.error("Books audit failed: %s", exc)


async def maybe_run_kpi_rollup(conn: asyncpg.Connection, sim_time: datetime) -> None:
    """Run KPI daily rollup. Phase 23 wires the kpi-engine; this is the trigger."""
    job_name = f"kpi_rollup:{sim_time.date()}"
    last_run = await get_last_run(conn, job_name)
    if last_run is not None:
        return

    if not KPI_ENGINE_URL:
        return  # Phase 23 not yet wired

    try:
        r = await _http.post(f"{KPI_ENGINE_URL}/rollup", json={
            "snapshot_date": sim_time.isoformat()
        }, timeout=60.0)
        if r.status_code == 200:
            await record_run(conn, job_name, sim_time)
    except Exception:
        pass  # Silent — KPI engine may not be up yet


# ---------------------------------------------------------------------------
# Main tick loop
# ---------------------------------------------------------------------------
async def tick_loop(pool: asyncpg.Pool) -> None:
    """Main orchestrator tick. Runs every TICK_INTERVAL_SECONDS wall-clock seconds."""
    log.info("Orchestrator: tick loop started (interval=%.0fs)", TICK_INTERVAL_SECONDS)
    while True:
        try:
            sim_time = await get_sim_time()
            log.info("Orchestrator tick at sim_time=%s", sim_time.isoformat())

            async with pool.acquire() as conn:
                # Order matches spec §4.3 priority: crisis first, then scheduled, then maintenance
                await maybe_handle_stale_threads(conn, sim_time)
                await maybe_run_performance_reviews(conn, sim_time)
                await maybe_run_standups(conn, sim_time)
                await maybe_run_cross_functional(conn, sim_time)
                await maybe_run_payroll(conn, sim_time)
                await maybe_run_books_audit(conn, sim_time)
                await maybe_run_kpi_rollup(conn, sim_time)

        except Exception as exc:
            log.error("Orchestrator tick error: %s", exc)

        await asyncio.sleep(TICK_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# FastAPI app (primarily for health check + manual trigger)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _http
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    _http = httpx.AsyncClient(timeout=30.0)
    tick_task = asyncio.create_task(tick_loop(_pool))
    log.info("Orchestrator: service ready")
    yield
    tick_task.cancel()
    try:
        await tick_task
    except asyncio.CancelledError:
        pass
    await _http.aclose()
    await _pool.close()


app = FastAPI(
    title="FakeCo Orchestrator",
    description="Central simulation heartbeat — schedules all periodic simulation jobs.",
    version="1.0.0",
    lifespan=lifespan,
)

PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]


@app.get("/health")
async def health():
    return {"status": "ok", "service": "orchestrator"}


@app.get("/status")
async def status(pool: PoolDep):
    """Return recent orchestrator job history."""
    async with pool.acquire() as conn:
        recent = await conn.fetch("""
            SELECT detail->>'job_name' as job_name,
                   detail->>'sim_time' as sim_time,
                   created_at
            FROM system_audit_log
            WHERE action = 'orchestrator_job_ran'
            ORDER BY created_at DESC LIMIT 20
        """)
    return [dict(r) for r in recent]


@app.post("/trigger/{job_name}")
async def manual_trigger(job_name: str, pool: PoolDep):
    """Manually trigger an orchestrator job by name (for testing/debugging)."""
    sim_time = await get_sim_time()
    async with pool.acquire() as conn:
        if job_name == "standup-all":
            await maybe_run_standups(conn, sim_time)
        elif job_name == "cross-functional":
            await maybe_run_cross_functional(conn, sim_time)
        elif job_name == "payroll":
            await maybe_run_payroll(conn, sim_time)
        elif job_name == "books-audit":
            await maybe_run_books_audit(conn, sim_time)
        elif job_name == "crisis-check":
            await maybe_handle_stale_threads(conn, sim_time)
        elif job_name == "performance-reviews":
            await maybe_run_performance_reviews(conn, sim_time)
        else:
            return {"status": "unknown_job", "job": job_name}
    return {"status": "triggered", "job": job_name, "sim_time": sim_time.isoformat()}
