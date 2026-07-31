"""
purge-manager/main.py — FakeCo "Real Appliances"
Phase 29: Scoped + full data purge.

Per PHASE29_PLAN.md (signed off 2026-07-31) and PLAN_REMAINING_PHASES.md's
Phase 29 scope checklist, one endpoint per purge scope plus POST /purge/full.

Every purge endpoint (scoped or full), before any destructive step runs:
  1. Validates the typed confirmation phrase in the request body (second gate).
  2. Calls snapshot-manager's OWN /snapshot/save API (never duplicates its dump
     logic) — if the snapshot save fails, the purge does NOT proceed. This is
     the mandatory-snapshot-before-purge rule from the user's sign-off; it is
     IN ADDITION to the confirmation-phrase gate, not instead of it.
  3. Sets system_maintenance_mode so orchestrator's tick loop no-ops for the
     duration, and best-effort pauses sim-clock.
  4. Performs the purge (appliance bulk-API where one exists, direct-DB
     truncate fallback otherwise, per Option B in PHASE29_PLAN.md §2).
  5. Clears maintenance mode, logs to snapshot_purge_log.

`system_audit_log` and `snapshot_purge_log` themselves are NEVER touched by
any purge scope (confirmed constraint from BUILD_LOG.md, carried forward here)
so there is always a durable record that a purge happened, across every scope.
"""
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated, Optional

import asyncpg
import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","service":"purge-manager","msg":"%(message)s"}'
)
log = logging.getLogger("purge_manager")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql://{os.environ.get('POSTGRES_USER', 'fakeco')}:"
    f"{os.environ.get('POSTGRES_PASSWORD', 'fakeco')}@"
    f"postgres/{os.environ.get('POSTGRES_DB', 'fakeco')}",
)
SNAPSHOT_MANAGER_URL = os.environ.get("SNAPSHOT_MANAGER_URL", "http://snapshot-manager:8000")
SIM_CLOCK_URL = os.environ.get("SIM_CLOCK_URL", "http://sim-clock:8000")

ZAMMAD_URL = os.environ.get("ZAMMAD_URL", "http://zammad-nginx:8080")
ZAMMAD_ADMIN_TOKEN = os.environ.get("ZAMMAD_ADMIN_TOKEN", "")
WIKIJS_URL = os.environ.get("WIKIJS_URL", "http://wikijs:3000")
WIKIJS_ADMIN_TOKEN = os.environ.get("WIKIJS_ADMIN_TOKEN", "")
MATTERMOST_URL = os.environ.get("MATTERMOST_URL", "http://mattermost:8065")
MATTERMOST_ADMIN_TOKEN = os.environ.get("MATTERMOST_ADMIN_TOKEN", "")

AKAUNTING_DB_HOST = "akaunting-db"
AKAUNTING_DB_NAME = "akaunting"
AKAUNTING_DB_USER = "akaunting"
AKAUNTING_DB_PASSWORD = os.environ.get("AKAUNTING_DB_PASSWORD", "")

# Scope -> required typed confirmation phrase
SCOPE_PHRASES = {
    "emails": "PURGE EMAILS",
    "chat": "PURGE CHAT",
    "tickets": "PURGE TICKETS",
    "wiki": "PURGE WIKI",
    "meetings_narrative": "PURGE MEETINGS AND NARRATIVE MEMORY",
    "accounting": "PURGE ACCOUNTING LEDGER",
    "external_world": "PURGE EXTERNAL WORLD",
    "kpi_history": "PURGE KPI HISTORY",
    "roster": "PURGE ROSTER",
    "company_direction": "PURGE COMPANY DIRECTION",
}
FULL_PURGE_PHRASE = "PURGE EVERYTHING"

_pool: Optional[asyncpg.Pool] = None
_http: Optional[httpx.AsyncClient] = None


async def get_pool() -> asyncpg.Pool:
    return _pool


PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _http
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    _http = httpx.AsyncClient(timeout=60.0)
    log.info("purge-manager: service ready")
    yield
    await _pool.close()
    await _http.aclose()


app = FastAPI(title="purge-manager", lifespan=lifespan)


class ScopeRequest(BaseModel):
    confirm: str


async def set_maintenance_mode(pool: asyncpg.Pool, enabled: bool, reason: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO system_maintenance_mode (id, enabled, reason, set_by, set_at, updated_at)
            VALUES (1, $1, $2, 'purge-manager', now(), now())
            ON CONFLICT (id) DO UPDATE
                SET enabled = $1, reason = $2, set_by = 'purge-manager', set_at = now(), updated_at = now()
            """,
            enabled, reason,
        )


async def pause_sim_clock_best_effort() -> None:
    try:
        await _http.post(f"{SIM_CLOCK_URL}/set_speed", json={"speed_multiplier": 0.1})
    except Exception as exc:
        log.warning("purge-manager: best-effort sim-clock pause failed (non-fatal): %s", exc)


async def resume_sim_clock_best_effort() -> None:
    try:
        await _http.post(f"{SIM_CLOCK_URL}/set_speed", json={"speed_multiplier": 1.0})
    except Exception as exc:
        log.warning("purge-manager: best-effort sim-clock resume failed (non-fatal): %s", exc)


async def log_op(pool: asyncpg.Pool, operation: str, scope: Optional[str], status: str,
                  detail: dict, log_id: Optional[int] = None) -> int:
    async with pool.acquire() as conn:
        if log_id is None:
            row = await conn.fetchrow(
                """
                INSERT INTO snapshot_purge_log (operation, scope, status, detail, started_at)
                VALUES ($1, $2, $3, $4::jsonb, now())
                RETURNING id
                """,
                operation, scope, status, json.dumps(detail),
            )
            return row["id"]
        await conn.execute(
            "UPDATE snapshot_purge_log SET status=$1, detail=$2::jsonb, finished_at=now() WHERE id=$3",
            status, json.dumps(detail), log_id,
        )
        return log_id


async def mandatory_pre_purge_snapshot(scope_label: str) -> dict:
    """Calls snapshot-manager's own /snapshot/save. Raises HTTPException on failure —
    purge must never proceed if this fails (user sign-off decision #1)."""
    try:
        resp = await _http.post(
            f"{SNAPSHOT_MANAGER_URL}/snapshot/save",
            json={"label": f"pre_purge_{scope_label}"},
            timeout=180.0,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Mandatory pre-purge snapshot could not be reached — purge aborted, nothing was touched: {exc}",
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Mandatory pre-purge snapshot FAILED (status {resp.status_code}) — "
                   f"purge aborted, nothing was touched: {resp.text[:500]}",
        )
    return resp.json()


# ---------------------------------------------------------------------------
# Scope implementations — appliance bulk-API where practical, direct-DB
# truncate fallback otherwise (Option B in PHASE29_PLAN.md §2).
# ---------------------------------------------------------------------------
async def purge_emails(pool: asyncpg.Pool) -> dict:
    # No bulk mailbox-wipe API in docker-mailserver's `setup` CLI without exec;
    # narrower v1 scope: clear per-employee mailbox_address linkage so downstream
    # services stop treating employees as having a working mailbox. Full Maildir
    # wipe is a snapshot/restore-shaped operation (needs mailserver stop/start),
    # intentionally left to a future enhancement rather than duplicated here.
    async with pool.acquire() as conn:
        n = await conn.fetchval("UPDATE employees SET mailbox_address = NULL WHERE mailbox_address IS NOT NULL RETURNING 1")
    return {"note": "mailbox_address links cleared; raw Maildir wipe not performed by this scope "
                     "(use snapshot-manager restore-from-empty-snapshot for a full mail wipe)"}


async def purge_chat(pool: asyncpg.Pool) -> dict:
    headers = {"Authorization": f"Bearer {MATTERMOST_ADMIN_TOKEN}"}
    deleted_posts, deleted_channels, errors = 0, 0, []
    try:
        resp = await _http.get(f"{MATTERMOST_URL}/api/v4/teams", headers=headers)
        resp.raise_for_status()
        for team in resp.json():
            ch_resp = await _http.get(f"{MATTERMOST_URL}/api/v4/teams/{team['id']}/channels", headers=headers)
            ch_resp.raise_for_status()
            for ch in ch_resp.json():
                posts_resp = await _http.get(
                    f"{MATTERMOST_URL}/api/v4/channels/{ch['id']}/posts", headers=headers
                )
                if posts_resp.status_code == 200:
                    for post_id in posts_resp.json().get("order", []):
                        d = await _http.delete(f"{MATTERMOST_URL}/api/v4/posts/{post_id}", headers=headers)
                        if d.status_code in (200, 201):
                            deleted_posts += 1
    except Exception as exc:
        errors.append(str(exc))
    return {"deleted_posts": deleted_posts, "errors": errors}


async def purge_tickets(pool: asyncpg.Pool) -> dict:
    headers = {"Authorization": f"Token token={ZAMMAD_ADMIN_TOKEN}"}
    deleted, errors = 0, []
    try:
        resp = await _http.get(f"{ZAMMAD_URL}/api/v1/tickets", headers=headers)
        resp.raise_for_status()
        for t in resp.json():
            d = await _http.delete(f"{ZAMMAD_URL}/api/v1/tickets/{t['id']}", headers=headers)
            if d.status_code in (200, 204):
                deleted += 1
    except Exception as exc:
        errors.append(str(exc))
    return {"deleted_tickets": deleted, "errors": errors}


async def purge_wiki(pool: asyncpg.Pool) -> dict:
    headers = {"Authorization": f"Bearer {WIKIJS_ADMIN_TOKEN}", "Content-Type": "application/json"}
    deleted, errors = 0, []
    try:
        list_q = {"query": "{ pages { list { id } } }"}
        resp = await _http.post(f"{WIKIJS_URL}/graphql", json=list_q, headers=headers)
        resp.raise_for_status()
        pages = (resp.json().get("data") or {}).get("pages", {}).get("list", []) or []
        for p in pages:
            del_q = {"query": f"mutation {{ pages {{ delete(id: {p['id']}) {{ responseResult {{ succeeded }} }} }} }}"}
            d = await _http.post(f"{WIKIJS_URL}/graphql", json=del_q, headers=headers)
            if d.status_code == 200:
                deleted += 1
    except Exception as exc:
        errors.append(str(exc))
    return {"deleted_pages": deleted, "errors": errors}


async def purge_meetings_narrative(pool: asyncpg.Pool) -> dict:
    # FK structure (Phase 13, verified) cascades most of this from narrative_threads/meetings.
    async with pool.acquire() as conn:
        async with conn.transaction():
            counts = {}
            for table in ["pending_reactions", "pending_approvals", "action_items",
                          "narrative_events", "meetings", "narrative_threads"]:
                counts[table] = await conn.fetchval(f"SELECT count(*) FROM {table}")
                await conn.execute(f"TRUNCATE TABLE {table} CASCADE")
    return {"rows_truncated": counts}


async def purge_accounting(pool: asyncpg.Pool) -> dict:
    # Akaunting has no bulk-wipe API — direct MariaDB truncate fallback (Option B).
    # transactions/documents/contacts are Akaunting's own core tables; re-run of
    # akaunting-init's idempotent chart-of-accounts setup is left to the operator
    # after this scope, matching PLAN_REMAINING_PHASES.md's Phase 29 note.
    import subprocess
    sql = (
        "SET FOREIGN_KEY_CHECKS=0; "
        "TRUNCATE TABLE transactions; "
        "TRUNCATE TABLE documents; "
        "TRUNCATE TABLE document_items; "
        "TRUNCATE TABLE document_transactions; "
        "SET FOREIGN_KEY_CHECKS=1;"
    )
    cmd = ["mysql", "-h", AKAUNTING_DB_HOST, "-u", AKAUNTING_DB_USER,
           f"-p{AKAUNTING_DB_PASSWORD}", AKAUNTING_DB_NAME, "-e", sql]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return {"returncode": proc.returncode, "stderr": proc.stderr[-500:] if proc.stderr else ""}


async def purge_external_world(pool: asyncpg.Pool) -> dict:
    async with pool.acquire() as conn:
        async with conn.transaction():
            counts = {}
            for table in ["customers", "market_benchmark"]:
                counts[table] = await conn.fetchval(f"SELECT count(*) FROM {table}")
                await conn.execute(f"TRUNCATE TABLE {table} CASCADE")
    return {"rows_truncated": counts}


async def purge_kpi_history(pool: asyncpg.Pool) -> dict:
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM kpi_snapshots")
        await conn.execute("TRUNCATE TABLE kpi_snapshots")
    return {"rows_truncated": {"kpi_snapshots": count}}


async def purge_roster(pool: asyncpg.Pool) -> dict:
    # Trickiest scope per PLAN_REMAINING_PHASES.md — appliance account
    # de-provisioning ahead of a full API build-out is out of v1 scope (no
    # FastAPI surface exists yet on `provisioning`, which is CLI-only); this
    # scope truncates the roster row set (cascades to dependent narrative rows
    # via existing FKs) and reports that appliance accounts are ORPHANED, not
    # deleted, until `provisioning`'s CLI is re-run — flagged explicitly rather
    # than silently claimed as complete.
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM employees")
        await conn.execute("TRUNCATE TABLE employees CASCADE")
    return {
        "rows_truncated": {"employees": count},
        "note": "Appliance accounts (Mattermost/Zammad/Wiki.js/mailboxes) for the purged "
                "roster were NOT de-provisioned by this call — re-run `provisioning` CLI "
                "to reseed a fresh roster; stale appliance accounts should be cleaned up "
                "manually or by a future de-provisioning enhancement.",
    }


async def purge_company_direction(pool: asyncpg.Pool) -> dict:
    # Real column names are content/version/is_current/created_at/created_by
    # (verified against narrative-db/migrations/002_narrative_core.sql — an
    # earlier draft of this function used made-up column names and was caught
    # during Phase 29's live disposable-environment verification).
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE company_directives")
        await conn.execute(
            "INSERT INTO company_directives (content, version, is_current, created_by) "
            "VALUES ($1, 1, TRUE, 'purge-manager')",
            "Default company direction (post-purge reset).",
        )
    return {"note": "company_directives reset to hardcoded default row"}


SCOPE_FUNCS = {
    "emails": purge_emails,
    "chat": purge_chat,
    "tickets": purge_tickets,
    "wiki": purge_wiki,
    "meetings_narrative": purge_meetings_narrative,
    "accounting": purge_accounting,
    "external_world": purge_external_world,
    "kpi_history": purge_kpi_history,
    "roster": purge_roster,
    "company_direction": purge_company_direction,
}


async def _run_scope(scope: str, pool: asyncpg.Pool) -> dict:
    snapshot_result = await mandatory_pre_purge_snapshot(scope)
    log_id = await log_op(pool, "purge_scope", scope, "started", {"pre_purge_snapshot": snapshot_result["snapshot_name"]})
    await set_maintenance_mode(pool, True, f"purge scope {scope}")
    await pause_sim_clock_best_effort()
    try:
        result = await SCOPE_FUNCS[scope](pool)
        await log_op(pool, "purge_scope", scope, "succeeded",
                     {"pre_purge_snapshot": snapshot_result["snapshot_name"], "result": result}, log_id)
        return {"scope": scope, "pre_purge_snapshot": snapshot_result["snapshot_name"], "result": result}
    except Exception as exc:
        await log_op(pool, "purge_scope", scope, "failed",
                     {"pre_purge_snapshot": snapshot_result["snapshot_name"], "error": str(exc)}, log_id)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        await resume_sim_clock_best_effort()
        await set_maintenance_mode(pool, False, None)


def _make_scope_endpoint(scope: str):
    async def endpoint(req: ScopeRequest, pool: PoolDep):
        expected = SCOPE_PHRASES[scope]
        if req.confirm != expected:
            raise HTTPException(status_code=400, detail=f"confirm must be the exact phrase '{expected}'")
        return await _run_scope(scope, pool)
    return endpoint


for _scope in SCOPE_FUNCS:
    app.add_api_route(f"/purge/{_scope}", _make_scope_endpoint(_scope), methods=["POST"])


@app.post("/purge/full")
async def purge_full(req: ScopeRequest, pool: PoolDep):
    if req.confirm != FULL_PURGE_PHRASE:
        raise HTTPException(status_code=400, detail=f"confirm must be the exact phrase '{FULL_PURGE_PHRASE}'")

    snapshot_result = await mandatory_pre_purge_snapshot("full")
    log_id = await log_op(pool, "purge_full", None, "started", {"pre_purge_snapshot": snapshot_result["snapshot_name"]})
    await set_maintenance_mode(pool, True, "full purge")
    await pause_sim_clock_best_effort()

    results = {}
    overall_ok = True
    try:
        # Order matters for roster: de-provision-adjacent scopes before truncating
        # the employees row that names them (per PHASE29_PLAN.md §4 item 5) —
        # run roster LAST so meetings/narrative/kpi rows referencing employees are
        # already cleared, minimizing what roster's own CASCADE has to do.
        ordered_scopes = ["emails", "chat", "tickets", "wiki", "meetings_narrative",
                          "accounting", "external_world", "kpi_history",
                          "company_direction", "roster"]
        for scope in ordered_scopes:
            try:
                results[scope] = await SCOPE_FUNCS[scope](pool)
            except Exception as exc:
                results[scope] = {"error": str(exc)}
                overall_ok = False

        status = "succeeded" if overall_ok else "partial_failure"
        await log_op(pool, "purge_full", None, status,
                     {"pre_purge_snapshot": snapshot_result["snapshot_name"], "results": results}, log_id)
        return {"pre_purge_snapshot": snapshot_result["snapshot_name"], "status": status, "results": results}
    finally:
        await resume_sim_clock_best_effort()
        await set_maintenance_mode(pool, False, None)


@app.get("/health")
async def health():
    return {"status": "ok"}
