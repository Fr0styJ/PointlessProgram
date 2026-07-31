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
import hashlib
import json
import logging
import os
import random
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

# Phase 19: PTO scheduler config
PTO_CHECK_PROBABILITY = float(os.environ.get("PTO_DAILY_PROBABILITY", "0.01"))  # per active employee, per sim-day
PTO_MIN_GAP_DAYS = int(os.environ.get("PTO_MIN_GAP_DAYS", "45"))  # min days between an employee's PTO windows
PTO_DURATION_MIN_DAYS = int(os.environ.get("PTO_DURATION_MIN_DAYS", "3"))
PTO_DURATION_MAX_DAYS = int(os.environ.get("PTO_DURATION_MAX_DAYS", "7"))
MAILSERVER_CONTAINER = os.environ.get("MAILSERVER_CONTAINER", "fakeco-mailserver")
MAILSERVER_DOMAIN = os.environ.get("MAILSERVER_DOMAIN", "fakecorp.internal")
MATTERMOST_URL = os.environ.get("MATTERMOST_URL", "http://mattermost:8065")
MATTERMOST_ADMIN_TOKEN = os.environ.get("MATTERMOST_ADMIN_TOKEN", "")

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
# Phase 19: PTO / out-of-office
#
# Sieve research finding (see BUILD_LOG.md Phase 19 entry): docker-mailserver's
# `setup` CLI has NO subcommand for Sieve script management (`setup help` only
# exposes email/alias/dkim/relay/debug/etc. — confirmed by inspecting a live
# container). docker-mailserver *does* ship Dovecot Pigeonhole and its
# `doveadm sieve` CLI plugin inside the same container, though, so rather than
# hand-rolling the raw ManageSieve wire protocol (RFC 5804) against port 4190,
# we drive `doveadm sieve put/activate/deactivate/delete -u <user>` via the
# same `docker exec fakeco-mailserver ...` pattern provisioning already uses
# for `setup email` — genuinely native Sieve/Pigeonhole, just invoked through
# doveadm instead of `setup`. This is equivalent to (and simpler + more
# reliable than) a raw ManageSieve client: doveadm's sieve plugin talks to the
# exact same per-user script storage a ManageSieve client would.
# ---------------------------------------------------------------------------
VACATION_SIEVE_SCRIPT_NAME = "pto-vacation"


def _vacation_sieve_script(employee_name: str, reason: str, end_sim_time: datetime) -> str:
    """A real Sieve vacation-responder script (RFC 5230)."""
    safe_reason = (reason or "PTO").replace('"', "'")
    until = end_sim_time.date().isoformat()
    return (
        'require ["vacation"];\n'
        "vacation\n"
        '    :days 1\n'
        f'    :subject "Out of office — {employee_name}"\n'
        f'    "Hi,\\n\\nI am currently out of office ({safe_reason}) until {until}. '
        'I will respond when I am back.\\n\\nThanks,\\n' + employee_name + '";\n'
    )


async def _docker_exec(*args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "docker", "exec", "-i", MAILSERVER_CONTAINER, *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def _docker_exec_stdin(stdin_data: bytes, *args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "docker", "exec", "-i", MAILSERVER_CONTAINER, *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input=stdin_data)
    return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def activate_vacation_sieve(mailbox_address: str, employee_name: str, reason: str, end_sim_time: datetime) -> None:
    """Install + activate a real Sieve vacation responder on PTO start."""
    script = _vacation_sieve_script(employee_name, reason, end_sim_time)
    rc, out, err = await _docker_exec_stdin(
        script.encode(), "doveadm", "sieve", "put", "-u", mailbox_address, VACATION_SIEVE_SCRIPT_NAME
    )
    if rc != 0:
        raise RuntimeError(f"doveadm sieve put failed for {mailbox_address}: {err or out}")
    rc, out, err = await _docker_exec("doveadm", "sieve", "activate", "-u", mailbox_address, VACATION_SIEVE_SCRIPT_NAME)
    if rc != 0:
        raise RuntimeError(f"doveadm sieve activate failed for {mailbox_address}: {err or out}")
    log.info("PTO: activated Sieve vacation responder for %s", mailbox_address)


async def deactivate_vacation_sieve(mailbox_address: str) -> None:
    """
    Remove the Sieve vacation responder on PTO end. Tolerant of already-gone state.

    BUG FOUND during Phase 19 verification: `doveadm sieve deactivate -u <user> <name>` (passing
    a script name, mirroring `activate`'s syntax) is NOT the same command as plain
    `doveadm sieve deactivate -u <user>` — `deactivate` takes no script-name argument at all; it
    always deactivates whatever is currently active. Passing an extra arg made it silently do
    nothing (still exit non-zero further down the line), and the subsequent `sieve delete` then
    failed with "Cannot delete the active Sieve script" — so PTO-end reversion looked like it
    logged success but the vacation responder was, in fact, still ACTIVE afterward (confirmed via
    `doveadm sieve list` still showing it ACTIVE post-revert). Fixed: no script-name arg to
    `deactivate`.
    """
    await _docker_exec("doveadm", "sieve", "deactivate", "-u", mailbox_address)
    rc, out, err = await _docker_exec("doveadm", "sieve", "delete", "-u", mailbox_address, VACATION_SIEVE_SCRIPT_NAME)
    if rc != 0 and "unknown script" not in (err + out).lower() and "doesn't exist" not in (err + out).lower():
        log.warning("PTO: sieve delete for %s returned rc=%d: %s", mailbox_address, rc, err or out)
    log.info("PTO: deactivated Sieve vacation responder for %s", mailbox_address)


async def set_mattermost_oof_status(mattermost_id: str, end_sim_time: datetime) -> None:
    """
    Real Mattermost custom status via PUT /api/v4/users/{id}/status/custom, using an
    ephemeral admin-issued personal access token to act as the employee — same
    impersonation pattern as human-bridge's post_mattermost_as_employee.
    """
    if not MATTERMOST_ADMIN_TOKEN or not mattermost_id:
        return
    async with httpx.AsyncClient(timeout=15.0) as http:
        r = await http.post(
            f"{MATTERMOST_URL}/api/v4/users/{mattermost_id}/tokens",
            headers={"Authorization": f"Bearer {MATTERMOST_ADMIN_TOKEN}"},
            json={"description": "orchestrator PTO status token"},
        )
        r.raise_for_status()
        token = r.json()["token"]
        token_id = r.json()["id"]
        try:
            r2 = await http.put(
                f"{MATTERMOST_URL}/api/v4/users/{mattermost_id}/status/custom",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "emoji": "palm_tree",
                    "text": "Out of Office",
                    "duration": "date_and_time",
                    "expires_at": end_sim_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                },
            )
            r2.raise_for_status()
        finally:
            # Real bug found here during Phase 19 verification (and present in human-bridge's
            # post_mattermost_as_employee, copied from the same pattern): Mattermost has no
            # `DELETE /users/{user_id}/tokens/{token_id}` route — that 404s silently (this code
            # doesn't check the status, so the ephemeral token was never actually being revoked).
            # The real revoke endpoint is `POST /users/tokens/revoke` with a `{"token_id": ...}`
            # body. Verified directly: DELETE returned 404 and the token was still listed under
            # GET /users/{id}/tokens afterward; switching to POST /tokens/revoke actually removes it.
            await http.post(
                f"{MATTERMOST_URL}/api/v4/users/tokens/revoke",
                headers={"Authorization": f"Bearer {MATTERMOST_ADMIN_TOKEN}"},
                json={"token_id": token_id},
            )
    log.info("PTO: set Mattermost OOO custom status for user %s", mattermost_id)


async def clear_mattermost_oof_status(mattermost_id: str) -> None:
    """Revert the custom status on PTO end (unset via PUT /status/custom/unset)."""
    if not MATTERMOST_ADMIN_TOKEN or not mattermost_id:
        return
    async with httpx.AsyncClient(timeout=15.0) as http:
        r = await http.post(
            f"{MATTERMOST_URL}/api/v4/users/{mattermost_id}/tokens",
            headers={"Authorization": f"Bearer {MATTERMOST_ADMIN_TOKEN}"},
            json={"description": "orchestrator PTO status token"},
        )
        r.raise_for_status()
        token = r.json()["token"]
        token_id = r.json()["id"]
        try:
            r2 = await http.delete(
                f"{MATTERMOST_URL}/api/v4/users/{mattermost_id}/status/custom",
                headers={"Authorization": f"Bearer {token}"},
            )
            r2.raise_for_status()
        finally:
            # Real bug found here during Phase 19 verification (and present in human-bridge's
            # post_mattermost_as_employee, copied from the same pattern): Mattermost has no
            # `DELETE /users/{user_id}/tokens/{token_id}` route — that 404s silently (this code
            # doesn't check the status, so the ephemeral token was never actually being revoked).
            # The real revoke endpoint is `POST /users/tokens/revoke` with a `{"token_id": ...}`
            # body. Verified directly: DELETE returned 404 and the token was still listed under
            # GET /users/{id}/tokens afterward; switching to POST /tokens/revoke actually removes it.
            await http.post(
                f"{MATTERMOST_URL}/api/v4/users/tokens/revoke",
                headers={"Authorization": f"Bearer {MATTERMOST_ADMIN_TOKEN}"},
                json={"token_id": token_id},
            )
    log.info("PTO: cleared Mattermost OOO custom status for user %s", mattermost_id)


async def maybe_schedule_pto(conn: asyncpg.Connection, sim_time: datetime) -> None:
    """
    Deterministic-per-run (seeded on employee id + sim date, so a given tick's decision is
    reproducible) daily probability check per active employee: if not currently on PTO and
    not within PTO_MIN_GAP_DAYS of their last window, roll PTO_CHECK_PROBABILITY to start a
    new PTO_DURATION_MIN..MAX-day window starting today.
    """
    job_name = f"pto_schedule_check:{sim_time.date()}"
    if await get_last_run(conn, job_name) is not None:
        return  # already rolled today

    employees = await conn.fetch("SELECT id, name FROM employees WHERE status = 'active'")
    for emp in employees:
        last_window = await conn.fetchrow("""
            SELECT end_sim_time FROM pto_calendar
            WHERE employee_id = $1 ORDER BY end_sim_time DESC LIMIT 1
        """, emp["id"])
        if last_window and (sim_time - last_window["end_sim_time"]).days < PTO_MIN_GAP_DAYS:
            continue
        on_pto_now = await conn.fetchval("""
            SELECT 1 FROM pto_calendar WHERE employee_id = $1
              AND start_sim_time <= $2 AND end_sim_time > $2 LIMIT 1
        """, emp["id"], sim_time)
        if on_pto_now:
            continue

        # Deterministic RNG seeded per (employee, sim-date) so re-running the same tick
        # never double-rolls, and results are reproducible for testing.
        seed = int(hashlib.sha256(f"pto:{emp['id']}:{sim_time.date()}".encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        if rng.random() >= PTO_CHECK_PROBABILITY:
            continue

        duration_days = rng.randint(PTO_DURATION_MIN_DAYS, PTO_DURATION_MAX_DAYS)
        start = sim_time
        end = sim_time + timedelta(days=duration_days)
        await conn.execute("""
            INSERT INTO pto_calendar (employee_id, start_sim_time, end_sim_time, reason)
            VALUES ($1, $2, $3, $4)
        """, emp["id"], start, end, "Scheduled time off")
        log.info("PTO: scheduled %s out from %s to %s", emp["name"], start.date(), end.date())

    await record_run(conn, job_name, sim_time)


async def maybe_apply_pto_effects(conn: asyncpg.Connection, sim_time: datetime) -> None:
    """
    Per tick: apply the real Sieve + Mattermost effects for any PTO window that has started
    but whose start-effects haven't been applied yet, and revert (+ fire a catching-up burst)
    for any window whose end-effects haven't been applied yet.
    """
    starting = await conn.fetch("""
        SELECT p.id, p.employee_id, p.end_sim_time, p.reason,
               e.name, e.mailbox_address, e.mattermost_id
        FROM pto_calendar p JOIN employees e ON e.id = p.employee_id
        WHERE p.start_sim_time <= $1 AND p.end_sim_time > $1
    """, sim_time)
    for row in starting:
        job_name = f"pto_start_effects:{row['id']}"
        if await get_last_run(conn, job_name) is not None:
            continue
        try:
            if row["mailbox_address"]:
                await activate_vacation_sieve(row["mailbox_address"], row["name"], row["reason"], row["end_sim_time"])
            if row["mattermost_id"]:
                await set_mattermost_oof_status(row["mattermost_id"], row["end_sim_time"])
            await record_run(conn, job_name, sim_time, {"employee_id": row["employee_id"], "pto_id": row["id"]})
        except Exception as exc:
            log.error("PTO start-effects failed for employee %d: %s", row["employee_id"], exc)

    ending = await conn.fetch("""
        SELECT p.id, p.employee_id, e.name, e.mailbox_address, e.mattermost_id
        FROM pto_calendar p JOIN employees e ON e.id = p.employee_id
        WHERE p.end_sim_time <= $1
    """, sim_time)
    for row in ending:
        job_name = f"pto_end_effects:{row['id']}"
        if await get_last_run(conn, job_name) is not None:
            continue
        try:
            if row["mailbox_address"]:
                await deactivate_vacation_sieve(row["mailbox_address"])
            if row["mattermost_id"]:
                await clear_mattermost_oof_status(row["mattermost_id"])
            await record_run(conn, job_name, sim_time, {"employee_id": row["employee_id"], "pto_id": row["id"]})
            await fire_catching_up_burst(conn, sim_time, row["employee_id"], row["name"])
        except Exception as exc:
            log.error("PTO end-effects failed for employee %d: %s", row["employee_id"], exc)


async def is_employee_on_pto(conn: asyncpg.Connection, employee_id: int, sim_time: datetime) -> bool:
    return bool(await conn.fetchval("""
        SELECT 1 FROM pto_calendar WHERE employee_id = $1
          AND start_sim_time <= $2 AND end_sim_time > $2 LIMIT 1
    """, employee_id, sim_time))


async def fire_catching_up_burst(conn: asyncpg.Connection, sim_time: datetime, employee_id: int, employee_name: str) -> None:
    """
    On the tick an employee's PTO window just ended: one extra burst of routine activity for
    them specifically, via a pending_reactions row targeting them in their department's most
    recently active open thread (reusing the same mechanism human-bridge/meeting-simulator's
    continuity loop already consumes — no new consumption path needed).
    """
    emp = await conn.fetchrow("SELECT department FROM employees WHERE id = $1", employee_id)
    if emp is None:
        return
    thread_id = await conn.fetchval("""
        SELECT id FROM narrative_threads WHERE department = $1 AND status = 'open'
        ORDER BY updated_at DESC LIMIT 1
    """, emp["department"])
    if thread_id is None:
        thread_id = await conn.fetchval("""
            INSERT INTO narrative_threads (topic, department, status, summary)
            VALUES ($1, $2, 'open', '') RETURNING id
        """, f"{employee_name} catching up after PTO", emp["department"])
    event_id = await conn.fetchval("""
        INSERT INTO narrative_events (thread_id, employee_id, origin, source_type, source_ref, short_summary)
        VALUES ($1, $2, 'external', 'external', $3, $4)
        RETURNING id
    """, thread_id, employee_id, f"pto_return:{employee_id}:{sim_time.isoformat()}",
        f"{employee_name} is back from PTO and catching up.")
    await conn.execute("""
        INSERT INTO pending_reactions (thread_id, target_employee_id, triggering_event_id, status)
        VALUES ($1, $2, $3, 'pending')
    """, thread_id, employee_id, event_id)
    log.info("PTO: fired catching-up burst for %s", employee_name)


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
        if await is_employee_on_pto(conn, emp["id"], sim_time):
            log.info("Orchestrator: skipping performance_review for %s — on PTO", emp["name"])
            continue

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
                await maybe_schedule_pto(conn, sim_time)
                await maybe_apply_pto_effects(conn, sim_time)
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
        elif job_name == "pto-schedule":
            await maybe_schedule_pto(conn, sim_time)
        elif job_name == "pto-effects":
            await maybe_apply_pto_effects(conn, sim_time)
        else:
            return {"status": "unknown_job", "job": job_name}
    return {"status": "triggered", "job": job_name, "sim_time": sim_time.isoformat()}
