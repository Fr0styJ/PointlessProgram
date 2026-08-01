"""
kpi-engine/main.py — FakeCo "Real Appliances"
Phase 23: KPI scoreboards + performance-review formula.

Spec §12.1 (KPI scoreboards), §12.2 (performance review cycle):
- Deterministic daily rollup across Zammad, Wiki.js, Mattermost, Akaunting.
  ZERO LLM calls anywhere in this path — same principle as accounting-engine (§10.1).
- One row per (snapshot_date, entity_type, entity_id, metric) written to `kpi_snapshots`,
  upserted via ON CONFLICT DO UPDATE (the table's UNIQUE constraint makes this naturally
  idempotent — safe to re-run a rollup for the same day).
- Performance-review formula: rank employees within department by a composite KPI score;
  top quartile +KPI_REVIEW_TOP_RAISE_PCT, second quartile +KPI_REVIEW_SECOND_RAISE_PCT,
  rest +0%. Applied via accounting-engine's existing `/payroll/raise` endpoint (raises
  apply immediately, no approval needed — spec §10.3) UNLESS KPI_REVIEW_APPROVAL_MODE=on,
  in which case proposals are queued into `pending_approvals` instead of auto-applied.
- SPEC_CLARIFICATIONS #6: cold-start exemption — skip employees with <1 full review cycle
  tenure, and skip departments with <2 active members (mirrors meeting-simulator's
  `/meetings/pending-performance-reviews` eligibility check so Phase 24 sees consistent data).
- Underperformance handling (opening a `performance_review` meeting instead of a cut) is
  Phase 24's job — this service only exposes the data via GET /reviews/due.

Exposed as a FastAPI service, manually triggered like every other custom service in this
project (POST /rollup/run, POST /reviews/run) — the orchestrator will call these on its
own schedule once Phase 24/wiring lands.
"""
import logging
import os
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from typing import Optional, Annotated

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","service":"kpi-engine","msg":"%(message)s"}'
)
log = logging.getLogger("kpi_engine")

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

ZAMMAD_URL = os.environ.get("ZAMMAD_URL", "http://zammad-nginx:8080")
ZAMMAD_ADMIN_TOKEN = os.environ.get("ZAMMAD_ADMIN_TOKEN", "")

WIKIJS_URL = os.environ.get("WIKIJS_URL", "http://wikijs:3000")
WIKIJS_ADMIN_TOKEN = os.environ.get("WIKIJS_ADMIN_TOKEN", "")

MATTERMOST_URL = os.environ.get("MATTERMOST_URL", "http://mattermost:8065")
MATTERMOST_ADMIN_TOKEN = os.environ.get("MATTERMOST_ADMIN_TOKEN", "")

AKAUNTING_URL = os.environ.get("AKAUNTING_URL", "http://akaunting")
AKAUNTING_ADMIN_EMAIL = os.environ.get("AKAUNTING_ADMIN_EMAIL", "")
AKAUNTING_ADMIN_PASSWORD = os.environ.get("AKAUNTING_ADMIN_PASSWORD", "")
AKAUNTING_COMPANY_ID = int(os.environ.get("AKAUNTING_COMPANY_ID", "1"))

ACCOUNTING_ENGINE_URL = os.environ.get("ACCOUNTING_ENGINE_URL", "http://accounting-engine:8000")

# Performance-review formula tuning (tunable via env, matching accounting-engine's
# IC_AUTO_APPROVE_LIMIT-style pattern).
KPI_REVIEW_TOP_RAISE_PCT = Decimal(os.environ.get("KPI_REVIEW_TOP_RAISE_PCT", "0.05"))
KPI_REVIEW_SECOND_RAISE_PCT = Decimal(os.environ.get("KPI_REVIEW_SECOND_RAISE_PCT", "0.02"))
KPI_REVIEW_MIN_TENURE_DAYS = int(os.environ.get("KPI_REVIEW_MIN_TENURE_DAYS", "90"))
KPI_REVIEW_MIN_DEPT_SIZE = int(os.environ.get("KPI_REVIEW_MIN_DEPT_SIZE", "2"))
KPI_REVIEW_LOOKBACK_DAYS = int(os.environ.get("KPI_REVIEW_LOOKBACK_DAYS", "30"))
KPI_REVIEW_UNDERPERFORM_PERCENTILE = Decimal(os.environ.get("KPI_REVIEW_UNDERPERFORM_PERCENTILE", "0.10"))
# "review & approve" toggle — off (auto-apply) by default per spec §12.2 ("runs fully
# automatically by default; dashboard toggle available for review & approve mode").
# This env var is now only the SEED default for kpi_engine_config's single row
# (Phase 35 migration 011) — the live value is read from that table so the
# dashboard's toggle can flip it without a container restart. See
# get_review_approval_mode() / set_review_approval_mode() below.
KPI_REVIEW_APPROVAL_MODE_ENV_DEFAULT = os.environ.get("KPI_REVIEW_APPROVAL_MODE", "off").lower() in ("on", "true", "1")

# Composite score weights — plain-code, deterministic, no LLM (spec §12.1/12.2).
KPI_WEIGHT_TICKETS_RESOLVED = Decimal(os.environ.get("KPI_WEIGHT_TICKETS_RESOLVED", "1.0"))
KPI_WEIGHT_WIKI_PAGES = Decimal(os.environ.get("KPI_WEIGHT_WIKI_PAGES", "1.0"))
KPI_WEIGHT_CHAT_MESSAGES = Decimal(os.environ.get("KPI_WEIGHT_CHAT_MESSAGES", "0.1"))
KPI_WEIGHT_RESOLUTION_HOURS = Decimal(os.environ.get("KPI_WEIGHT_RESOLUTION_HOURS", "-0.05"))


# ---------------------------------------------------------------------------
# Zammad client — ticket counts/resolution time per department/employee (§12.1)
# ---------------------------------------------------------------------------
class ZammadClient:
    def __init__(self, base_url: str, admin_token: str):
        self.base = base_url.rstrip("/") + "/api/v1"
        self.headers = {"Authorization": f"Token token={admin_token}"}
        self._client = httpx.AsyncClient(headers=self.headers, timeout=30.0)

    async def close(self):
        await self._client.aclose()

    async def get_groups(self) -> dict:
        """Returns {group_id: group_name}."""
        r = await self._client.get(f"{self.base}/groups")
        r.raise_for_status()
        return {g["id"]: g["name"] for g in r.json()}

    async def get_tickets_in_range(self, start: datetime, end: datetime) -> list[dict]:
        """
        Fetch tickets and filter by created_at/close_at client-side in plain Python
        (deterministic, no LLM, no reliance on Zammad's own search-query date syntax).
        Zammad's search endpoint requires a non-empty `query`; "*" matches everything.
        """
        r = await self._client.get(
            f"{self.base}/tickets/search",
            params={"query": "*", "limit": 1000, "expand": "true"},
        )
        r.raise_for_status()
        ids = r.json()
        # /tickets/search with expand=true still returns bare ids on some Zammad
        # versions; fall back to fetching each ticket individually if so.
        tickets = []
        if ids and isinstance(ids[0], dict):
            tickets = ids
        else:
            for tid in ids:
                tr = await self._client.get(f"{self.base}/tickets/{tid}")
                tr.raise_for_status()
                tickets.append(tr.json())
        return tickets


# ---------------------------------------------------------------------------
# Wiki.js client — page create/update counts (§12.1)
# ---------------------------------------------------------------------------
class WikiJSClient:
    def __init__(self, base_url: str, admin_token: str):
        self.graphql_url = base_url.rstrip("/") + "/graphql"
        self.headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        self._client = httpx.AsyncClient(headers=self.headers, timeout=30.0)

    async def close(self):
        await self._client.aclose()

    async def graphql(self, query: str, variables: dict = None) -> dict:
        r = await self._client.post(self.graphql_url, json={"query": query, "variables": variables or {}})
        r.raise_for_status()
        body = r.json()
        if body.get("errors"):
            raise RuntimeError(f"Wiki.js GraphQL error: {body['errors']}")
        return body

    async def list_pages(self) -> list[dict]:
        # `pages.list`'s item type (PageListItem) does NOT expose authorId/creatorId — those
        # only exist on the single-page type (`pages.single(id)`). Confirmed via GraphQL
        # introspection against a live instance: requesting them on `list` 400s with
        # "Cannot query field \"authorId\" on type \"PageListItem\"". Fetch the list first,
        # then a per-page `single` query to get attribution (N+1, acceptable for a once-daily
        # rollup over a realistically small wiki page count).
        result = await self.graphql("""
            query {
                pages {
                    list {
                        id
                        path
                        title
                        createdAt
                        updatedAt
                    }
                }
            }
        """)
        pages = ((result.get("data") or {}).get("pages") or {}).get("list") or []
        for p in pages:
            detail = await self.graphql("""
                query($id: Int!) {
                    pages {
                        single(id: $id) {
                            authorId
                            creatorId
                        }
                    }
                }
            """, {"id": p["id"]})
            single = ((detail.get("data") or {}).get("pages") or {}).get("single") or {}
            p["authorId"] = single.get("authorId")
            p["creatorId"] = single.get("creatorId")
        return pages


# ---------------------------------------------------------------------------
# Mattermost client — message counts per user/channel (§12.1)
# ---------------------------------------------------------------------------
class MattermostClient:
    def __init__(self, base_url: str, admin_token: str):
        self.base = base_url.rstrip("/") + "/api/v4"
        self.headers = {"Authorization": f"Bearer {admin_token}"}
        self._client = httpx.AsyncClient(headers=self.headers, timeout=30.0)

    async def close(self):
        await self._client.aclose()

    async def get_channels_for_team(self, team_id: str) -> list[dict]:
        r = await self._client.get(f"{self.base}/teams/{team_id}/channels")
        r.raise_for_status()
        return r.json()

    async def get_teams(self) -> list[dict]:
        r = await self._client.get(f"{self.base}/teams")
        r.raise_for_status()
        return r.json()

    async def get_posts_in_range(self, channel_id: str, start: datetime, end: datetime) -> list[dict]:
        """
        No dedicated stats endpoint exists for message counts, so page through
        /channels/{id}/posts and filter by create_at (epoch ms) client-side.
        """
        posts = []
        page = 0
        since_ms = int(start.timestamp() * 1000)
        while True:
            r = await self._client.get(
                f"{self.base}/channels/{channel_id}/posts",
                params={"page": page, "per_page": 200, "since": since_ms},
            )
            r.raise_for_status()
            body = r.json()
            order = body.get("order", [])
            if not order:
                break
            posts_map = body.get("posts", {})
            posts.extend(posts_map[pid] for pid in order if pid in posts_map)
            if len(order) < 200:
                break
            page += 1
        end_ms = int(end.timestamp() * 1000)
        return [p for p in posts if since_ms <= p.get("create_at", 0) < end_ms]


# ---------------------------------------------------------------------------
# Akaunting client — revenue in range (§12.1). Same X-Company-aware pattern as
# accounting-engine.AkauntingClient (company_id sent in every request body/query).
# ---------------------------------------------------------------------------
class AkauntingClient:
    def __init__(self, base_url: str, email: str, password: str, company_id: int):
        self.base = base_url.rstrip("/") + "/api"
        self.company_id = company_id
        self.auth = (email, password)
        # Akaunting resolves company context from the `X-Company` header specifically — NOT a
        # `company`/`company_id` query param or a header named `company`. Without it, module-
        # dependent parts of the API return 500 (confirmed live: this exact endpoint 500'd until
        # the header was added). See BUILD_LOG.md's Phase 9/15 entry ("X-Company") for the full
        # root-cause writeup from when this was first found.
        # ALSO needs a `Host` header matching Akaunting's APP_URL (Laravel's TrustHosts
        # middleware rejects the bare "akaunting" service DNS name with a 500 "Untrusted Host" —
        # found live while verifying this exact rollup call; also affected accounting-engine's
        # AkauntingClient, fixed there too in the same pass).
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={"X-Company": str(company_id), "Host": "accounting.fakecorp.internal"},
        )

    async def close(self):
        await self._client.aclose()

    async def get_income_transactions(self, start: date, end: date) -> list[dict]:
        r = await self._client.get(
            f"{self.base}/transactions",
            params={"company_id": self.company_id, "type": "income",
                    "paid_at": f"{start.isoformat()},{end.isoformat()}"},
            auth=self.auth,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        # Belt-and-suspenders: also filter client-side, since Akaunting's `paid_at`
        # range-query parameter format is not consistently documented across versions.
        out = []
        for tx in data:
            paid_at = tx.get("paid_at", "")[:10]
            try:
                d = date.fromisoformat(paid_at)
            except ValueError:
                continue
            if start <= d <= end:
                out.append(tx)
        return out


# ---------------------------------------------------------------------------
# Database pool
# ---------------------------------------------------------------------------
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


async def audit_log(conn: asyncpg.Connection, actor: str, action: str, detail: dict) -> None:
    import json
    await conn.execute(
        "INSERT INTO system_audit_log (actor, action, detail) VALUES ($1, $2, $3)",
        actor, action, json.dumps(detail, default=str)
    )


# ---------------------------------------------------------------------------
# Phase 35: live review-mode config (kpi_engine_config, migration 011)
# ---------------------------------------------------------------------------
async def get_review_approval_mode(pool: asyncpg.Pool) -> bool:
    """
    Reads the live review-mode flag from kpi_engine_config. Falls back to the
    env-var default if the row somehow doesn't exist yet (e.g. migration ran
    but this is the very first call in a race) rather than erroring.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT review_approval_mode FROM kpi_engine_config WHERE id = 1")
        if row is None:
            return KPI_REVIEW_APPROVAL_MODE_ENV_DEFAULT
        return bool(row["review_approval_mode"])


async def set_review_approval_mode(pool: asyncpg.Pool, enabled: bool, actor: str = "principal") -> bool:
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO kpi_engine_config (id, review_approval_mode, updated_at, updated_by)
            VALUES (1, $1, NOW(), $2)
            ON CONFLICT (id) DO UPDATE
                SET review_approval_mode = EXCLUDED.review_approval_mode,
                    updated_at = NOW(),
                    updated_by = EXCLUDED.updated_by
        """, enabled, actor)
        await audit_log(conn, actor, "kpi_review_mode_changed", {"review_approval_mode": enabled})
    return enabled


async def write_snapshot(
    conn: asyncpg.Connection,
    snapshot_date: date,
    entity_type: str,
    entity_id: str,
    metric: str,
    value: Decimal,
) -> None:
    """Upsert into kpi_snapshots — UNIQUE(snapshot_date, entity_type, entity_id, metric)
    makes this naturally idempotent; re-running a rollup for the same day overwrites,
    never duplicates."""
    await conn.execute("""
        INSERT INTO kpi_snapshots (snapshot_date, entity_type, entity_id, metric, value)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (snapshot_date, entity_type, entity_id, metric)
        DO UPDATE SET value = EXCLUDED.value
    """, snapshot_date, entity_type, entity_id, metric, value)


# ---------------------------------------------------------------------------
# Daily rollup (§12.1) — ZERO LLM calls. Pure deterministic aggregation.
# ---------------------------------------------------------------------------
async def run_rollup(
    pool: asyncpg.Pool,
    zammad: ZammadClient,
    wiki: WikiJSClient,
    mattermost: MattermostClient,
    akaunting: AkauntingClient,
    start: datetime,
    end: datetime,
    snapshot_date: Optional[date] = None,
) -> dict:
    snapshot_date = snapshot_date or start.date()
    written = 0

    async with pool.acquire() as conn:
        employees = await conn.fetch("""
            SELECT id, name, department, zammad_agent_id, mattermost_id, wiki_user_id
            FROM employees WHERE status = 'active'
        """)
        by_zammad_id = {e["zammad_agent_id"]: e for e in employees if e["zammad_agent_id"]}
        by_mm_id = {e["mattermost_id"]: e for e in employees if e["mattermost_id"]}
        by_wiki_id = {str(e["wiki_user_id"]): e for e in employees if e["wiki_user_id"]}
        dept_of = {e["id"]: e["department"] for e in employees}

        # --- Zammad: tickets opened/resolved + avg resolution time ------------
        groups = await zammad.get_groups()
        tickets = await zammad.get_tickets_in_range(start, end)

        per_emp_opened: dict = {}
        per_emp_resolved: dict = {}
        per_emp_resolution_hours: dict = {}
        per_dept_opened: dict = {}
        per_dept_resolved: dict = {}
        per_dept_resolution_hours: dict = {}

        def _parse_dt(s):
            if not s:
                return None
            return datetime.fromisoformat(s.replace("Z", "+00:00"))

        for t in tickets:
            created = _parse_dt(t.get("created_at"))
            closed = _parse_dt(t.get("close_at"))
            group_name = groups.get(t.get("group_id"), f"group:{t.get('group_id')}")
            owner_id = str(t.get("owner_id", ""))
            emp = by_zammad_id.get(owner_id)

            if created and start <= created < end:
                if emp:
                    per_emp_opened[emp["id"]] = per_emp_opened.get(emp["id"], 0) + 1
                per_dept_opened[group_name] = per_dept_opened.get(group_name, 0) + 1

            if closed and start <= closed < end:
                if emp:
                    per_emp_resolved[emp["id"]] = per_emp_resolved.get(emp["id"], 0) + 1
                per_dept_resolved[group_name] = per_dept_resolved.get(group_name, 0) + 1
                if created:
                    hours = (closed - created).total_seconds() / 3600.0
                    if emp:
                        per_emp_resolution_hours.setdefault(emp["id"], []).append(hours)
                    per_dept_resolution_hours.setdefault(group_name, []).append(hours)

        for emp_id, count in per_emp_opened.items():
            await write_snapshot(conn, snapshot_date, "employee", str(emp_id), "tickets_opened", Decimal(count))
            written += 1
        for emp_id, count in per_emp_resolved.items():
            await write_snapshot(conn, snapshot_date, "employee", str(emp_id), "tickets_resolved", Decimal(count))
            written += 1
        for emp_id, hours_list in per_emp_resolution_hours.items():
            avg = Decimal(sum(hours_list) / len(hours_list)).quantize(Decimal("0.01"))
            await write_snapshot(conn, snapshot_date, "employee", str(emp_id), "avg_resolution_hours", avg)
            written += 1
        for dept, count in per_dept_opened.items():
            await write_snapshot(conn, snapshot_date, "department", dept, "tickets_opened", Decimal(count))
            written += 1
        for dept, count in per_dept_resolved.items():
            await write_snapshot(conn, snapshot_date, "department", dept, "tickets_resolved", Decimal(count))
            written += 1
        for dept, hours_list in per_dept_resolution_hours.items():
            avg = Decimal(sum(hours_list) / len(hours_list)).quantize(Decimal("0.01"))
            await write_snapshot(conn, snapshot_date, "department", dept, "avg_resolution_hours", avg)
            written += 1

        # --- Wiki.js: page create/update counts --------------------------------
        pages = await wiki.list_pages()
        per_emp_created: dict = {}
        per_emp_updated: dict = {}
        per_dept_created: dict = {}
        per_dept_updated: dict = {}

        for p in pages:
            created = _parse_dt(p.get("createdAt"))
            updated = _parse_dt(p.get("updatedAt"))
            author_id = str(p.get("authorId", ""))
            creator_id = str(p.get("creatorId", ""))
            creator_emp = by_wiki_id.get(creator_id)
            author_emp = by_wiki_id.get(author_id)

            if created and start <= created < end:
                if creator_emp:
                    per_emp_created[creator_emp["id"]] = per_emp_created.get(creator_emp["id"], 0) + 1
                    per_dept_created[creator_emp["department"]] = per_dept_created.get(creator_emp["department"], 0) + 1
            # An update in the same window as the creation is still a genuine edit
            # event on a Wiki.js page (updatedAt bumps on every save, including the
            # initial one) — only count it as a distinct "update" if it happened
            # after creation, to avoid double counting the initial save.
            if updated and start <= updated < end and (not created or updated > created):
                if author_emp:
                    per_emp_updated[author_emp["id"]] = per_emp_updated.get(author_emp["id"], 0) + 1
                    per_dept_updated[author_emp["department"]] = per_dept_updated.get(author_emp["department"], 0) + 1

        for emp_id, count in per_emp_created.items():
            await write_snapshot(conn, snapshot_date, "employee", str(emp_id), "wiki_pages_created", Decimal(count))
            written += 1
        for emp_id, count in per_emp_updated.items():
            await write_snapshot(conn, snapshot_date, "employee", str(emp_id), "wiki_pages_updated", Decimal(count))
            written += 1
        for dept, count in per_dept_created.items():
            await write_snapshot(conn, snapshot_date, "department", dept, "wiki_pages_created", Decimal(count))
            written += 1
        for dept, count in per_dept_updated.items():
            await write_snapshot(conn, snapshot_date, "department", dept, "wiki_pages_updated", Decimal(count))
            written += 1

        # --- Mattermost: message counts per user/channel ------------------------
        per_emp_messages: dict = {}
        per_dept_messages: dict = {}
        teams = await mattermost.get_teams()
        seen_channels = set()
        for team in teams:
            channels = await mattermost.get_channels_for_team(team["id"])
            for ch in channels:
                if ch["id"] in seen_channels:
                    continue
                seen_channels.add(ch["id"])
                posts = await mattermost.get_posts_in_range(ch["id"], start, end)
                for post in posts:
                    user_id = post.get("user_id")
                    emp = by_mm_id.get(user_id)
                    if emp:
                        per_emp_messages[emp["id"]] = per_emp_messages.get(emp["id"], 0) + 1
                        per_dept_messages[emp["department"]] = per_dept_messages.get(emp["department"], 0) + 1

        for emp_id, count in per_emp_messages.items():
            await write_snapshot(conn, snapshot_date, "employee", str(emp_id), "chat_messages", Decimal(count))
            written += 1
        for dept, count in per_dept_messages.items():
            await write_snapshot(conn, snapshot_date, "department", dept, "chat_messages", Decimal(count))
            written += 1

        # --- Akaunting: revenue in range -----------------------------------------
        income_txs = await akaunting.get_income_transactions(start.date(), end.date() - timedelta(days=1) if end.date() > start.date() else end.date())
        total_revenue = sum(Decimal(str(tx.get("amount", 0))) for tx in income_txs)
        await write_snapshot(conn, snapshot_date, "department", "Company", "revenue_posted", total_revenue)
        written += 1

        await audit_log(conn, "kpi-engine", "rollup_complete", {
            "snapshot_date": snapshot_date.isoformat(),
            "range_start": start.isoformat(),
            "range_end": end.isoformat(),
            "rows_written": written,
        })

    log.info("Rollup complete for %s: %d rows written", snapshot_date, written)
    return {"status": "complete", "snapshot_date": snapshot_date.isoformat(), "rows_written": written}


# ---------------------------------------------------------------------------
# Performance-review formula (§12.2) — plain code, no LLM.
# ---------------------------------------------------------------------------
async def compute_review_candidates(pool: asyncpg.Pool, as_of: Optional[datetime] = None) -> list[dict]:
    """
    Returns the ranked review candidates: composite score, department quartile
    tier, proposed raise pct, and an `underperforming` flag (Phase 24 consumes
    this to decide whether to open a performance_review meeting — this service
    never opens meetings itself).

    SPEC_CLARIFICATIONS #6 cold start: skip employees with <1 full review cycle
    tenure (KPI_REVIEW_MIN_TENURE_DAYS) and departments with fewer than
    KPI_REVIEW_MIN_DEPT_SIZE active members — mirrors meeting-simulator's
    `/meetings/pending-performance-reviews` eligibility filter.
    """
    as_of = as_of or datetime.now(timezone.utc)
    lookback_start = as_of - timedelta(days=KPI_REVIEW_LOOKBACK_DAYS)

    async with pool.acquire() as conn:
        employees = await conn.fetch(f"""
            SELECT e.id, e.name, e.department, e.pay_rate, e.hired_at
            FROM employees e
            WHERE e.status = 'active'
              AND e.hired_at < NOW() - INTERVAL '{KPI_REVIEW_MIN_TENURE_DAYS} days'
              AND (
                SELECT COUNT(*) FROM employees e2
                WHERE e2.department = e.department AND e2.status = 'active'
              ) >= {KPI_REVIEW_MIN_DEPT_SIZE}
            ORDER BY e.department, e.id
        """)

        results = []
        by_dept: dict = {}
        for emp in employees:
            metrics = await conn.fetch("""
                SELECT metric, value FROM kpi_snapshots
                WHERE entity_type = 'employee' AND entity_id = $1 AND snapshot_date >= $2
            """, str(emp["id"]), lookback_start.date())
            m = {}
            for row in metrics:
                m.setdefault(row["metric"], []).append(Decimal(str(row["value"])))
            tickets_resolved = sum(m.get("tickets_resolved", [Decimal(0)]))
            wiki_pages = sum(m.get("wiki_pages_created", [Decimal(0)])) + sum(m.get("wiki_pages_updated", [Decimal(0)]))
            chat_messages = sum(m.get("chat_messages", [Decimal(0)]))
            resolution_hours_list = m.get("avg_resolution_hours", [])
            avg_resolution_hours = (sum(resolution_hours_list) / len(resolution_hours_list)) if resolution_hours_list else Decimal(0)

            composite = (
                tickets_resolved * KPI_WEIGHT_TICKETS_RESOLVED
                + wiki_pages * KPI_WEIGHT_WIKI_PAGES
                + chat_messages * KPI_WEIGHT_CHAT_MESSAGES
                + avg_resolution_hours * KPI_WEIGHT_RESOLUTION_HOURS
            )
            entry = {
                "employee_id": emp["id"],
                "name": emp["name"],
                "department": emp["department"],
                "pay_rate": float(emp["pay_rate"]),
                "composite_score": float(composite),
                "tickets_resolved": float(tickets_resolved),
                "wiki_pages": float(wiki_pages),
                "chat_messages": float(chat_messages),
                "avg_resolution_hours": float(avg_resolution_hours),
            }
            results.append(entry)
            by_dept.setdefault(emp["department"], []).append(entry)

        # Rank within department by composite score (descending = best first).
        for dept, members in by_dept.items():
            ranked = sorted(members, key=lambda e: e["composite_score"], reverse=True)
            n = len(ranked)
            top_cut = -(-n // 4)       # ceil(n/4)
            second_cut = -(-n * 2 // 4)  # ceil(n/2)
            underperform_cut = max(1, int(n * float(KPI_REVIEW_UNDERPERFORM_PERCENTILE)))
            for i, entry in enumerate(ranked):
                if i < top_cut:
                    entry["tier"] = "top_quartile"
                    entry["raise_pct"] = float(KPI_REVIEW_TOP_RAISE_PCT)
                elif i < second_cut:
                    entry["tier"] = "second_quartile"
                    entry["raise_pct"] = float(KPI_REVIEW_SECOND_RAISE_PCT)
                else:
                    entry["tier"] = "rest"
                    entry["raise_pct"] = 0.0
                entry["dept_rank"] = i + 1
                entry["dept_size"] = n
                entry["underperforming"] = i >= (n - underperform_cut)

        return results


async def apply_review_raises(pool: asyncpg.Pool, http: httpx.AsyncClient, as_of: Optional[datetime] = None) -> dict:
    """
    Runs the review formula and, for each employee in top/second quartile:
      - default mode: calls accounting-engine's existing POST /payroll/raise
        (raises apply immediately, no approval, spec §10.3) — does NOT
        reimplement the DB write, calls into the real endpoint.
      - KPI_REVIEW_APPROVAL_MODE=on: queues a proposed raise into
        pending_approvals instead of auto-applying (dashboard "review & approve"
        toggle, off by default).
    """
    candidates = await compute_review_candidates(pool, as_of)
    applied = []
    queued = []
    skipped = []
    approval_mode = await get_review_approval_mode(pool)

    async with pool.acquire() as conn:
        for c in candidates:
            if c["raise_pct"] <= 0:
                skipped.append(c["employee_id"])
                continue
            new_pay = round(Decimal(str(c["pay_rate"])) * (Decimal("1") + Decimal(str(c["raise_pct"]))), 2)
            reason = f"performance_review: {c['tier']} in {c['department']} (rank {c['dept_rank']}/{c['dept_size']})"

            if approval_mode:
                idem = f"review-raise:{c['employee_id']}:{(as_of or datetime.now(timezone.utc)).date().isoformat()}"
                existing = await conn.fetchrow(
                    "SELECT id FROM pending_approvals WHERE idempotency_key = $1", idem
                )
                if existing:
                    queued.append({"employee_id": c["employee_id"], "approval_id": existing["id"], "duplicate": True})
                    continue
                approval_id = await conn.fetchval("""
                    INSERT INTO pending_approvals
                        (expense_request_ref, requester_employee_id, approver_employee_id,
                         approver_is_principal, amount, status, idempotency_key)
                    VALUES ($1, $2, $3, $4, $5, 'pending', $6)
                    RETURNING id
                """,
                    f"review_raise:{reason}",
                    c["employee_id"],
                    None,
                    True,
                    new_pay,
                    idem,
                )
                await audit_log(conn, "kpi-engine", "review_raise_queued", {
                    "employee_id": c["employee_id"], "new_pay": float(new_pay),
                    "reason": reason, "approval_id": approval_id,
                })
                queued.append({"employee_id": c["employee_id"], "approval_id": approval_id, "new_pay": float(new_pay)})
            else:
                try:
                    r = await http.post(
                        f"{ACCOUNTING_ENGINE_URL}/payroll/raise",
                        params={"employee_id": c["employee_id"], "new_pay": str(new_pay), "reason": reason},
                    )
                    r.raise_for_status()
                    result = r.json()
                    applied.append({"employee_id": c["employee_id"], **result})
                    await audit_log(conn, "kpi-engine", "review_raise_applied", {
                        "employee_id": c["employee_id"], "new_pay": float(new_pay), "reason": reason,
                    })
                except httpx.HTTPStatusError as exc:
                    log.error("Review raise failed for employee %d: %s", c["employee_id"], exc)
                    skipped.append(c["employee_id"])

    return {
        "status": "complete",
        "approval_mode": approval_mode,
        "applied": applied,
        "queued": queued,
        "skipped": skipped,
        "candidates": candidates,
    }


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    log.info("kpi-engine: ready")
    yield
    await _pool.close()


app = FastAPI(
    title="FakeCo KPI Engine",
    description="Deterministic KPI rollups + performance-review formula — no LLM calls.",
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


def get_zammad() -> ZammadClient:
    return ZammadClient(ZAMMAD_URL, ZAMMAD_ADMIN_TOKEN)


def get_wiki() -> WikiJSClient:
    return WikiJSClient(WIKIJS_URL, WIKIJS_ADMIN_TOKEN)


def get_mattermost() -> MattermostClient:
    return MattermostClient(MATTERMOST_URL, MATTERMOST_ADMIN_TOKEN)


def get_akaunting() -> AkauntingClient:
    return AkauntingClient(AKAUNTING_URL, AKAUNTING_ADMIN_EMAIL, AKAUNTING_ADMIN_PASSWORD, AKAUNTING_COMPANY_ID)


class RollupRequest(BaseModel):
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    snapshot_date: Optional[date] = None


class ReviewRunRequest(BaseModel):
    as_of: Optional[datetime] = None


@app.get("/health")
async def health():
    return {"status": "ok", "service": "kpi-engine"}


@app.post("/rollup/run")
async def rollup_run_endpoint(req: RollupRequest, pool: PoolDep):
    end = req.end or datetime.now(timezone.utc)
    start = req.start or (end - timedelta(days=1))
    zammad = get_zammad()
    wiki = get_wiki()
    mattermost = get_mattermost()
    akaunting = get_akaunting()
    try:
        return await run_rollup(pool, zammad, wiki, mattermost, akaunting, start, end, req.snapshot_date)
    finally:
        await zammad.close()
        await wiki.close()
        await mattermost.close()
        await akaunting.close()


class ReviewModeRequest(BaseModel):
    enabled: bool
    actor: str = "principal"


@app.get("/config/review-mode")
async def get_review_mode_endpoint(pool: PoolDep):
    """Phase 35: dashboard KPI tab reads this to render the automatic vs
    review-and-approve toggle's current state."""
    return {"approval_mode": await get_review_approval_mode(pool)}


@app.post("/config/review-mode")
async def set_review_mode_endpoint(req: ReviewModeRequest, pool: PoolDep):
    """Phase 35: dashboard KPI tab's toggle writes here — live-switches the
    flag apply_review_raises() reads on its next run, no container restart
    needed (replaces the old KPI_REVIEW_APPROVAL_MODE env-var-only behavior)."""
    new_value = await set_review_approval_mode(pool, req.enabled, req.actor)
    return {"approval_mode": new_value}


@app.get("/reviews/due")
async def reviews_due_endpoint(pool: PoolDep):
    """
    Exposes ranked review candidates (composite score, quartile tier, proposed
    raise pct, underperforming flag) for Phase 24's meeting-simulator extension
    to consume when deciding whether to open a performance_review meeting.
    Mirrors meeting-simulator's /meetings/pending-performance-reviews eligibility
    filter (tenure + department-size cold-start exemption).
    """
    return await compute_review_candidates(pool)


@app.post("/reviews/run")
async def reviews_run_endpoint(req: ReviewRunRequest, pool: PoolDep):
    async with httpx.AsyncClient(timeout=30.0) as http:
        return await apply_review_raises(pool, http, req.as_of)
