"""
narrative-db/migrate.py — FakeCo migration runner
Phase 13: Applies SQL migrations in order, idempotently.

Tracks applied migrations in a `schema_migrations` table (created on first run).
Safe to re-run: skips already-applied migrations.

Usage:
    python migrate.py [--dry-run]

Environment:
    DATABASE_URL or POSTGRES_* vars (same as sim-clock)
"""
import asyncio
import hashlib
import logging
import os
import sys
from pathlib import Path

import asyncpg

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql://{os.environ.get('POSTGRES_USER','fakeco')}:"
    f"{os.environ.get('POSTGRES_PASSWORD','fakeco')}@"
    f"{os.environ.get('POSTGRES_HOST','postgres')}:"
    f"{os.environ.get('POSTGRES_PORT','5432')}/"
    f"{os.environ.get('POSTGRES_DB','fakeco')}"
)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("migrate")


async def ensure_migrations_table(conn: asyncpg.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename    TEXT    PRIMARY KEY,
            checksum    TEXT    NOT NULL,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


async def get_applied(conn: asyncpg.Connection) -> dict[str, str]:
    rows = await conn.fetch("SELECT filename, checksum FROM schema_migrations")
    return {row["filename"]: row["checksum"] for row in rows}


def file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def run_migrations(dry_run: bool = False) -> None:
    log.info("Connecting to Postgres...")
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)

    try:
        async with pool.acquire() as conn:
            await ensure_migrations_table(conn)
            applied = await get_applied(conn)

        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        if not migration_files:
            log.warning("No migration files found in %s", MIGRATIONS_DIR)
            return

        for mf in migration_files:
            checksum = file_checksum(mf)
            if mf.name in applied:
                if applied[mf.name] != checksum:
                    log.error(
                        "CHECKSUM MISMATCH for already-applied migration %s! "
                        "Do not modify applied migrations. Aborting.",
                        mf.name,
                    )
                    sys.exit(1)
                log.info("  SKIP  %s (already applied)", mf.name)
                continue

            sql = mf.read_text(encoding="utf-8")
            log.info("  APPLY %s%s", mf.name, " [DRY RUN]" if dry_run else "")

            if not dry_run:
                async with pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.execute(sql)
                        await conn.execute(
                            "INSERT INTO schema_migrations (filename, checksum) VALUES ($1, $2)",
                            mf.name, checksum
                        )
                log.info("  DONE  %s", mf.name)

        log.info("Migration run complete.")

    finally:
        await pool.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(run_migrations(dry_run=dry_run))
