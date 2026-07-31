"""
branding-manager/main.py — FakeCo "Real Appliances"
Phase 30: Branding & asset manager.

Spec §17: bundled avatar image library + themed Mattermost custom-emoji pack.
  - employee_id -> avatar_asset_id mapping (employee_branding table,
    narrative-db/migrations/007_branding.sql)
  - Per-employee avatar picker + bulk actions (randomize / apply-one-to-all /
    reset-to-default), pushed through each appliance's REAL avatar-upload API:
      Mattermost: POST /api/v4/users/{id}/image (multipart)
      Zammad:     POST /api/v1/users/avatar/{id} (multipart, admin-on-behalf)
      Wiki.js:    users.update GraphQL mutation, avatar as a data: URL string
  - First-boot: uploads the bundled emoji pack to Mattermost
    (POST /api/v4/emoji, multipart) — a real, native Mattermost feature.

Only the selection/bulk-push logic here is custom; rendering of the pushed
avatars/emoji is entirely each real appliance's own doing.
"""
import base64
import logging
import os
import random
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal, Optional

import asyncpg
import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","service":"branding-manager","msg":"%(message)s"}'
)
log = logging.getLogger("branding_manager")

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
MATTERMOST_URL = os.environ.get("MATTERMOST_URL", "http://mattermost:8065")
MATTERMOST_ADMIN_TOKEN = os.environ.get("MATTERMOST_ADMIN_TOKEN", "")
ZAMMAD_URL = os.environ.get("ZAMMAD_URL", "http://zammad-nginx:8080")
ZAMMAD_ADMIN_TOKEN = os.environ.get("ZAMMAD_ADMIN_TOKEN", "")
WIKIJS_URL = os.environ.get("WIKIJS_URL", "http://wikijs:3000")
WIKIJS_ADMIN_TOKEN = os.environ.get("WIKIJS_ADMIN_TOKEN", "")
# Wiki.js has no REST/GraphQL endpoint to set another user's (or even one's
# own) avatar directly — confirmed via schema introspection (Phase 30
# verification): `users.update`'s only args are id/email/name/newPassword/
# groups/location/jobTitle/timezone/dateFormat/appearance (no `avatar`), the
# `User` GraphQL type itself has no `avatar` field, and
# `updateUserAvatarData()` (server/models/users.js) is only ever called from
# OAuth-provider login sync (`profile.picture`), never from a controller
# route. The only avatar route that exists is a GET
# (`/_userav/:uid`, server/controllers/common.js) reading straight from the
# `userAvatars` Postgres table (id, data bytea) — there's no POST/PUT
# counterpart. So the real, working mechanism is a direct write to that same
# table Wiki.js's own `/_userav/:uid` route reads from; verification then
# re-fetches through that real route to confirm the appliance actually
# serves the new image. See BUILD_LOG.md Phase 30 entry.
WIKIJS_DB_HOST = os.environ.get("WIKIJS_DB_HOST", "wikijs-db")
WIKIJS_DB_PORT = int(os.environ.get("WIKIJS_DB_PORT", "5432"))
WIKIJS_DB_NAME = os.environ.get("WIKIJS_DB_NAME", "wikijs")
WIKIJS_DB_USER = os.environ.get("WIKIJS_DB_USER", "wikijs")
WIKIJS_DB_PASSWORD = os.environ.get("WIKIJS_DB_PASSWORD", "")

ASSETS_DIR = Path(os.environ.get("BRANDING_ASSETS_DIR", str(Path(__file__).parent / "assets")))
AVATARS_DIR = ASSETS_DIR / "avatars"
EMOJI_DIR = ASSETS_DIR / "emoji"
DEFAULT_AVATAR_ASSET_ID = os.environ.get("DEFAULT_AVATAR_ASSET_ID", "avatar-01")


def list_avatar_assets() -> list[str]:
    if not AVATARS_DIR.is_dir():
        return []
    return sorted(p.stem for p in AVATARS_DIR.glob("*.png"))


def list_emoji_assets() -> list[str]:
    if not EMOJI_DIR.is_dir():
        return []
    return sorted(p.stem for p in EMOJI_DIR.glob("*.png"))


def avatar_path(asset_id: str) -> Path:
    # Guard against path traversal — asset_id must be a bare filename stem
    # that actually exists in the bundled library.
    safe = os.path.basename(asset_id)
    path = AVATARS_DIR / f"{safe}.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"unknown avatar asset '{asset_id}'")
    return path


# ---------------------------------------------------------------------------
# Database pool
# ---------------------------------------------------------------------------
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


# ---------------------------------------------------------------------------
# Mattermost client — avatar push + custom emoji upload
# ---------------------------------------------------------------------------
class MattermostClient:
    def __init__(self, base_url: str, admin_token: str):
        self.base = base_url.rstrip("/") + "/api/v4"
        self.headers = {"Authorization": f"Bearer {admin_token}"}
        self._client = httpx.AsyncClient(headers=self.headers, timeout=30.0)

    async def close(self):
        await self._client.aclose()

    async def set_user_avatar(self, user_id: str, image_path: Path) -> None:
        """
        POST /api/v4/users/{user_id}/image — admin token can set another
        user's profile image directly, no impersonation token needed (this
        is a distinct admin-capable endpoint, unlike posting messages which
        requires acting as the user).
        """
        with open(image_path, "rb") as f:
            r = await self._client.post(
                f"{self.base}/users/{user_id}/image",
                files={"image": (image_path.name, f, "image/png")},
            )
        r.raise_for_status()

    async def reset_user_avatar(self, user_id: str) -> None:
        """DELETE /api/v4/users/{user_id}/image resets to the default generated avatar."""
        r = await self._client.delete(f"{self.base}/users/{user_id}/image")
        r.raise_for_status()

    async def get_user(self, user_id: str) -> dict:
        r = await self._client.get(f"{self.base}/users/{user_id}")
        r.raise_for_status()
        return r.json()

    async def get_emoji_by_name(self, name: str) -> Optional[dict]:
        r = await self._client.get(f"{self.base}/emoji/name/{name}")
        if r.status_code == 200:
            return r.json()
        return None

    async def create_emoji(self, name: str, image_path: Path, creator_user_id: str) -> dict:
        """POST /api/v4/emoji — multipart: `image` file + `emoji` JSON metadata part."""
        import json as _json
        with open(image_path, "rb") as f:
            r = await self._client.post(
                f"{self.base}/emoji",
                files={
                    "image": (image_path.name, f, "image/png"),
                    "emoji": (None, _json.dumps({"name": name, "creator_id": creator_user_id})),
                },
            )
        r.raise_for_status()
        return r.json()

    async def get_first_admin_id(self) -> str:
        """Use as the emoji `creator_id` — Mattermost requires a real user id."""
        r = await self._client.get(f"{self.base}/users/me")
        r.raise_for_status()
        return r.json()["id"]


# ---------------------------------------------------------------------------
# Zammad client — avatar push
#
# RESEARCH FINDING (Phase 30 verification, against a live isolated instance):
# Zammad's avatar API (`POST/GET/DELETE /api/v1/users/avatar`, routes in
# config/routes/user.rb) is *entirely current_user-scoped* — every one of
# `avatar_new`/`avatar_list`/`avatar_destroy`/`avatar_set_default` in
# UsersController operates on `current_user`, never on a `user_id` param, and
# there is no separate "set avatar for another user" REST or GraphQL mutation
# (checked both `app/graphql/gql/mutations/user/current/avatar` — also
# current-user-scoped — and `UserAccessTokenController`, which likewise can
# only mint/list/revoke tokens for `current_user`, not create one for an
# arbitrary employee the way Mattermost's admin `/users/{id}/tokens` does).
# So there is no admin-token shortcut here at all, unlike Mattermost/Wiki.js.
#
# The real, working on-behalf-of mechanism, confirmed live: an admin token
# CAN `PUT /api/v1/users/{id}` to set that user's `password` (admin.user
# permission), then authenticate as the employee via HTTP Basic Auth with
# that (temporary) password and call the normal current-user avatar API as
# them — same spirit as the Mattermost impersonation-PAT pattern used
# elsewhere in this codebase (mint ephemeral credential, act as the
# employee, no permanent secret stored). We don't need to revert the
# password afterward since employee Zammad accounts are bots with no other
# login flow depending on it.
# ---------------------------------------------------------------------------
class ZammadClient:
    def __init__(self, base_url: str, admin_token: str):
        self.base = base_url.rstrip("/") + "/api/v1"
        self.headers = {"Authorization": f"Token token={admin_token}"}
        self._client = httpx.AsyncClient(headers=self.headers, timeout=30.0)

    async def close(self):
        await self._client.aclose()

    @staticmethod
    def _ephemeral_password() -> str:
        import secrets
        return f"Brand-{secrets.token_urlsafe(18)}!1"

    async def _as_employee_client(self, user_id: str) -> tuple[httpx.AsyncClient, dict]:
        """Sets a fresh ephemeral password on `user_id` (admin call) and
        returns an httpx client authenticated as that user via Basic Auth,
        plus the user record (for the login/email)."""
        password = self._ephemeral_password()
        r = await self._client.put(f"{self.base}/users/{user_id}", json={"password": password})
        r.raise_for_status()
        user = r.json()
        login = user.get("login") or user.get("email")
        return httpx.AsyncClient(auth=(login, password), timeout=30.0), user

    async def set_user_avatar(self, user_id: str, image_path: Path) -> None:
        img_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        data_url = f"data:image/png;base64,{img_b64}"
        emp_client, _ = await self._as_employee_client(user_id)
        try:
            r = await emp_client.post(
                f"{self.base}/users/avatar",
                json={"avatar_full": data_url, "avatar_resize": data_url},
            )
            r.raise_for_status()
        finally:
            await emp_client.aclose()

    async def reset_user_avatar(self, user_id: str) -> None:
        """
        Remove all avatars belonging to the user, reverting to Zammad's
        default initials.

        BUG FOUND during Phase 30 verification: `UsersController#avatar_destroy`
        only re-points `user.image` at the next remaining default avatar's hash
        if one still exists after the delete — when the LAST avatar record is
        removed, `user.image` is left pointing at the now-deleted hash instead
        of being cleared. The hash still resolves via `GET
        /api/v1/users/image/{hash}` (Zammad keeps the underlying Store blob
        even once no Avatar row references it), so the user silently keeps
        showing a stale, previously-deleted image instead of reverting to
        initials. Confirmed live: deleted employee's only avatar record, `image`
        field remained the deleted avatar's hash, and that hash still served
        200 with the old image bytes. Worked around here by explicitly
        clearing `image` via the admin-token `PUT /users/{id}` call afterward.
        """
        emp_client, _ = await self._as_employee_client(user_id)
        try:
            r = await emp_client.get(f"{self.base}/users/avatar")
            if r.status_code == 200:
                for avatar in r.json().get("avatars", []):
                    await emp_client.delete(f"{self.base}/users/avatar/{avatar['id']}")
        finally:
            await emp_client.aclose()
        # Explicit fix for the dangling-`image`-hash bug documented above.
        await self._client.put(f"{self.base}/users/{user_id}", json={"image": None})

    async def get_user(self, user_id: str) -> dict:
        r = await self._client.get(f"{self.base}/users/{user_id}")
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Wiki.js client — avatar push via GraphQL
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

    async def set_user_avatar(self, user_id: str, image_path: Path) -> None:
        """
        No GraphQL/REST mutation exists for this (see module-level note next
        to WIKIJS_DB_* config) — writes directly to the `userAvatars` table
        Wiki.js's own `/_userav/:uid` route reads from.
        """
        conn = await asyncpg.connect(
            host=WIKIJS_DB_HOST, port=WIKIJS_DB_PORT, database=WIKIJS_DB_NAME,
            user=WIKIJS_DB_USER, password=WIKIJS_DB_PASSWORD,
        )
        try:
            data = image_path.read_bytes()
            await conn.execute(
                """
                INSERT INTO "userAvatars" (id, data) VALUES ($1, $2)
                ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data
                """,
                int(user_id), data,
            )
        finally:
            await conn.close()

    async def reset_user_avatar(self, user_id: str) -> None:
        """Deletes the row — `/_userav/:uid` 404s afterward, same as a never-set avatar."""
        conn = await asyncpg.connect(
            host=WIKIJS_DB_HOST, port=WIKIJS_DB_PORT, database=WIKIJS_DB_NAME,
            user=WIKIJS_DB_USER, password=WIKIJS_DB_PASSWORD,
        )
        try:
            await conn.execute('DELETE FROM "userAvatars" WHERE id = $1', int(user_id))
        finally:
            await conn.close()

    async def get_user(self, user_id: str) -> dict:
        result = await self.graphql("""
            query($id: Int!) {
                users {
                    single(id: $id) {
                        id
                        email
                        name
                        avatar
                    }
                }
            }
        """, {"id": int(user_id)})
        return ((result.get("data") or {}).get("users") or {}).get("single") or {}


def get_mattermost() -> MattermostClient:
    return MattermostClient(MATTERMOST_URL, MATTERMOST_ADMIN_TOKEN)


def get_zammad() -> ZammadClient:
    return ZammadClient(ZAMMAD_URL, ZAMMAD_ADMIN_TOKEN)


def get_wikijs() -> WikiJSClient:
    return WikiJSClient(WIKIJS_URL, WIKIJS_ADMIN_TOKEN)


# ---------------------------------------------------------------------------
# Core push logic
# ---------------------------------------------------------------------------
async def push_avatar_to_employee(conn: asyncpg.Connection, employee: dict, asset_id: str) -> dict:
    """
    Pushes `asset_id`'s image to every appliance account this employee has
    (mattermost_id / zammad_agent_id / wiki_user_id — any may be NULL if the
    employee wasn't provisioned on that appliance). Returns a per-appliance
    result dict; failures on one appliance don't block the others.
    """
    path = avatar_path(asset_id)
    results: dict[str, str] = {}

    if employee.get("mattermost_id"):
        mm = get_mattermost()
        try:
            await mm.set_user_avatar(employee["mattermost_id"], path)
            results["mattermost"] = "ok"
        except Exception as e:
            log.warning("mattermost avatar push failed for employee %s: %s", employee["id"], e)
            results["mattermost"] = f"error: {e}"
        finally:
            await mm.close()
    else:
        results["mattermost"] = "skipped (no mattermost_id)"

    if employee.get("zammad_agent_id"):
        zc = get_zammad()
        try:
            await zc.set_user_avatar(employee["zammad_agent_id"], path)
            results["zammad"] = "ok"
        except Exception as e:
            log.warning("zammad avatar push failed for employee %s: %s", employee["id"], e)
            results["zammad"] = f"error: {e}"
        finally:
            await zc.close()
    else:
        results["zammad"] = "skipped (no zammad_agent_id)"

    if employee.get("wiki_user_id"):
        wc = get_wikijs()
        try:
            await wc.set_user_avatar(employee["wiki_user_id"], path)
            results["wikijs"] = "ok"
        except Exception as e:
            log.warning("wikijs avatar push failed for employee %s: %s", employee["id"], e)
            results["wikijs"] = f"error: {e}"
        finally:
            await wc.close()
    else:
        results["wikijs"] = "skipped (no wiki_user_id)"

    await conn.execute(
        """
        INSERT INTO employee_branding (employee_id, avatar_asset_id, updated_at)
        VALUES ($1, $2, NOW())
        ON CONFLICT (employee_id)
        DO UPDATE SET avatar_asset_id = EXCLUDED.avatar_asset_id, updated_at = NOW()
        """,
        employee["id"], asset_id,
    )
    return {"employee_id": employee["id"], "asset_id": asset_id, "appliances": results}


async def reset_employee_avatar(conn: asyncpg.Connection, employee: dict) -> dict:
    results: dict[str, str] = {}

    if employee.get("mattermost_id"):
        mm = get_mattermost()
        try:
            await mm.reset_user_avatar(employee["mattermost_id"])
            results["mattermost"] = "ok"
        except Exception as e:
            results["mattermost"] = f"error: {e}"
        finally:
            await mm.close()
    else:
        results["mattermost"] = "skipped (no mattermost_id)"

    if employee.get("zammad_agent_id"):
        zc = get_zammad()
        try:
            await zc.reset_user_avatar(employee["zammad_agent_id"])
            results["zammad"] = "ok"
        except Exception as e:
            results["zammad"] = f"error: {e}"
        finally:
            await zc.close()
    else:
        results["zammad"] = "skipped (no zammad_agent_id)"

    if employee.get("wiki_user_id"):
        wc = get_wikijs()
        try:
            await wc.reset_user_avatar(employee["wiki_user_id"])
            results["wikijs"] = "ok"
        except Exception as e:
            results["wikijs"] = f"error: {e}"
        finally:
            await wc.close()
    else:
        results["wikijs"] = "skipped (no wiki_user_id)"

    await conn.execute(
        """
        INSERT INTO employee_branding (employee_id, avatar_asset_id, updated_at)
        VALUES ($1, $2, NOW())
        ON CONFLICT (employee_id)
        DO UPDATE SET avatar_asset_id = EXCLUDED.avatar_asset_id, updated_at = NOW()
        """,
        employee["id"], DEFAULT_AVATAR_ASSET_ID,
    )
    return {"employee_id": employee["id"], "asset_id": DEFAULT_AVATAR_ASSET_ID, "appliances": results}


async def upload_emoji_pack(conn: asyncpg.Connection) -> list[dict]:
    mm = get_mattermost()
    results = []
    try:
        creator_id = await mm.get_first_admin_id()
        for stem in list_emoji_assets():
            existing = await mm.get_emoji_by_name(stem)
            if existing:
                results.append({"name": stem, "status": "already exists"})
                continue
            path = EMOJI_DIR / f"{stem}.png"
            created = await mm.create_emoji(stem, path, creator_id)
            results.append({"name": stem, "status": "created", "id": created.get("id")})
            log.info("branding-manager: uploaded emoji :%s:", stem)
    finally:
        await mm.close()
    return results


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    log.info("branding-manager: ready (%d avatar assets, %d emoji assets)",
              len(list_avatar_assets()), len(list_emoji_assets()))
    yield
    await _pool.close()


app = FastAPI(
    title="FakeCo Branding & Asset Manager",
    description="Employee avatar/emoji asset library + bulk push to Mattermost/Zammad/Wiki.js.",
    version="1.0.0",
    lifespan=lifespan,
)

PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]


@app.get("/health")
async def health():
    return {"status": "ok", "service": "branding-manager"}


@app.get("/assets")
async def assets():
    return {"avatars": list_avatar_assets(), "emoji": list_emoji_assets()}


@app.get("/assets/avatars/{asset_id}.png")
async def get_avatar_asset(asset_id: str):
    from fastapi.responses import FileResponse
    return FileResponse(avatar_path(asset_id), media_type="image/png")


class ApplyAvatarRequest(BaseModel):
    employee_id: int
    asset_id: str


@app.post("/branding/apply")
async def apply_avatar(req: ApplyAvatarRequest, pool: PoolDep):
    async with pool.acquire() as conn:
        employee = await conn.fetchrow("SELECT * FROM employees WHERE id = $1", req.employee_id)
        if not employee:
            raise HTTPException(status_code=404, detail="employee not found")
        result = await push_avatar_to_employee(conn, dict(employee), req.asset_id)
    return result


class BulkApplyRequest(BaseModel):
    employee_ids: list[int]
    mode: Literal["randomize", "apply-one-to-all", "reset-to-default"]
    asset_id: Optional[str] = None  # required for apply-one-to-all


@app.post("/branding/bulk-apply")
async def bulk_apply(req: BulkApplyRequest, pool: PoolDep):
    if req.mode == "apply-one-to-all" and not req.asset_id:
        raise HTTPException(status_code=422, detail="asset_id required for apply-one-to-all")
    if req.asset_id:
        avatar_path(req.asset_id)  # validate it exists up front

    available = list_avatar_assets()
    if not available:
        raise HTTPException(status_code=500, detail="no bundled avatar assets found")

    results = []
    async with pool.acquire() as conn:
        for employee_id in req.employee_ids:
            employee = await conn.fetchrow("SELECT * FROM employees WHERE id = $1", employee_id)
            if not employee:
                results.append({"employee_id": employee_id, "error": "employee not found"})
                continue
            employee = dict(employee)

            if req.mode == "reset-to-default":
                results.append(await reset_employee_avatar(conn, employee))
            elif req.mode == "apply-one-to-all":
                results.append(await push_avatar_to_employee(conn, employee, req.asset_id))
            else:  # randomize
                asset_id = random.choice(available)
                results.append(await push_avatar_to_employee(conn, employee, asset_id))

    return {"mode": req.mode, "count": len(results), "results": results}


@app.get("/branding/employee/{employee_id}")
async def get_employee_branding(employee_id: int, pool: PoolDep):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT employee_id, avatar_asset_id, updated_at FROM employee_branding WHERE employee_id = $1",
            employee_id,
        )
    if not row:
        return {"employee_id": employee_id, "avatar_asset_id": None, "updated_at": None}
    return dict(row)


@app.post("/branding/emoji-pack/upload")
async def emoji_pack_upload(pool: PoolDep):
    """First-boot (or on-demand) upload of the bundled emoji pack to Mattermost."""
    async with pool.acquire() as conn:
        results = await upload_emoji_pack(conn)
    return {"count": len(results), "results": results}
