"""
snapshot-manager/main.py — FakeCo "Real Appliances"
Phase 29: Snapshot save/restore sidecar.

Per PHASE29_PLAN.md (signed off 2026-07-31), this is a dedicated sidecar,
multi-homed onto net_data + net_dmz + net_mail (+ net_mgmt for the
docker-socket-proxy start/stop calls used during restore), that talks
DIRECTLY to each appliance's own database over the network — never
`docker exec` (docker-socket-proxy's EXEC=0 is a hard, deliberate Phase 1
constraint, not something this service works around).

Captures, into one timestamped directory per snapshot under the
`snapshot_storage` volume:
  - narrative.sql       — pg_dump -Fc of the shared `fakeco` DB only (NOT the
                          whole Postgres instance — LiteLLM's own spend-history
                          DB lives on the same instance under a different
                          database name and must NOT be swept in).
  - mattermost.sql, zammad.sql, wikijs.sql, nextcloud.sql — pg_dump -Fc of each
                          appliance's own dedicated Postgres instance.
  - nextcloud_files.tar — Nextcloud's uploaded-file data volume.
  - wordpress.sql, akaunting.sql — mysqldump of each MariaDB instance.
  - mailserver_maildir.tar — docker-mailserver's Maildir, read from a
                          read-only shared volume mount (no exec needed).
  - manifest.json       — sim-clock state at capture time, wall-clock
                          timestamp, and a sha256 checksum per artifact file.

Restore does the reverse: stop the affected app-tier containers via the
already-allowed docker-socket-proxy CONTAINERS+POST (start/stop/restart)
capability, restore each DB / untar each archive, restart. Zammad's
Elasticsearch index is derived state and is flagged (not rebuilt here — no
exec-free Zammad API exists pre-Phase-30/31 for a full reindex trigger; noted
as a known follow-up, logged to snapshot_purge_log so it isn't silently lost).

Both /snapshot/save and /snapshot/restore:
  - set `system_maintenance_mode` before starting and clear it after, so
    orchestrator's tick loop no-ops for the duration (see orchestrator/main.py).
  - best-effort pause sim-clock (its speed range is 0.1x-10.0x, no true "0"
    stop exists — 0.1x is the closest available and is NOT relied upon for
    correctness; system_maintenance_mode is the actual, enforced gate).
  - write a row to `snapshot_purge_log` (started/succeeded/failed).

Restore additionally requires a typed confirmation phrase in the request body
(second layer, in addition to the pre-restore snapshot NOT being required here
since restore itself IS the recovery step — but /snapshot/save is itself
always called first automatically by purge-manager before any purge).
"""
import asyncio
import hashlib
import json
import logging
import os
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

import asyncpg
import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","service":"snapshot-manager","msg":"%(message)s"}'
)
log = logging.getLogger("snapshot_manager")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql://{os.environ.get('POSTGRES_USER', 'fakeco')}:"
    f"{os.environ.get('POSTGRES_PASSWORD', 'fakeco')}@"
    f"postgres/{os.environ.get('POSTGRES_DB', 'fakeco')}",
)
SIM_CLOCK_URL = os.environ.get("SIM_CLOCK_URL", "http://sim-clock:8000")
SOCKET_PROXY_URL = os.environ.get("SOCKET_PROXY_URL", "http://docker-socket-proxy:2375")

SNAPSHOT_ROOT = Path(os.environ.get("SNAPSHOT_ROOT", "/snapshots"))
MAILDIR_PATH = Path(os.environ.get("MAILDIR_PATH", "/maildir"))
NEXTCLOUD_DATA_PATH = Path(os.environ.get("NEXTCLOUD_DATA_PATH", "/nextcloud_data"))

RESTORE_CONFIRM_PHRASE = "RESTORE SNAPSHOT"

# Each Postgres-backed appliance: (artifact name, host, db, user, password env var)
POSTGRES_TARGETS = [
    ("narrative", "postgres", os.environ.get("POSTGRES_DB", "fakeco"),
     os.environ.get("POSTGRES_USER", "fakeco"), os.environ.get("POSTGRES_PASSWORD", "")),
    ("mattermost", "mattermost-db", "mattermost", "mattermost",
     os.environ.get("MATTERMOST_DB_PASSWORD", "")),
    ("zammad", "zammad-db", "zammad", "zammad",
     os.environ.get("ZAMMAD_DB_PASSWORD", "")),
    ("wikijs", "wikijs-db", "wikijs", "wikijs",
     os.environ.get("WIKIJS_DB_PASSWORD", "")),
    ("nextcloud", "nextcloud-db", "nextcloud", "nextcloud",
     os.environ.get("NEXTCLOUD_DB_PASSWORD", "")),
]

# Each MariaDB-backed appliance: (artifact name, host, db, user, password env var)
MYSQL_TARGETS = [
    ("wordpress", "wordpress-db", "wordpress", "wordpress",
     os.environ.get("WORDPRESS_DB_PASSWORD", "")),
    ("akaunting", "akaunting-db", "akaunting", "akaunting",
     os.environ.get("AKAUNTING_DB_PASSWORD", "")),
]

# App-tier containers that must be stopped before their DB is restored, and
# restarted after. Grouped per appliance in dependency order (per PHASE29_PLAN
# §3 — Zammad has 4 app-tier processes, everything else has 1).
APP_CONTAINERS_BY_TARGET = {
    "mattermost": ["fakeco-mattermost"],
    "zammad": ["fakeco-zammad-nginx", "fakeco-zammad-websocket", "fakeco-zammad-scheduler",
               "fakeco-zammad-railsserver"],
    "wikijs": ["fakeco-wikijs"],
    "nextcloud": ["fakeco-nextcloud"],
    "wordpress": ["fakeco-wordpress"],
    "akaunting": ["fakeco-akaunting"],
    "narrative": [],  # no single "app" container fronts the shared narrative DB
}
MAILSERVER_CONTAINER = "fakeco-mailserver"

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
    log.info("snapshot-manager: service ready")
    yield
    await _pool.close()
    await _http.aclose()


app = FastAPI(title="snapshot-manager", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Maintenance-mode + audit-log helpers
# ---------------------------------------------------------------------------
async def set_maintenance_mode(pool: asyncpg.Pool, enabled: bool, reason: str, set_by: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO system_maintenance_mode (id, enabled, reason, set_by, set_at, updated_at)
            VALUES (1, $1, $2, $3, now(), now())
            ON CONFLICT (id) DO UPDATE
                SET enabled = $1, reason = $2, set_by = $3, set_at = now(), updated_at = now()
            """,
            enabled, reason, set_by,
        )


async def pause_sim_clock_best_effort() -> None:
    try:
        await _http.post(f"{SIM_CLOCK_URL}/set_speed", json={"speed_multiplier": 0.1})
    except Exception as exc:
        log.warning("snapshot-manager: best-effort sim-clock pause failed (non-fatal): %s", exc)


async def resume_sim_clock_best_effort(speed: float = 1.0) -> None:
    try:
        await _http.post(f"{SIM_CLOCK_URL}/set_speed", json={"speed_multiplier": speed})
    except Exception as exc:
        log.warning("snapshot-manager: best-effort sim-clock resume failed (non-fatal): %s", exc)


async def log_op(pool: asyncpg.Pool, operation: str, scope: Optional[str], snapshot_name: Optional[str],
                  status: str, detail: dict, log_id: Optional[int] = None) -> int:
    async with pool.acquire() as conn:
        if log_id is None:
            row = await conn.fetchrow(
                """
                INSERT INTO snapshot_purge_log (operation, scope, snapshot_name, status, detail, started_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, now())
                RETURNING id
                """,
                operation, scope, snapshot_name, status, json.dumps(detail),
            )
            return row["id"]
        else:
            await conn.execute(
                """
                UPDATE snapshot_purge_log
                SET status = $1, detail = $2::jsonb, finished_at = now()
                WHERE id = $3
                """,
                status, json.dumps(detail), log_id,
            )
            return log_id


async def docker_container_action(container: str, action: str) -> bool:
    """POST to docker-socket-proxy's Docker-Engine-compatible REST API. No `docker exec` anywhere."""
    try:
        resp = await _http.post(f"{SOCKET_PROXY_URL}/containers/{container}/{action}?t=15")
        if resp.status_code not in (204, 304):
            log.warning("docker %s %s: unexpected status %s: %s", action, container, resp.status_code, resp.text)
            return False
        return True
    except Exception as exc:
        log.error("docker %s %s failed: %s", action, container, exc)
        return False


async def get_sim_state(pool: asyncpg.Pool) -> dict:
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT sim_time, speed_multiplier FROM sim_clock WHERE id = 1")
        if row:
            return {"sim_time": row["sim_time"].isoformat(), "speed_multiplier": float(row["speed_multiplier"])}
    except Exception as exc:
        log.warning("could not read sim_clock state for manifest: %s", exc)
    return {}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_subprocess(cmd: list, env: dict = None) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout, proc.stderr


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
class SaveRequest(BaseModel):
    label: Optional[str] = None


@app.post("/snapshot/save")
async def snapshot_save(req: SaveRequest, pool: PoolDep):
    sim_state = await get_sim_state(pool)
    wall_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sim_tag = sim_state.get("sim_time", "unknown").replace(":", "").replace("-", "")
    snapshot_name = f"{sim_tag}_{wall_ts}"
    if req.label:
        snapshot_name = f"{snapshot_name}_{req.label}"
    snap_dir = SNAPSHOT_ROOT / snapshot_name
    snap_dir.mkdir(parents=True, exist_ok=False)

    log_id = await log_op(pool, "snapshot_save", None, snapshot_name, "started", {})
    await set_maintenance_mode(pool, True, f"snapshot save {snapshot_name}", "snapshot-manager")
    await pause_sim_clock_best_effort()

    results = {}
    overall_ok = True
    try:
        for name, host, db, user, password in POSTGRES_TARGETS:
            target_file = snap_dir / f"{name}.sql"
            env = {**os.environ, "PGPASSWORD": password}
            rc, out, err = run_subprocess(
                ["pg_dump", "-h", host, "-U", user, "-d", db, "-Fc", "-f", str(target_file)],
                env=env,
            )
            ok = rc == 0 and target_file.exists() and target_file.stat().st_size > 0
            results[name] = {"ok": ok, "returncode": rc, "stderr": err[-500:] if err else ""}
            overall_ok = overall_ok and ok

        for name, host, db, user, password in MYSQL_TARGETS:
            target_file = snap_dir / f"{name}.sql"
            cmd = ["mysqldump", "-h", host, "-u", user, f"-p{password}", "--single-transaction", db]
            proc = subprocess.run(cmd, capture_output=True)
            ok = proc.returncode == 0 and len(proc.stdout) > 0
            if ok:
                target_file.write_bytes(proc.stdout)
            results[name] = {"ok": ok, "returncode": proc.returncode,
                              "stderr": proc.stderr.decode(errors="replace")[-500:] if proc.stderr else ""}
            overall_ok = overall_ok and ok

        # Mailserver Maildir — read-only shared volume, no exec, no stop needed for save
        maildir_tar = snap_dir / "mailserver_maildir.tar"
        rc, out, err = run_subprocess(["tar", "-cf", str(maildir_tar), "-C", str(MAILDIR_PATH), "."])
        ok = rc == 0 and maildir_tar.exists()
        results["mailserver_maildir"] = {"ok": ok, "returncode": rc, "stderr": err[-500:] if err else ""}
        overall_ok = overall_ok and ok

        # Nextcloud uploaded-file data volume (separate from its DB dump above)
        nc_tar = snap_dir / "nextcloud_files.tar"
        if NEXTCLOUD_DATA_PATH.exists():
            rc, out, err = run_subprocess(["tar", "-cf", str(nc_tar), "-C", str(NEXTCLOUD_DATA_PATH), "."])
            ok = rc == 0 and nc_tar.exists()
        else:
            ok = False
            err = "NEXTCLOUD_DATA_PATH not mounted"
        results["nextcloud_files"] = {"ok": ok, "returncode": rc if NEXTCLOUD_DATA_PATH.exists() else -1,
                                       "stderr": err[-500:] if err else ""}
        overall_ok = overall_ok and ok

        manifest = {
            "snapshot_name": snapshot_name,
            "wall_clock_captured_at": datetime.now(timezone.utc).isoformat(),
            "sim_state": sim_state,
            "artifacts": {},
        }
        for f in sorted(snap_dir.glob("*")):
            if f.name == "manifest.json":
                continue
            manifest["artifacts"][f.name] = {"size_bytes": f.stat().st_size, "sha256": sha256_of(f)}
        (snap_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

        status = "succeeded" if overall_ok else "failed"
        await log_op(pool, "snapshot_save", None, snapshot_name, status, results, log_id)
        if not overall_ok:
            raise HTTPException(status_code=500, detail={"snapshot_name": snapshot_name, "results": results})
        return {"snapshot_name": snapshot_name, "results": results, "manifest": manifest}
    except HTTPException:
        raise
    except Exception as exc:
        await log_op(pool, "snapshot_save", None, snapshot_name, "failed", {"error": str(exc), **results}, log_id)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        await resume_sim_clock_best_effort()
        await set_maintenance_mode(pool, False, None, "snapshot-manager")


@app.get("/snapshot/list")
async def snapshot_list():
    if not SNAPSHOT_ROOT.exists():
        return {"snapshots": []}
    out = []
    for d in sorted(SNAPSHOT_ROOT.iterdir()):
        manifest_path = d / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            manifest["total_size_bytes"] = sum(
                a.get("size_bytes", 0) for a in manifest.get("artifacts", {}).values()
            )
            out.append(manifest)
    return {"snapshots": out}


@app.delete("/snapshot/{snapshot_name}")
async def snapshot_delete(snapshot_name: str, pool: PoolDep):
    """Phase 36: Data Management tab's per-snapshot Delete button. Only ever
    removes the named snapshot's own directory under SNAPSHOT_ROOT — never
    touches any appliance's live data (this is purely storage cleanup, not a
    purge). Guards against path traversal by requiring the resolved path stay
    a direct child of SNAPSHOT_ROOT."""
    safe_name = os.path.basename(snapshot_name)
    snap_dir = SNAPSHOT_ROOT / safe_name
    if not snap_dir.is_dir() or not (snap_dir / "manifest.json").exists():
        raise HTTPException(status_code=404, detail=f"snapshot {snapshot_name} not found")
    import shutil
    shutil.rmtree(snap_dir)
    await log_op(pool, "snapshot_delete", None, safe_name, "succeeded", {})
    return {"status": "deleted", "snapshot_name": safe_name}


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------
class RestoreRequest(BaseModel):
    snapshot_name: str
    confirm: str


@app.post("/snapshot/restore")
async def snapshot_restore(req: RestoreRequest, pool: PoolDep):
    if req.confirm != RESTORE_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f"confirm must be the exact phrase '{RESTORE_CONFIRM_PHRASE}'",
        )
    snap_dir = SNAPSHOT_ROOT / req.snapshot_name
    manifest_path = snap_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"snapshot {req.snapshot_name} not found (no manifest.json)")
    manifest = json.loads(manifest_path.read_text())

    log_id = await log_op(pool, "snapshot_restore", None, req.snapshot_name, "started", {})
    await set_maintenance_mode(pool, True, f"snapshot restore {req.snapshot_name}", "snapshot-manager")
    await pause_sim_clock_best_effort()

    results = {}
    overall_ok = True
    notes = []
    try:
        # 1. Stop all app-tier containers first (per §3 ordering: app down -> DB restore -> app up)
        for target, containers in APP_CONTAINERS_BY_TARGET.items():
            for c in containers:
                await docker_container_action(c, "stop")
        await docker_container_action(MAILSERVER_CONTAINER, "stop")
        await asyncio.sleep(2)  # let stop settle before writing to the shared Maildir volume

        # 2. Restore each Postgres appliance DB
        for name, host, db, user, password in POSTGRES_TARGETS:
            src = snap_dir / f"{name}.sql"
            if not src.exists():
                results[name] = {"ok": False, "error": "artifact missing from snapshot"}
                overall_ok = False
                continue
            env = {**os.environ, "PGPASSWORD": password}
            rc, out, err = run_subprocess(
                [
                    "pg_restore", "-h", host, "-U", user, "-d", db,
                    "--clean", "--if-exists", "--single-transaction", str(src),
                ],
                env=env,
            )
            # Exit code is the authoritative success/failure signal, not a substring grep on
            # stderr (that heuristic used to misfire: pg_restore/psql routinely emit lines
            # containing "ERROR"/"error" as part of harmless NOTICEs or its own informational
            # summary line, e.g. "pg_restore: warning: errors ignored on restore: N" — a plain
            # `"ERROR" in output` check can misclassify those as fatal, or miss a real failure
            # whose message happens not to contain that literal word).
            # --single-transaction makes the exit code fully trustworthy here: pg_restore wraps
            # the whole restore in one transaction, so ANY genuine error aborts the transaction
            # and pg_restore exits non-zero; harmless --if-exists "does not exist, skipping"
            # NOTICEs never affect the exit code either way.
            ok = rc == 0
            results[name] = {"ok": ok, "returncode": rc, "stderr": err[-800:] if err else ""}
            overall_ok = overall_ok and ok

        # 3. Restore each MariaDB appliance DB
        for name, host, db, user, password in MYSQL_TARGETS:
            src = snap_dir / f"{name}.sql"
            if not src.exists():
                results[name] = {"ok": False, "error": "artifact missing from snapshot"}
                overall_ok = False
                continue
            cmd = ["mysql", "-h", host, "-u", user, f"-p{password}", db]
            with open(src, "rb") as f:
                proc = subprocess.run(cmd, stdin=f, capture_output=True)
            ok = proc.returncode == 0
            results[name] = {"ok": ok, "returncode": proc.returncode,
                              "stderr": proc.stderr.decode(errors="replace")[-800:] if proc.stderr else ""}
            overall_ok = overall_ok and ok

        # 4. Untar mailserver Maildir ONLY while mailserver is stopped (write window)
        maildir_tar = snap_dir / "mailserver_maildir.tar"
        if maildir_tar.exists():
            rc, out, err = run_subprocess(["tar", "-xf", str(maildir_tar), "-C", str(MAILDIR_PATH)])
            ok = rc == 0
            results["mailserver_maildir"] = {"ok": ok, "returncode": rc, "stderr": err[-500:] if err else ""}
            overall_ok = overall_ok and ok

        # 5. Untar Nextcloud files (app already stopped above)
        nc_tar = snap_dir / "nextcloud_files.tar"
        if nc_tar.exists() and NEXTCLOUD_DATA_PATH.exists():
            rc, out, err = run_subprocess(["tar", "-xf", str(nc_tar), "-C", str(NEXTCLOUD_DATA_PATH)])
            ok = rc == 0
            results["nextcloud_files"] = {"ok": ok, "returncode": rc, "stderr": err[-500:] if err else ""}
            overall_ok = overall_ok and ok

        # 6. Restart everything
        await docker_container_action(MAILSERVER_CONTAINER, "start")
        for target, containers in APP_CONTAINERS_BY_TARGET.items():
            # dependency order within zammad matters: railsserver -> scheduler -> websocket -> nginx
            for c in reversed(containers):
                await docker_container_action(c, "start")

        notes.append(
            "Zammad Elasticsearch index was NOT rebuilt automatically after this restore "
            "(no exec-free reindex trigger exists yet) — Zammad search results may be stale "
            "until a manual reindex is run."
        )

        status = "succeeded" if overall_ok else "failed"
        await log_op(pool, "snapshot_restore", None, req.snapshot_name, status,
                      {"results": results, "notes": notes}, log_id)
        if not overall_ok:
            raise HTTPException(status_code=500, detail={"results": results, "notes": notes})
        return {"snapshot_name": req.snapshot_name, "results": results, "notes": notes}
    except HTTPException:
        raise
    except Exception as exc:
        await log_op(pool, "snapshot_restore", None, req.snapshot_name, "failed",
                      {"error": str(exc), **results}, log_id)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        await resume_sim_clock_best_effort()
        await set_maintenance_mode(pool, False, None, "snapshot-manager")


@app.get("/health")
async def health():
    return {"status": "ok"}
