"""
provisioning/main.py — FakeCo "Real Appliances"
Phase 14: Per-employee account provisioning across all appliances.

Spec §9, §7, §26:
- Creates real accounts on docker-mailserver, Mattermost, Zammad, Wiki.js
- Writes back resulting appliance IDs to the employees roster row
- Idempotent: re-running for the same employee does NOT create duplicate accounts
- Fire path: status → 'terminated', deactivates (never deletes) accounts everywhere

SPEC_CLARIFICATIONS #10: Placeholder roster is seeded in migration 003_employees.sql.

Usage (CLI, no dashboard needed until Phase 34):
    python main.py provision --employee-id 1
    python main.py provision --all
    python main.py fire --employee-id 5
    python main.py provision-principal

Environment:
    DATABASE_URL, MAILSERVER_HOST, MATTERMOST_URL, MATTERMOST_ADMIN_TOKEN,
    ZAMMAD_URL, ZAMMAD_ADMIN_TOKEN, WIKIJS_URL, WIKIJS_ADMIN_TOKEN,
    MAILSERVER_DOMAIN
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","service":"provisioning","msg":"%(message)s"}'
)
log = logging.getLogger("provisioning")

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql://{os.environ.get('POSTGRES_USER','fakeco')}:"
    f"{os.environ.get('POSTGRES_PASSWORD','fakeco')}@"
    f"{os.environ.get('POSTGRES_HOST','postgres')}:"
    f"{os.environ.get('POSTGRES_PORT','5432')}/"
    f"{os.environ.get('POSTGRES_DB','fakeco')}"
)
MAILSERVER_DOMAIN = os.environ.get("MAILSERVER_DOMAIN", "fakecorp.internal")
MAILSERVER_CONTAINER = os.environ.get("MAILSERVER_CONTAINER", "fakeco-mailserver")
MATTERMOST_URL = os.environ.get("MATTERMOST_URL", "http://mattermost:8065")
MATTERMOST_ADMIN_TOKEN = os.environ.get("MATTERMOST_ADMIN_TOKEN", "")
MATTERMOST_TEAM_ID = os.environ.get("MATTERMOST_TEAM_ID", "")  # written at first-boot
ZAMMAD_URL = os.environ.get("ZAMMAD_URL", "http://zammad-nginx:8080")
ZAMMAD_ADMIN_TOKEN = os.environ.get("ZAMMAD_ADMIN_TOKEN", "")
WIKIJS_URL = os.environ.get("WIKIJS_URL", "http://wikijs:3000")
WIKIJS_ADMIN_TOKEN = os.environ.get("WIKIJS_ADMIN_TOKEN", "")
PRINCIPAL_EMAIL = os.environ.get("PRINCIPAL_EMAIL", "principal@fakecorp.internal")
PRINCIPAL_NAME = os.environ.get("PRINCIPAL_NAME", "Admin")
PERSONALITY_LIBRARY_PATH = Path(
    os.environ.get("PERSONALITY_LIBRARY_PATH", "/app/personality-library")
)

# Provisioning bootstrap: used for setup email add command against docker-mailserver
# In Docker context, we exec into the mailserver container.
DOCKER_HOST = os.environ.get("DOCKER_HOST", "unix:///var/run/docker.sock")


# ---------------------------------------------------------------------------
# Reusable employee personality library
# ---------------------------------------------------------------------------
_PERSONALITY_REQUIRED_FIELDS = {
    "id", "short_label", "background", "core_personality", "communication_style",
    "chat_style", "email_style", "motivations", "strengths", "flaws",
    "conflict_style", "decision_style", "work_habits", "quirks",
    "relationship_tendencies", "response_guidance", "prohibited_assumptions",
}


def _concise_personality(profile: dict) -> str:
    """Keep existing meeting prompts useful without injecting the full biography."""
    parts = [
        profile["core_personality"],
        f"Communication: {profile['communication_style']}",
        f"Decision style: {profile['decision_style']}",
        f"Response guidance: {profile['response_guidance']}",
    ]
    return "\n".join(str(part).strip() for part in parts if str(part).strip())


async def sync_personality_library(conn: asyncpg.Connection) -> int:
    """Validate/upsert the canonical JSON library and assign every unassigned employee."""
    if not PERSONALITY_LIBRARY_PATH.exists():
        raise RuntimeError(f"Personality library not found: {PERSONALITY_LIBRARY_PATH}")
    files = (
        sorted(PERSONALITY_LIBRARY_PATH.glob("*.json"))
        if PERSONALITY_LIBRARY_PATH.is_dir()
        else [PERSONALITY_LIBRARY_PATH]
    )
    profiles: list[dict] = []
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        batch = payload.get("profiles") if isinstance(payload, dict) else None
        if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not isinstance(batch, list) or not batch:
            raise RuntimeError(f"Invalid personality library batch: {path}")
        profiles.extend(batch)
    if not profiles:
        raise RuntimeError("Personality library contains no profiles")

    seen: set[str] = set()
    for profile in profiles:
        missing = _PERSONALITY_REQUIRED_FIELDS - set(profile) if isinstance(profile, dict) else _PERSONALITY_REQUIRED_FIELDS
        if missing:
            raise RuntimeError(f"Invalid personality profile; missing fields: {sorted(missing)}")
        profile_id = str(profile["id"])
        if profile_id in seen:
            raise RuntimeError(f"Duplicate personality profile id: {profile_id}")
        seen.add(profile_id)
        await conn.execute("""
            INSERT INTO personality_profiles (id, short_label, profile, updated_at)
            VALUES ($1, $2, $3::jsonb, NOW())
            ON CONFLICT (id) DO UPDATE
            SET short_label = EXCLUDED.short_label,
                profile = EXCLUDED.profile,
                updated_at = NOW()
        """, profile_id, str(profile["short_label"]), json.dumps(profile))

    employee_ids = await conn.fetch(
        "SELECT id FROM employees WHERE personality_profile_id IS NULL ORDER BY id"
    )
    for row in employee_ids:
        await assign_personality_profile(conn, row["id"])
    log.info("Personality library: synced %d profiles; assigned %d employee(s)", len(profiles), len(employee_ids))
    return len(profiles)


async def assign_personality_profile(conn: asyncpg.Connection, employee_id: int) -> Optional[str]:
    """Choose randomly among least-used profiles, then keep that assignment stable."""
    current = await conn.fetchval(
        "SELECT personality_profile_id FROM employees WHERE id = $1", employee_id
    )
    if current:
        return str(current)
    selected = await conn.fetchrow("""
        SELECT p.id, p.profile
        FROM personality_profiles p
        LEFT JOIN employees e ON e.personality_profile_id = p.id
        GROUP BY p.id, p.profile
        ORDER BY COUNT(e.id), RANDOM()
        LIMIT 1
    """)
    if not selected:
        raise RuntimeError("Cannot assign employee personality: profile library is empty")
    profile = selected["profile"]
    if isinstance(profile, str):
        profile = json.loads(profile)
    await conn.execute("""
        UPDATE employees
        SET personality_profile_id = $2,
            personality = $3
        WHERE id = $1 AND personality_profile_id IS NULL
    """, employee_id, selected["id"], _concise_personality(profile))
    return str(selected["id"])


# ---------------------------------------------------------------------------
# Mattermost helpers
# ---------------------------------------------------------------------------
class MattermostClient:
    def __init__(self, base_url: str, admin_token: str, team_id: str = ""):
        self.base = base_url.rstrip("/") + "/api/v4"
        self.headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        self.team_id = team_id
        self._client = httpx.AsyncClient(headers=self.headers, timeout=30.0)

    async def close(self):
        await self._client.aclose()

    async def get_user_by_email(self, email: str) -> Optional[dict]:
        r = await self._client.get(f"{self.base}/users/email/{email}")
        if r.status_code == 200:
            return r.json()
        return None

    async def create_bot(self, username: str, display_name: str, description: str = "") -> dict:
        """Create a bot account. Returns bot user dict."""
        r = await self._client.post(f"{self.base}/bots", json={
            "username": username,
            "display_name": display_name,
            "description": description,
        })
        r.raise_for_status()
        return r.json()

    async def get_bot_by_username(self, username: str) -> Optional[dict]:
        """Check if a bot with this username exists."""
        r = await self._client.get(f"{self.base}/users/username/{username}")
        if r.status_code == 200:
            return r.json()
        return None

    async def disable_user(self, user_id: str) -> None:
        """Deactivate (disable) a Mattermost user. Does NOT delete."""
        r = await self._client.delete(f"{self.base}/users/{user_id}")
        r.raise_for_status()

    async def add_to_team(self, user_id: str, team_id: str) -> None:
        r = await self._client.post(f"{self.base}/teams/{team_id}/members", json={
            "team_id": team_id,
            "user_id": user_id,
        })
        if r.status_code not in (200, 201):
            log.warning("Mattermost: could not add user %s to team %s: %s", user_id, team_id, r.text)

    async def create_human_account(self, email: str, username: str, name: str, password: str) -> dict:
        """Create a real human account (for the Principal). Returns user dict."""
        r = await self._client.post(f"{self.base}/users", json={
            "email": email,
            "username": username,
            "first_name": name.split()[0] if name else name,
            "last_name": " ".join(name.split()[1:]) if len(name.split()) > 1 else "",
            "password": password,
            "email_verified": True,
        })
        r.raise_for_status()
        return r.json()

    async def generate_bot_token(self, user_id: str, description: str = "bot token") -> str:
        """Create a personal access token for a bot. Returns the token string."""
        r = await self._client.post(f"{self.base}/users/{user_id}/tokens", json={
            "description": description
        })
        r.raise_for_status()
        return r.json()["token"]


# ---------------------------------------------------------------------------
# Zammad helpers
# ---------------------------------------------------------------------------
class ZammadClient:
    def __init__(self, base_url: str, admin_token: str):
        self.base = base_url.rstrip("/") + "/api/v1"
        self.headers = {"Authorization": f"Token token={admin_token}", "Content-Type": "application/json"}
        self._client = httpx.AsyncClient(headers=self.headers, timeout=30.0)

    async def close(self):
        await self._client.aclose()

    async def get_user_by_email(self, email: str) -> Optional[dict]:
        r = await self._client.get(f"{self.base}/users/search?query=email:{email}")
        if r.status_code == 200:
            users = r.json()
            return users[0] if users else None
        return None

    async def create_user(self, email: str, firstname: str, lastname: str, role_names: list[str] = None) -> dict:
        role_names = role_names or ["Agent"]
        r = await self._client.post(f"{self.base}/users", json={
            "email": email,
            "firstname": firstname,
            "lastname": lastname,
            "roles": role_names,
            "active": True,
        })
        r.raise_for_status()
        return r.json()

    async def deactivate_user(self, user_id: int) -> None:
        """Deactivate a Zammad user. Does NOT delete."""
        r = await self._client.put(f"{self.base}/users/{user_id}", json={"active": False})
        r.raise_for_status()


# ---------------------------------------------------------------------------
# Wiki.js helpers (GraphQL)
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

    async def get_user_by_email(self, email: str) -> Optional[dict]:
        # NOTE: requesting `isActive` here used to crash the whole query with
        # "Cannot return null for non-nullable field UserMinimal.isActive" — Wiki.js's search
        # index returns a null isActive for at least some freshly-created accounts even though
        # the field is declared non-nullable in its own schema. We don't need it for lookup
        # purposes, so just don't ask for it.
        result = await self.graphql("""
            query($email: String!) {
                users {
                    search(query: $email) {
                        id
                        email
                        name
                    }
                }
            }
        """, {"email": email})
        users = (result.get("data") or {}).get("users") or {}
        users = users.get("search") or []
        for user in users:
            if user.get("email", "").lower() == email.lower():
                return user
        return None

    async def create_user(self, email: str, name: str, password_reset: bool = True) -> dict:
        # Wiki.js's `passwordRaw` arg is nullable in the schema but the resolver rejects a blank
        # password for the "local" provider at runtime ("Password raw can't be blank") — bot
        # accounts never log in interactively, so derive a password the same deterministic way
        # mail accounts do rather than requiring a human-entered one.
        password = hashlib.sha256(
            f"{os.environ.get('MAILSERVER_BOT_SECRET', 'fakeco-bot-mail-secret-change-me')}:wikijs:{email}".encode()
        ).hexdigest()[:24]
        result = await self.graphql("""
            mutation($email: String!, $name: String!, $passwordRaw: String!, $providerKey: String!, $groups: [Int]!, $mustChangePassword: Boolean, $sendWelcomeEmail: Boolean) {
                users {
                    create(email: $email, name: $name, passwordRaw: $passwordRaw, providerKey: $providerKey, groups: $groups, mustChangePassword: $mustChangePassword, sendWelcomeEmail: $sendWelcomeEmail) {
                        responseResult {
                            succeeded
                            errorCode
                            slug
                            message
                        }
                        user {
                            id
                            email
                            name
                        }
                    }
                }
            }
        """, {
            "email": email,
            "name": name,
            "passwordRaw": password,
            "providerKey": "local",
            "groups": [1],  # Default group ID — Guests (1) or Editors (2); adjust in first-boot
            "mustChangePassword": False,
            "sendWelcomeEmail": False,
        })
        create_result = ((result.get("data") or {}).get("users") or {}).get("create") or {}
        if not create_result.get("responseResult", {}).get("succeeded"):
            raise RuntimeError(f"Wiki.js user creation failed: {create_result}")
        # `.get("user", {})` only falls back to {} when the key is missing, not when it's
        # explicitly `null` (which is what Wiki.js returns here) — guard against None too.
        return create_result.get("user") or {}

    async def deactivate_user(self, user_id: int) -> None:
        await self.graphql("""
            mutation($id: Int!) {
                users {
                    deactivate(id: $id) {
                        responseResult { succeeded errorCode message }
                    }
                }
            }
        """, {"id": user_id})


# ---------------------------------------------------------------------------
# Mail helpers (docker-mailserver uses its own CLI via docker exec)
# We call the Docker socket-proxy (or a thin shell wrapper) to exec setup commands.
# In Phase 14, we use a simplified HTTP helper that the provisioning service calls.
# ---------------------------------------------------------------------------
class MailserverClient:
    """
    Wraps docker-mailserver account management.
    In Docker, calls docker exec fakeco-mailserver setup email add <email> <password>
    via a local subprocess (provisioning container must be on same Docker daemon).

    Password is deterministically derived from employee email + a server secret.
    Employees never need to know their sim-email password; they're bots.
    """
    def __init__(self, container_name: str = "fakeco-mailserver", mail_domain: str = "fakecorp.internal"):
        self.container = container_name
        self.domain = mail_domain

    def _derive_password(self, email: str) -> str:
        """
        Deterministic bot password. NOT for human security — sim mailboxes only.
        Derived from email + a fixed salt. Stored nowhere; re-derivable.
        """
        salt = os.environ.get("MAILSERVER_BOT_SECRET", "fakeco-bot-mail-secret-change-me")
        return hashlib.sha256(f"{salt}:{email}".encode()).hexdigest()[:24]

    async def account_exists(self, email: str) -> bool:
        """Check if an email account exists by listing accounts."""
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", self.container,
            "setup", "email", "list",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return email in stdout.decode(errors="replace")

    async def create_account(self, email: str) -> bool:
        """Create mailbox. Idempotent: check first."""
        if await self.account_exists(email):
            log.info("mail: account %s already exists, skipping", email)
            return False
        password = self._derive_password(email)
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", self.container,
            "setup", "email", "add", email, password,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"mail: create_account failed for {email}: {stderr.decode()}")
        log.info("mail: created account %s", email)
        return True

    async def restrict_account(self, email: str) -> None:
        """
        Restrict/lock a mailbox for termination — blocks send AND receive without deleting
        the mailbox or its contents (spec §9: deactivate everywhere, never delete).
        Real docker-mailserver CLI syntax is `setup email restrict <add|del|list> <send|receive>
        <email>` — a single `setup email restrict <email>` (no direction) is not a valid
        invocation and silently no-ops (docker-mailserver still exits 0 on an unrecognized
        subcommand shape here, so this went unnoticed without an actual runtime check).
        """
        for direction in ("send", "receive"):
            proc = await asyncio.create_subprocess_exec(
                "docker", "exec", self.container,
                "setup", "email", "restrict", "add", direction, email,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"mail: restrict ({direction}) failed for {email}: {stderr.decode()}")
        log.info("mail: restricted account %s (send+receive blocked, mailbox preserved)", email)


# ---------------------------------------------------------------------------
# Core provisioning logic
# ---------------------------------------------------------------------------
async def provision_employee(
    conn: asyncpg.Connection,
    employee: asyncpg.Record,
    mm: MattermostClient,
    zammad: ZammadClient,
    wiki: WikiJSClient,
    mail: MailserverClient,
) -> None:
    """
    Provision one employee across all four appliances.
    Idempotent: skips any appliance where the account already exists.
    Writes back appliance IDs to the employees row when new accounts are created.
    """
    emp_id = employee["id"]
    name = employee["name"]
    email = employee["email"]
    parts = name.split()
    firstname = parts[0]
    lastname = " ".join(parts[1:]) if len(parts) > 1 else ""
    # Mattermost username: lowercase, no spaces, no @
    mm_username = email.split("@")[0].replace(".", "_").lower()

    updates = {}

    # -- docker-mailserver --
    log.info("Provisioning mail for %s (%s)...", name, email)
    try:
        await mail.create_account(email)
        updates["mailbox_address"] = email
    except Exception as exc:
        log.error("mail: failed for %s: %s", email, exc)

    # -- Mattermost --
    log.info("Provisioning Mattermost for %s (%s)...", name, email)
    existing_mm = await mm.get_bot_by_username(mm_username)
    if existing_mm:
        mm_id = existing_mm["id"]
        log.info("Mattermost: bot %s already exists (id=%s)", mm_username, mm_id)
    else:
        try:
            bot = await mm.create_bot(
                username=mm_username,
                display_name=name,
                description=f"FakeCo bot account for {name}",
            )
            mm_id = bot["user_id"]
            log.info("Mattermost: created bot %s (id=%s)", mm_username, mm_id)
        except Exception as exc:
            log.error("Mattermost: failed for %s: %s", name, exc)
            mm_id = None
    if mm_id and mm.team_id:
        await mm.add_to_team(mm_id, mm.team_id)
    if mm_id:
        updates["mattermost_id"] = mm_id

    # -- Zammad --
    log.info("Provisioning Zammad for %s (%s)...", name, email)
    existing_zammad = await zammad.get_user_by_email(email)
    if existing_zammad:
        zammad_id = str(existing_zammad["id"])
        log.info("Zammad: user %s already exists (id=%s)", email, zammad_id)
    else:
        try:
            user = await zammad.create_user(email, firstname, lastname, role_names=["Agent"])
            zammad_id = str(user["id"])
            log.info("Zammad: created agent %s (id=%s)", email, zammad_id)
        except Exception as exc:
            log.error("Zammad: failed for %s: %s", name, exc)
            zammad_id = None
    if zammad_id:
        updates["zammad_agent_id"] = zammad_id

    # -- Wiki.js --
    log.info("Provisioning Wiki.js for %s (%s)...", name, email)
    existing_wiki = await wiki.get_user_by_email(email)
    if existing_wiki:
        wiki_id = str(existing_wiki["id"])
        log.info("Wiki.js: user %s already exists (id=%s)", email, wiki_id)
    else:
        try:
            user = await wiki.create_user(email, name)
            wiki_id = str(user.get("id", ""))
            if not wiki_id:
                # Wiki.js's `create` mutation response has `user: null` even on success in
                # this version — look the account up by email to get its real ID.
                created = await wiki.get_user_by_email(email)
                wiki_id = str(created["id"]) if created else ""
            log.info("Wiki.js: created user %s (id=%s)", email, wiki_id)
        except Exception as exc:
            log.error("Wiki.js: failed for %s: %s", name, exc)
            wiki_id = None
    if wiki_id:
        updates["wiki_user_id"] = wiki_id

    # Write back IDs to the roster row
    if updates:
        set_clauses = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates.keys()))
        values = [emp_id] + list(updates.values())
        await conn.execute(
            f"UPDATE employees SET {set_clauses} WHERE id = $1",
            *values
        )
        log.info("Roster updated for employee %d with: %s", emp_id, list(updates.keys()))

    await seed_employee_relationships(conn, employee)


async def seed_employee_relationships(conn: asyncpg.Connection, employee: asyncpg.Record) -> None:
    """
    Phase 20 (spec §5): on first provisioning, seed 1-2 lightweight starting
    `employee_relationships` rows for the new hire — deterministic, no LLM call.

    Picks up to 2 other active same-department employees (closest in hire order,
    excluding self), default relationship_type='neutral' and a small positive
    affinity_score. Respects the schema's canonical-ordering CHECK
    (employee_a_id < employee_b_id) and UNIQUE(employee_a_id, employee_b_id) —
    idempotent via ON CONFLICT DO NOTHING, so re-running provisioning never
    duplicates or overwrites relationships that may have since evolved via
    meeting-simulator's affinity updates (Phase 20 §3).
    """
    emp_id = employee["id"]
    department = employee["department"]
    if not department:
        return

    peers = await conn.fetch(
        """
        SELECT id FROM employees
        WHERE department = $1 AND status = 'active' AND id != $2
        ORDER BY hired_at ASC, id ASC
        LIMIT 2
        """,
        department, emp_id,
    )
    if not peers:
        log.info("Relationships: no same-department peers yet for employee %d, skipping seed", emp_id)
        return

    seeded = 0
    for peer in peers:
        peer_id = peer["id"]
        a_id, b_id = (emp_id, peer_id) if emp_id < peer_id else (peer_id, emp_id)
        result = await conn.execute(
            """
            INSERT INTO employee_relationships
                (employee_a_id, employee_b_id, relationship_type, affinity_score, notes)
            VALUES ($1, $2, 'neutral', 10, 'Seeded at hire time: same-department starting relationship')
            ON CONFLICT (employee_a_id, employee_b_id) DO NOTHING
            """,
            a_id, b_id,
        )
        if result.endswith("1"):
            seeded += 1
    log.info("Relationships: seeded %d starting relationship row(s) for employee %d (%s)", seeded, emp_id, department)


async def fire_employee(
    conn: asyncpg.Connection,
    employee: asyncpg.Record,
    mm: MattermostClient,
    zammad: ZammadClient,
    wiki: WikiJSClient,
    mail: MailserverClient,
) -> None:
    """
    Fire path: status → 'terminated'; deactivate (never delete) accounts everywhere.
    Spec §9: "deactivate (never delete) accounts everywhere"
    """
    emp_id = employee["id"]
    name = employee["name"]
    email = employee["email"]
    log.info("Firing employee %d (%s)...", emp_id, name)

    # Update roster status
    await conn.execute(
        "UPDATE employees SET status = 'terminated', terminated_at = NOW() WHERE id = $1",
        emp_id
    )

    # Deactivate Mattermost
    if employee["mattermost_id"]:
        try:
            await mm.disable_user(employee["mattermost_id"])
            log.info("Mattermost: deactivated user %s", employee["mattermost_id"])
        except Exception as exc:
            log.error("Mattermost deactivation failed for %s: %s", name, exc)

    # Deactivate Zammad
    if employee["zammad_agent_id"]:
        try:
            await zammad.deactivate_user(int(employee["zammad_agent_id"]))
            log.info("Zammad: deactivated user %s", employee["zammad_agent_id"])
        except Exception as exc:
            log.error("Zammad deactivation failed for %s: %s", name, exc)

    # Deactivate Wiki.js
    if employee["wiki_user_id"]:
        try:
            await wiki.deactivate_user(int(employee["wiki_user_id"]))
            log.info("Wiki.js: deactivated user %s", employee["wiki_user_id"])
        except Exception as exc:
            log.error("Wiki.js deactivation failed for %s: %s", name, exc)

    # Restrict mail: blocks send+receive without deleting the mailbox/contents
    if employee["mailbox_address"]:
        try:
            await mail.restrict_account(employee["mailbox_address"])
        except Exception as exc:
            log.error("Mail restriction failed for %s: %s", name, exc)

    # Orphaned action_items for this employee will be handled by the orchestrator reassignment logic.
    await reassign_pending_reactions(conn, employee)
    log.info("Fire complete for %d (%s). Accounts deactivated (not deleted).", emp_id, name)


async def reassign_pending_reactions(conn: asyncpg.Connection, employee: asyncpg.Record) -> None:
    """
    Phase 17 exit criteria: firing an employee with a pending pending_reactions
    row must reassign it (not orphan it) — pending_reactions.target_employee_id
    is ON DELETE CASCADE but employees rows are never actually deleted (soft
    delete only, status='terminated'), so no DB cascade will ever fire here;
    reassignment has to be explicit.

    Selection: same-department, same-role_tier active employee (closest
    substitute), falling back to any active employee. No action_items
    reassignment logic exists yet to mirror exactly (see comment above), so
    this is a simple, self-consistent version of that same idea.
    """
    emp_id = employee["id"]
    pending = await conn.fetch(
        "SELECT id FROM pending_reactions WHERE target_employee_id = $1 AND status = 'pending'",
        emp_id,
    )
    if not pending:
        return

    replacement_id = await conn.fetchval("""
        SELECT id FROM employees
        WHERE status = 'active' AND id != $1 AND department = $2 AND role_tier = $3
        ORDER BY hired_at ASC LIMIT 1
    """, emp_id, employee["department"], employee["role_tier"])

    if not replacement_id:
        replacement_id = await conn.fetchval("""
            SELECT id FROM employees WHERE status = 'active' AND id != $1
            ORDER BY hired_at ASC LIMIT 1
        """, emp_id)

    if not replacement_id:
        log.warning("Fire: no active employee available to reassign %d pending_reactions from %s",
                    len(pending), employee["name"])
        return

    await conn.execute("""
        UPDATE pending_reactions SET target_employee_id = $1
        WHERE target_employee_id = $2 AND status = 'pending'
    """, replacement_id, emp_id)
    log.info("Fire: reassigned %d pending_reactions row(s) from %d to %d", len(pending), emp_id, replacement_id)


# ---------------------------------------------------------------------------
# Phase 34: FastAPI HTTP service mode ("serve") — dashboard's HR tab needs a
# live Fire/Hire endpoint to call; provisioning was CLI-only through Phase 14.
# This is additive: `python main.py serve` runs the app below; every other
# invocation (`provision --all`, `fire --employee-id N`, `provision-principal`)
# still goes through the original argparse CLI in main() further down,
# unchanged, so first-boot scripts/manual runs keep working exactly as before.
# ---------------------------------------------------------------------------
_svc_pool: Optional[asyncpg.Pool] = None
_svc_mm: Optional[MattermostClient] = None
_svc_zammad: Optional[ZammadClient] = None
_svc_wiki: Optional[WikiJSClient] = None
_svc_mail: Optional[MailserverClient] = None


@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _svc_pool, _svc_mm, _svc_zammad, _svc_wiki, _svc_mail
    _svc_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=5)
    async with _svc_pool.acquire() as conn:
        await sync_personality_library(conn)
    _svc_mm = MattermostClient(MATTERMOST_URL, MATTERMOST_ADMIN_TOKEN, MATTERMOST_TEAM_ID)
    _svc_zammad = ZammadClient(ZAMMAD_URL, ZAMMAD_ADMIN_TOKEN)
    _svc_wiki = WikiJSClient(WIKIJS_URL, WIKIJS_ADMIN_TOKEN)
    _svc_mail = MailserverClient(MAILSERVER_CONTAINER, MAILSERVER_DOMAIN)
    log.info("provisioning: HTTP service ready")
    yield
    await _svc_mm.close()
    await _svc_zammad.close()
    await _svc_wiki.close()
    await _svc_pool.close()


app = FastAPI(
    title="FakeCo Provisioning Service",
    description="Phase 14 CLI + Phase 34 HTTP wrapper: Fire/Hire for the dashboard HR tab.",
    version="1.0.0",
    lifespan=_lifespan,
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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "provisioning"}


class HireRequest(BaseModel):
    name: str
    department: str
    title: str
    role_tier: str = "ic"  # 'ic' or 'lead'


class FireRequest(BaseModel):
    employee_id: int


def _slugify_email(name: str) -> str:
    parts = re.sub(r"[^A-Za-z ]", "", name).strip().split()
    if not parts:
        parts = ["new", "hire"]
    local = ".".join(p.lower() for p in parts)
    return f"{local}@{MAILSERVER_DOMAIN}"


@app.post("/hire")
async def hire_employee_endpoint(req: HireRequest):
    """
    Phase 34 HR tab "Hire" form: department + title (+ name, needed since
    employees.name/email are NOT NULL/UNIQUE — the dashboard form collects
    all three). Inserts a real employees row (pay_rate defaulted from
    market_benchmark for the department/tier, falling back to 0 if no
    benchmark row exists), then runs the exact same provision_employee()
    flow the Phase 14 CLI uses — no duplicated account-creation logic.
    """
    if req.role_tier not in ("ic", "lead"):
        raise HTTPException(status_code=422, detail="role_tier must be 'ic' or 'lead'")
    email = _slugify_email(req.name)
    async with _svc_pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM employees WHERE email = $1", email)
        if existing:
            raise HTTPException(status_code=409, detail=f"Employee with email {email} already exists (id={existing['id']})")

        benchmark = await conn.fetchval(
            "SELECT benchmark_pay FROM market_benchmark WHERE department = $1 AND role_tier = $2",
            req.department, req.role_tier,
        )
        pay_rate = benchmark or 0

        emp = await conn.fetchrow("""
            INSERT INTO employees (name, email, department, role, role_tier, status, hired_at, pay_rate, pay_frequency)
            VALUES ($1, $2, $3, $4, $5, 'active', NOW(), $6, 'biweekly')
            RETURNING *
        """, req.name, email, req.department, req.title, req.role_tier, pay_rate)

        await assign_personality_profile(conn, emp["id"])
        emp = await conn.fetchrow("SELECT * FROM employees WHERE id = $1", emp["id"])

        await provision_employee(conn, emp, _svc_mm, _svc_zammad, _svc_wiki, _svc_mail)

    log.info("HTTP /hire: provisioned new employee %d (%s, %s / %s)", emp["id"], req.name, req.department, req.title)
    return {"status": "hired", "employee_id": emp["id"], "email": email, "pay_rate": float(pay_rate)}


@app.post("/fire")
async def fire_employee_endpoint(req: FireRequest):
    async with _svc_pool.acquire() as conn:
        emp = await conn.fetchrow("SELECT * FROM employees WHERE id = $1", req.employee_id)
        if not emp:
            raise HTTPException(status_code=404, detail=f"Employee {req.employee_id} not found")
        if emp["status"] == "terminated":
            return {"status": "already_terminated", "employee_id": req.employee_id}
        await fire_employee(conn, emp, _svc_mm, _svc_zammad, _svc_wiki, _svc_mail)
    return {"status": "terminated", "employee_id": req.employee_id}


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------
async def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="FakeCo employee provisioning")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prov = sub.add_parser("provision", help="Provision one or all employees")
    p_prov.add_argument("--employee-id", type=int, help="Provision a specific employee by ID")
    p_prov.add_argument("--all", action="store_true", help="Provision all active employees")

    p_fire = sub.add_parser("fire", help="Fire (terminate) an employee")
    p_fire.add_argument("--employee-id", type=int, required=True)

    sub.add_parser("provision-principal", help="Provision the Principal human account")

    args = parser.parse_args()

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=5)
    mm = MattermostClient(MATTERMOST_URL, MATTERMOST_ADMIN_TOKEN, MATTERMOST_TEAM_ID)
    zammad = ZammadClient(ZAMMAD_URL, ZAMMAD_ADMIN_TOKEN)
    wiki = WikiJSClient(WIKIJS_URL, WIKIJS_ADMIN_TOKEN)
    mail = MailserverClient(MAILSERVER_CONTAINER, MAILSERVER_DOMAIN)

    try:
        async with pool.acquire() as conn:
            await sync_personality_library(conn)
            if args.command == "provision":
                if args.all:
                    employees = await conn.fetch(
                        "SELECT * FROM employees WHERE status IN ('active', 'vacant') ORDER BY id"
                    )
                elif args.employee_id:
                    employees = await conn.fetch(
                        "SELECT * FROM employees WHERE id = $1", args.employee_id
                    )
                else:
                    parser.error("--employee-id or --all required")
                    return

                for emp in employees:
                    await provision_employee(conn, emp, mm, zammad, wiki, mail)

            elif args.command == "fire":
                emp = await conn.fetchrow(
                    "SELECT * FROM employees WHERE id = $1", args.employee_id
                )
                if not emp:
                    log.error("Employee %d not found", args.employee_id)
                    sys.exit(1)
                await fire_employee(conn, emp, mm, zammad, wiki, mail)

            elif args.command == "provision-principal":
                # Principal gets a human Mattermost account, not a bot
                principal_mm_username = PRINCIPAL_EMAIL.split("@")[0].replace(".", "_").lower()
                existing = await mm.get_bot_by_username(principal_mm_username)
                if existing:
                    log.info("Mattermost: Principal account already exists (id=%s)", existing["id"])
                else:
                    principal_password = os.environ.get("PRINCIPAL_MATTERMOST_PASSWORD", "")
                    if not principal_password:
                        log.error("PRINCIPAL_MATTERMOST_PASSWORD env var required for provision-principal")
                        sys.exit(1)
                    user = await mm.create_human_account(
                        email=PRINCIPAL_EMAIL,
                        username=principal_mm_username,
                        name=PRINCIPAL_NAME,
                        password=principal_password,
                    )
                    log.info("Mattermost: Principal account created (id=%s)", user["id"])

                # Principal gets Zammad + Wiki.js accounts too
                # (Zammad: for approving expense requests; Wiki.js: for editing pages)
                zammad_principal = await zammad.get_user_by_email(PRINCIPAL_EMAIL)
                if not zammad_principal:
                    parts = PRINCIPAL_NAME.split()
                    await zammad.create_user(
                        PRINCIPAL_EMAIL,
                        parts[0],
                        " ".join(parts[1:]) if len(parts) > 1 else "",
                        role_names=["Admin", "Agent"],
                    )
                    log.info("Zammad: Principal account created")
                else:
                    log.info("Zammad: Principal account already exists")

                wiki_principal = await wiki.get_user_by_email(PRINCIPAL_EMAIL)
                if not wiki_principal:
                    await wiki.create_user(PRINCIPAL_EMAIL, PRINCIPAL_NAME)
                    log.info("Wiki.js: Principal account created")
                else:
                    log.info("Wiki.js: Principal account already exists")

                # Mail: create principal mailbox
                await mail.create_account(PRINCIPAL_EMAIL)
                log.info("provision-principal: complete")

    finally:
        await mm.close()
        await zammad.close()
        await wiki.close()
        await pool.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        asyncio.run(main())
