"""
meeting-simulator/main.py — FakeCo "Real Appliances"
Phase 16: Meeting simulation engine.

Spec §4.2–4.5 + §6 (meeting types and cadence):
  - standup           — every weekday, per-department (§6.1)
  - cross_functional  — 2x/month across departments (§6.2)
  - pay_negotiation   — on-demand from Phase 24 pay-cut stub (§6.4)
  - performance_review— per-employee, triggered by scheduler (§6.3)
  - crisis_response   — triggered by unresolved narrative thread (§6.5)

Spec §4.3: Meeting prioritization (all meetings eligible every tick, but ordered):
  Priority 1: Crisis response (Principal reaction window triggers this)
  Priority 2: Performance reviews with pending reactions
  Priority 3: Scheduled standup / cross-functional
  Priority 4: On-demand pay negotiation

Spec §20.1: Use 'heavy' model tier for meetings.
Each meeting:
  1. Selects attendees deterministically (not randomly by LLM).
  2. Constructs a structured prompt from narrative context.
  3. Calls LiteLLM /chat/completions (heavy tier).
  4. Parses the LLM output into decisions, action_items, outcome.
  5. Posts to Mattermost, creates narrative_event row, updates thread.
  6. Forwards any financial consequences to accounting-engine.

Token efficiency (§20.1 tip 1): uses system prompt caching pattern —
  company directive block is a pinned system message, not repeated each call.
"""
import asyncio
import json
import logging
import os
import random
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Annotated
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","service":"meeting-simulator","msg":"%(message)s"}'
)
log = logging.getLogger("meeting_sim")

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
LITELLM_URL = os.environ.get("LITELLM_URL", "http://litellm:4000")
LITELLM_API_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
MATTERMOST_URL = os.environ.get("MATTERMOST_URL", "http://mattermost:8065")
MATTERMOST_BOT_TOKEN = os.environ.get("MATTERMOST_BOT_TOKEN", "")     # the orchestrator bot's token
MATTERMOST_TEAM_ID = os.environ.get("MATTERMOST_TEAM_ID", "")
SIM_CLOCK_URL = os.environ.get("SIM_CLOCK_URL", "http://sim-clock:8000")
ACCOUNTING_ENGINE_URL = os.environ.get("ACCOUNTING_ENGINE_URL", "http://accounting-engine:8000")
WIKIJS_URL = os.environ.get("WIKIJS_URL", "http://wikijs:3000")
WIKIJS_ADMIN_TOKEN = os.environ.get("WIKIJS_ADMIN_TOKEN", "")


# ---------------------------------------------------------------------------
# LiteLLM client
# ---------------------------------------------------------------------------
class LLMClient:
    def __init__(self, base_url: str, api_key: str):
        self.base = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self._client = httpx.AsyncClient(headers=self.headers, timeout=120.0)

    async def close(self):
        await self._client.aclose()

    async def chat(
        self,
        messages: list[dict],
        model: str = "heavy",
        max_tokens: int = 2000,
        temperature: float = 0.8,
    ) -> str:
        """Returns the text content of the first choice."""
        r = await self._client.post(f"{self.base}/chat/completions", json={
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Mattermost client (minimal — just posting messages)
# ---------------------------------------------------------------------------
class MattermostClient:
    def __init__(self, base_url: str, bot_token: str, team_id: str = ""):
        self.base = base_url.rstrip("/") + "/api/v4"
        self.headers = {"Authorization": f"Bearer {bot_token}"}
        self.team_id = team_id
        self._client = httpx.AsyncClient(headers=self.headers, timeout=30.0)

    async def close(self):
        await self._client.aclose()

    async def get_or_create_channel(self, name: str, display_name: str, purpose: str = "") -> str:
        """Get or create a channel. Returns channel_id."""
        r = await self._client.get(f"{self.base}/teams/{self.team_id}/channels/name/{name}")
        if r.status_code == 200:
            return r.json()["id"]
        r2 = await self._client.post(f"{self.base}/channels", json={
            "team_id": self.team_id,
            "name": name,
            "display_name": display_name,
            "purpose": purpose,
            "type": "O",  # public
        })
        r2.raise_for_status()
        return r2.json()["id"]

    async def post_message(self, channel_id: str, text: str, props: dict = None) -> str:
        """Post a message. Returns post_id."""
        payload = {"channel_id": channel_id, "message": text}
        if props:
            payload["props"] = props
        r = await self._client.post(f"{self.base}/posts", json=payload)
        r.raise_for_status()
        return r.json()["id"]


# ---------------------------------------------------------------------------
# Wiki.js client (minimal — just page creation via GraphQL)
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

    async def create_page(self, path: str, title: str, content: str, description: str = "", tags: list[str] = None) -> dict:
        """Create a Wiki.js page. Returns the responseResult dict (succeeded/errorCode/message)."""
        result = await self.graphql("""
            mutation($content: String!, $description: String!, $editor: String!, $isPublished: Boolean!, $isPrivate: Boolean!, $locale: String!, $path: String!, $tags: [String]!, $title: String!) {
                pages {
                    create(content: $content, description: $description, editor: $editor, isPublished: $isPublished, isPrivate: $isPrivate, locale: $locale, path: $path, tags: $tags, title: $title) {
                        responseResult { succeeded errorCode message }
                        page { id path title }
                    }
                }
            }
        """, {
            "content": content,
            "description": description or title,
            "editor": "markdown",
            "isPublished": True,
            "isPrivate": False,
            "locale": "en",
            "path": path,
            "tags": tags or [],
            "title": title,
        })
        create_result = ((result.get("data") or {}).get("pages") or {}).get("create") or {}
        # `.get("responseResult", {})` only falls back to {} when the key is missing, not when
        # it's explicitly `null` — guard against None too (same Wiki.js quirk as provisioning).
        response_result = create_result.get("responseResult") or {}
        if not response_result.get("succeeded"):
            raise RuntimeError(f"Wiki.js page creation failed: {create_result}")
        return response_result


# ---------------------------------------------------------------------------
# Sim clock helper
# ---------------------------------------------------------------------------
async def get_sim_time(http_client: httpx.AsyncClient) -> datetime:
    try:
        r = await http_client.get(f"{SIM_CLOCK_URL}/sim_time", timeout=5.0)
        r.raise_for_status()
        ts = r.json()["sim_time"]
        return datetime.fromisoformat(ts)
    except Exception:
        log.warning("Could not reach sim-clock, using wall time")
        return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Meeting attendee selection (deterministic — not LLM-driven)
# Spec §4.2: attendee list is NOT left to the LLM to invent.
# ---------------------------------------------------------------------------
async def select_attendees(
    conn: asyncpg.Connection,
    meeting_type: str,
    department: Optional[str] = None,
    target_employee_id: Optional[int] = None,
    max_cross_dept: int = 5,
) -> list[dict]:
    """
    Deterministically selects meeting attendees.

    standup:          all active employees in the department
    cross_functional: department leads + one IC from each department (up to max_cross_dept)
    pay_negotiation:  target employee + their department lead + HR lead
    performance_review: target employee + their department lead
    crisis_response:  all active leads + any employees named in the crisis thread
    """
    if meeting_type == "standup":
        employees = await conn.fetch(
            "SELECT id, name, role_tier FROM employees WHERE department = $1 AND status = 'active' ORDER BY hired_at",
            department
        )
    elif meeting_type == "cross_functional":
        # Leads (always attend) + one IC per department, chosen via relationship-weighted
        # scoring (Phase 20 §4): among each department's active ICs, prefer whoever has the
        # highest existing affinity with the leads already attending — ties broken by
        # hired_at for determinism, matching this function's existing no-randomness contract.
        leads = await conn.fetch(
            "SELECT id, name, department, role_tier FROM employees WHERE role_tier = 'lead' AND status = 'active'"
        )
        lead_ids = [l["id"] for l in leads]
        ic_candidates = await conn.fetch("""
            SELECT id, name, department, role_tier, hired_at
            FROM employees WHERE role_tier = 'ic' AND status = 'active'
            ORDER BY department, hired_at
        """)
        relationships = await fetch_relationship_map(conn)

        by_dept: dict[str, list[dict]] = {}
        for ic in ic_candidates:
            by_dept.setdefault(ic["department"], []).append(dict(ic))

        chosen_ics = []
        for dept, candidates in by_dept.items():
            best = max(
                candidates,
                key=lambda c: (score_candidate_by_relationships(c["id"], lead_ids, relationships), -c["hired_at"].timestamp()),
            )
            chosen_ics.append(best)

        all_emp = {e["id"]: dict(e) for e in leads}
        for ic in chosen_ics:
            all_emp[ic["id"]] = ic
        employees = list(all_emp.values())[:max_cross_dept]
    elif meeting_type == "pay_negotiation":
        if not target_employee_id:
            raise ValueError("pay_negotiation requires target_employee_id")
        target = await conn.fetchrow("SELECT id, name, department, role_tier FROM employees WHERE id = $1", target_employee_id)
        lead = await conn.fetchrow("""
            SELECT id, name, department, role_tier FROM employees
            WHERE department = $1 AND role_tier = 'lead' AND status = 'active' AND id != $2
            ORDER BY hired_at LIMIT 1
        """, target["department"], target_employee_id)
        hr_lead = await conn.fetchrow("""
            SELECT id, name, department, role_tier FROM employees
            WHERE department = 'HR' AND role_tier = 'lead' AND status = 'active'
            ORDER BY hired_at LIMIT 1
        """)
        employees = [e for e in [target, lead, hr_lead] if e is not None]
    elif meeting_type == "performance_review":
        if not target_employee_id:
            raise ValueError("performance_review requires target_employee_id")
        target = await conn.fetchrow("SELECT id, name, department, role_tier FROM employees WHERE id = $1", target_employee_id)
        lead = await conn.fetchrow("""
            SELECT id, name, department, role_tier FROM employees
            WHERE department = $1 AND role_tier = 'lead' AND status = 'active' AND id != $2
            ORDER BY hired_at LIMIT 1
        """, target["department"], target_employee_id)
        employees = [e for e in [lead, target] if e is not None]
    elif meeting_type == "crisis_response":
        employees = await conn.fetch(
            "SELECT id, name, role_tier FROM employees WHERE role_tier = 'lead' AND status = 'active'"
        )
    else:
        raise ValueError(f"Unknown meeting_type: {meeting_type}")

    return [dict(e) for e in employees]


# ---------------------------------------------------------------------------
# Relationship-weighted attendee scoring (Phase 20 §4)
# Spec §5 + exit criteria: a plain, directly-callable, deterministic scoring
# function — NOT baked invisibly into LLM-driven selection — so it can be
# tested with fixed relationship data and a direct assertion, no statistical
# sampling required.
# ---------------------------------------------------------------------------
def score_candidate_by_relationships(
    candidate_id: int,
    already_selected_ids: list[int],
    relationships: dict[tuple[int, int], int],
) -> int:
    """
    Sums the affinity_score between `candidate_id` and everyone already
    selected for the meeting. `relationships` maps canonical
    (min_id, max_id) pairs -> affinity_score (same convention as the
    employee_relationships table's ordering constraint). Higher score means
    the candidate is a better (more allied) fit alongside the current
    attendee list; unknown pairs contribute 0 (neutral, no data yet).
    """
    total = 0
    for other_id in already_selected_ids:
        if other_id == candidate_id:
            continue
        key = (candidate_id, other_id) if candidate_id < other_id else (other_id, candidate_id)
        total += relationships.get(key, 0)
    return total


async def fetch_relationship_map(conn: asyncpg.Connection) -> dict[tuple[int, int], int]:
    """Loads the full employee_relationships table into a {(a_id,b_id): affinity_score} dict."""
    rows = await conn.fetch("SELECT employee_a_id, employee_b_id, affinity_score FROM employee_relationships")
    return {(r["employee_a_id"], r["employee_b_id"]): r["affinity_score"] for r in rows}


def decision_text(decision) -> str:
    """Decisions ride the same LLM call as everything else (Phase 20 §2), so they're now
    objects ({description, stances}) rather than bare strings — tolerate either shape for
    display purposes (Mattermost/Wiki.js text, and any legacy/parse-error fallback data)."""
    if isinstance(decision, dict):
        return decision.get("description", "")
    return str(decision)


AFFINITY_DELTA = 5  # Phase 20 §3: fixed deterministic nudge per agree/disagree pair on a decision


def compute_affinity_updates(
    decisions: list,
    attendees: list[dict],
    delta: int = AFFINITY_DELTA,
) -> dict[tuple[int, int], int]:
    """
    Pure, deterministic (no LLM) function: walks each decision's per-attendee `stances`
    (added to the existing meeting-generation LLM call, Phase 20 §2) and, for every pair of
    attendees who both took a non-neutral stance on that decision, nudges their pairwise
    affinity up by `delta` if they agreed or down by `delta` if they disagreed. Neutral
    stances don't participate in any pair. Returns {(a_id, b_id): total_delta} using the
    same canonical (min_id, max_id) ordering as the employee_relationships table's CHECK
    constraint, ready to be applied by `apply_affinity_updates`.
    """
    name_to_id = {a["name"]: a["id"] for a in attendees}
    name_to_id_ci = {name.lower(): eid for name, eid in name_to_id.items()}

    updates: dict[tuple[int, int], int] = {}
    for d in decisions:
        if not isinstance(d, dict):
            continue
        stances = d.get("stances") or {}
        resolved: dict[int, str] = {}
        for name, stance in stances.items():
            eid = name_to_id.get(name) or name_to_id_ci.get(str(name).lower())
            if eid is not None and stance in ("agree", "disagree", "neutral"):
                resolved[eid] = stance

        ids = sorted(resolved.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a_id, b_id = ids[i], ids[j]
                stance_a, stance_b = resolved[a_id], resolved[b_id]
                if stance_a == "neutral" or stance_b == "neutral":
                    continue
                change = delta if stance_a == stance_b else -delta
                key = (a_id, b_id)  # ids is already sorted, so a_id < b_id
                updates[key] = updates.get(key, 0) + change
    return updates


async def apply_affinity_updates(conn: asyncpg.Connection, updates: dict[tuple[int, int], int]) -> None:
    """Upserts each pairwise affinity delta into employee_relationships, clamped to the
    schema's [-100, 100] CHECK range. No LLM call — spec §5's explicit no-extra-LLM-cost
    constraint for relationship updates."""
    for (a_id, b_id), delta in updates.items():
        if delta == 0:
            continue
        await conn.execute(
            """
            INSERT INTO employee_relationships (employee_a_id, employee_b_id, relationship_type, affinity_score)
            VALUES ($1, $2, 'neutral', GREATEST(-100, LEAST(100, $3)))
            ON CONFLICT (employee_a_id, employee_b_id) DO UPDATE
            SET affinity_score = GREATEST(-100, LEAST(100, employee_relationships.affinity_score + $3)),
                last_updated = NOW()
            """,
            a_id, b_id, delta,
        )


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------
async def build_meeting_prompt(
    conn: asyncpg.Connection,
    meeting_type: str,
    attendees: list[dict],
    thread: Optional[dict],
    sim_time: datetime,
    extra_context: str = "",
) -> list[dict]:
    """
    Build structured messages for the LLM.
    Token efficiency: company directive is a pinned system message (cacheable).
    """
    # Get current company directive (cached block)
    directive = await conn.fetchrow(
        "SELECT content FROM company_directives WHERE is_current = TRUE ORDER BY version DESC LIMIT 1"
    )
    directive_text = directive["content"] if directive else "No company directive set."

    attendee_list = "\n".join(
        f"- {a['name']} ({a.get('role_tier', 'ic').upper()}, {a.get('department', 'Unknown')})"
        for a in attendees
    )

    thread_context = ""
    if thread:
        thread_context = (
            f"\nCurrent narrative thread: [{thread['topic']}] (status: {thread['status']})\n"
            f"Summary: {thread.get('summary', 'No summary yet.')}"
        )

    system_message = (
        f"You are simulating a realistic internal meeting at FakeCo, a B2B software company. "
        f"The simulation date is {sim_time.strftime('%A, %B %d, %Y')}.\n\n"
        f"COMPANY DIRECTION (pinned):\n{directive_text}\n\n"
        f"Write in a realistic, professional-but-casual workplace tone. "
        f"Do NOT invent financial amounts — use only amounts provided. "
        f"Do NOT auto-approve or deny expense requests — that is handled by separate deterministic code. "
        f"Your job is to generate realistic meeting dialogue, decisions, and action items."
    )

    user_message = (
        f"Meeting type: {meeting_type.replace('_', ' ').title()}\n"
        f"Attendees:\n{attendee_list}\n"
        f"{thread_context}\n"
        f"{extra_context}\n\n"
        f"Produce a JSON object with these fields:\n"
        f"  transcript_summary: string (2–5 paragraph meeting summary, natural voice)\n"
        f"  decisions: array of objects, each with fields:\n"
        f"    description: string (concrete decision made, e.g. 'Reassign ticket #42 to Carol')\n"
        f"    stances: object mapping EACH attendee's exact name (as listed above) to their\n"
        f"      stance on this decision: one of 'agree', 'disagree', 'neutral'. Every attendee\n"
        f"      must have an entry for every decision, even if their stance is 'neutral'\n"
        f"      (i.e. they went along with it without strong feelings either way). Base stances\n"
        f"      on realistic workplace dynamics — attendees in the same department, or whose\n"
        f"      priorities align with the decision, are more likely to agree.\n"
        f"  action_items: array of objects with fields: assignee_name, description, due_in_days\n"
        f"  outcome: object with type-specific fields (see below)\n"
        f"  short_summary: one-sentence event summary for the narrative log\n\n"
        f"Outcome type-specific fields:\n"
        f"  standup: {{blockers: [string], completed_yesterday: [string], planned_today: [string]}}\n"
        f"  cross_functional: {{alignment_issues: [string], cross_team_decisions: [string]}}\n"
        f"  pay_negotiation: {{agreed_new_pay: null (leave null — determined by accounting engine), outcome_text: string}}\n"
        f"  performance_review: {{rating: 'meets_expectations'|'exceeds'|'needs_improvement', feedback: string, raise_recommended: boolean, raise_amount: null}}\n"
        f"  crisis_response: {{resolution: string, responsible_employee: string}}\n\n"
        f"Respond with ONLY valid JSON, no markdown fences."
    )

    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]


# ---------------------------------------------------------------------------
# Meeting execution (the core loop)
# ---------------------------------------------------------------------------
async def run_meeting(
    pool: asyncpg.Pool,
    llm: LLMClient,
    mm: MattermostClient,
    wiki: WikiJSClient,
    meeting_type: str,
    department: Optional[str] = None,
    target_employee_id: Optional[int] = None,
    thread_id: Optional[int] = None,
    extra_context: str = "",
) -> dict:
    """
    Runs a complete meeting:
    1. Select attendees.
    2. Fetch thread context.
    3. Get sim time.
    4. Build prompt.
    5. Call LLM (heavy tier).
    6. Parse and persist: meetings row, action_items rows, narrative_event row.
    7. Post to Mattermost.
    8. Return meeting ID and parsed outcome.
    """
    async with httpx.AsyncClient(timeout=10.0) as http:
        sim_time = await get_sim_time(http)

    async with pool.acquire() as conn:
        attendees = await select_attendees(conn, meeting_type, department, target_employee_id)
        if not attendees:
            raise ValueError(f"No attendees could be selected for {meeting_type} ({department})")

        thread = None
        if thread_id:
            thread = await conn.fetchrow("SELECT * FROM narrative_threads WHERE id = $1", thread_id)

        # Build and execute LLM call
        messages = await build_meeting_prompt(conn, meeting_type, attendees, thread, sim_time, extra_context)

    log.info("Meeting: running %s (attendees: %s)", meeting_type, [a["name"] for a in attendees])
    try:
        raw_response = await llm.chat(messages, model="heavy", max_tokens=2500)
    except Exception as exc:
        log.error("LLM call failed for meeting: %s", exc)
        raise

    # Parse LLM output
    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError:
        # Attempt to strip stray markdown fences
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[1:])
        if cleaned.endswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[:-1])
        try:
            parsed = json.loads(cleaned)
        except Exception:
            log.error("Could not parse LLM output as JSON:\n%s", raw_response[:500])
            parsed = {
                "transcript_summary": raw_response[:1000],
                "decisions": [],
                "action_items": [],
                "outcome": {"parse_error": True},
                "short_summary": f"{meeting_type} meeting (parse error)",
            }

    # Persist to DB
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Ensure narrative thread exists for this meeting
            if not thread_id:
                thread_id = await conn.fetchval("""
                    INSERT INTO narrative_threads (topic, department, status, summary)
                    VALUES ($1, $2, 'in_progress', $3)
                    RETURNING id
                """,
                    f"{meeting_type.replace('_', ' ').title()} — {department or 'cross-team'}",
                    department,
                    parsed.get("short_summary", "")
                )

            # Create meetings row
            attendee_ids = [a["id"] for a in attendees]
            meeting_id = await conn.fetchval("""
                INSERT INTO meetings
                    (thread_id, meeting_type, attendees, agenda, transcript_summary,
                     decisions, outcome, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
            """,
                thread_id,
                meeting_type,
                json.dumps(attendee_ids),
                extra_context or f"{meeting_type.replace('_', ' ').title()} meeting",
                parsed.get("transcript_summary", ""),
                json.dumps(parsed.get("decisions", [])),
                json.dumps(parsed.get("outcome", {})),
                sim_time,
            )

            # Create action_items
            for ai in parsed.get("action_items", []):
                # Resolve assignee by name (best-effort match)
                assignee_name = ai.get("assignee_name", "")
                due_in_days = int(ai.get("due_in_days", 3))
                due_at = sim_time + timedelta(days=due_in_days)

                assignee_id = await conn.fetchval(
                    "SELECT id FROM employees WHERE name ILIKE $1 AND status = 'active' LIMIT 1",
                    f"%{assignee_name}%"
                )
                if not assignee_id and attendees:
                    assignee_id = attendees[0]["id"]  # fallback to first attendee

                if assignee_id:
                    await conn.execute("""
                        INSERT INTO action_items
                            (meeting_id, thread_id, owner_employee_id, description, due_at, status)
                        VALUES ($1, $2, $3, $4, $5, 'open')
                    """, meeting_id, thread_id, assignee_id, ai.get("description", ""), due_at)

            # Deterministic relationship-affinity update (Phase 20 §3) — plain Python over the
            # per-attendee `stances` that rode this same LLM call, no second LLM call spent.
            affinity_updates = compute_affinity_updates(parsed.get("decisions", []), attendees)
            if affinity_updates:
                await apply_affinity_updates(conn, affinity_updates)
                log.info("Meeting: applied %d affinity update(s): %s", len(affinity_updates), affinity_updates)

            # Create narrative_event
            await conn.execute("""
                INSERT INTO narrative_events
                    (thread_id, origin, source_type, source_ref, short_summary, created_at)
                VALUES ($1, 'ai', 'meeting', $2, $3, $4)
            """,
                thread_id,
                f"meeting:{meeting_id}",
                parsed.get("short_summary", f"{meeting_type} meeting"),
                sim_time,
            )

            # Update narrative_thread summary
            await conn.execute("""
                UPDATE narrative_threads SET summary = $1, updated_at = $2 WHERE id = $3
            """, parsed.get("transcript_summary", "")[:500], sim_time, thread_id)

    # Post to Mattermost
    try:
        channel_name = f"meetings-{meeting_type.replace('_', '-')}"
        if department:
            channel_name = f"meetings-{department.lower()}-{meeting_type.replace('_', '-')}"
        channel_name = channel_name[:64]  # Mattermost channel name limit
        channel_id = await mm.get_or_create_channel(
            name=channel_name,
            display_name=f"Meeting: {meeting_type.replace('_', ' ').title()} — {department or 'Cross-Team'}",
            purpose="Auto-generated meeting minutes",
        )
        mm_text = (
            f"### 📋 {meeting_type.replace('_', ' ').title()} — {sim_time.strftime('%Y-%m-%d')}\n\n"
            f"**Attendees:** {', '.join(a['name'] for a in attendees)}\n\n"
            f"{parsed.get('transcript_summary', '')[:2000]}\n\n"
        )
        if parsed.get("decisions"):
            mm_text += "**Decisions:**\n" + "\n".join(f"- {decision_text(d)}" for d in parsed["decisions"]) + "\n\n"
        if parsed.get("action_items"):
            mm_text += "**Action Items:**\n" + "\n".join(
                f"- [{ai.get('assignee_name', '?')}] {ai.get('description', '')}"
                for ai in parsed["action_items"]
            ) + "\n"
        post_id = await mm.post_message(channel_id, mm_text)
        log.info("Meeting %d posted to Mattermost channel %s (post_id=%s)", meeting_id, channel_name, post_id)
    except Exception as exc:
        log.warning("Failed to post meeting to Mattermost: %s", exc)

    # Create Wiki.js meeting-notes page
    try:
        wiki_path = f"meeting-notes/{department.lower()}/{sim_time.strftime('%Y-%m-%d')}-{meeting_id}" \
            if department else f"meeting-notes/cross-team/{sim_time.strftime('%Y-%m-%d')}-{meeting_id}"
        wiki_title = f"{meeting_type.replace('_', ' ').title()} — {sim_time.strftime('%Y-%m-%d')} ({department or 'Cross-Team'})"
        wiki_content = (
            f"# {wiki_title}\n\n"
            f"**Attendees:** {', '.join(a['name'] for a in attendees)}\n\n"
            f"## Summary\n\n{parsed.get('transcript_summary', '')}\n\n"
        )
        if parsed.get("decisions"):
            wiki_content += "## Decisions\n\n" + "\n".join(f"- {decision_text(d)}" for d in parsed["decisions"]) + "\n\n"
        if parsed.get("action_items"):
            wiki_content += "## Action Items\n\n" + "\n".join(
                f"- [{ai.get('assignee_name', '?')}] {ai.get('description', '')}"
                for ai in parsed["action_items"]
            ) + "\n"
        await wiki.create_page(
            path=wiki_path,
            title=wiki_title,
            content=wiki_content,
            tags=[meeting_type],
        )
        log.info("Meeting %d: created Wiki.js meeting-notes page at %s", meeting_id, wiki_path)
    except Exception as exc:
        log.warning("Failed to create Wiki.js meeting-notes page for meeting %d: %s", meeting_id, exc)

    # Handle outcome consequences for certain meeting types
    outcome = parsed.get("outcome", {})
    if meeting_type == "performance_review":
        raise_recommended = outcome.get("raise_recommended", False)
        if raise_recommended:
            log.info(
                "Meeting %d: performance_review recommends raise for employee %s — "
                "sending to accounting-engine (Phase 24 wires pay outcome)",
                meeting_id, target_employee_id
            )
            # Phase 24 will wire this. Stub: log it as an action item for the lead.

    log.info("Meeting %d complete: %s (%s)", meeting_id, meeting_type, department or "cross-team")
    return {
        "meeting_id": meeting_id,
        "thread_id": thread_id,
        "meeting_type": meeting_type,
        "attendees": [a["name"] for a in attendees],
        "outcome": outcome,
        "short_summary": parsed.get("short_summary", ""),
        "action_items_created": len(parsed.get("action_items", [])),
    }


# ---------------------------------------------------------------------------
# FastAPI app + scheduler
# ---------------------------------------------------------------------------
_pool: asyncpg.Pool | None = None
_llm: LLMClient | None = None
_mm: MattermostClient | None = None
_wiki: WikiJSClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _llm, _mm, _wiki
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    _llm = LLMClient(LITELLM_URL, LITELLM_API_KEY)
    _mm = MattermostClient(MATTERMOST_URL, MATTERMOST_BOT_TOKEN, MATTERMOST_TEAM_ID)
    _wiki = WikiJSClient(WIKIJS_URL, WIKIJS_ADMIN_TOKEN)
    log.info("meeting-simulator: ready")
    yield
    if _llm:
        await _llm.close()
    if _mm:
        await _mm.close()
    if _wiki:
        await _wiki.close()
    if _pool:
        await _pool.close()


app = FastAPI(
    title="FakeCo Meeting Simulator",
    description="Generates and persists realistic internal meetings using LLM + deterministic attendee selection.",
    version="1.0.0",
    lifespan=lifespan,
)


async def get_pool_dep() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Pool not initialized")
    return _pool


PoolDep = Annotated[asyncpg.Pool, Depends(get_pool_dep)]


# --- API models ---
class RunMeetingRequest(BaseModel):
    meeting_type: str = Field(..., description="standup|cross_functional|pay_negotiation|performance_review|crisis_response")
    department: Optional[str] = None
    target_employee_id: Optional[int] = None
    thread_id: Optional[int] = None
    extra_context: str = ""


class MeetingResult(BaseModel):
    meeting_id: int
    thread_id: int
    meeting_type: str
    attendees: list[str]
    short_summary: str
    action_items_created: int


# --- Endpoints ---
@app.get("/health")
async def health():
    return {"status": "ok", "service": "meeting-simulator"}


@app.post("/meeting/run", response_model=MeetingResult)
async def trigger_meeting(req: RunMeetingRequest, pool: PoolDep):
    """Trigger a single meeting run. Called by the orchestrator on its schedule."""
    if _llm is None or _mm is None or _wiki is None:
        raise HTTPException(status_code=503, detail="LLM, Mattermost, or Wiki.js client not ready")

    result = await run_meeting(
        pool=pool,
        llm=_llm,
        mm=_mm,
        wiki=_wiki,
        meeting_type=req.meeting_type,
        department=req.department,
        target_employee_id=req.target_employee_id,
        thread_id=req.thread_id,
        extra_context=req.extra_context,
    )
    return MeetingResult(**result)


@app.get("/meetings/pending-performance-reviews")
async def get_pending_performance_reviews(pool: PoolDep):
    """
    Returns list of employees eligible for a performance review.
    Spec §6.3: skip employees with < 1 full cycle tenure or
    if their department has < 2 members.
    SPEC_CLARIFICATIONS #6: cold start exemption.
    """
    async with pool.acquire() as conn:
        eligible = await conn.fetch("""
            SELECT e.id, e.name, e.department, e.hired_at
            FROM employees e
            WHERE e.status = 'active'
              AND e.hired_at < NOW() - INTERVAL '90 days'
              AND (
                SELECT COUNT(*) FROM employees e2
                WHERE e2.department = e.department AND e2.status = 'active'
              ) >= 2
            ORDER BY e.hired_at
        """)
        return [dict(e) for e in eligible]
