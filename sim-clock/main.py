"""
sim_clock — FakeCo "Real Appliances"
Phase 12: Simulation clock service.

Spec §19.1: sim_clock table with sim_time, last_wall_checkpoint, speed_multiplier.
Ticker: sim_time += wall_elapsed_since_last_tick * speed_multiplier
set_speed API: changes speed_multiplier; next tick reflects it immediately.
Speed range: 0.1x (Caveman) to 10.0x (Fast-forward), default 1.0x.

Every time-aware decision in the system reads sim_time from Postgres — never wall-clock.
"""
import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Annotated

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

TICK_INTERVAL_SECONDS = float(os.environ.get("TICK_INTERVAL_SECONDS", "1.0"))
MIN_SPEED = 0.1
MAX_SPEED = 10.0
DEFAULT_SPEED = float(os.environ.get("SPEED_MULTIPLIER", "1.0"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","service":"sim-clock","msg":"%(message)s"}'
)
log = logging.getLogger("sim_clock")

# ---------------------------------------------------------------------------
# Database pool (module-level, shared across ticker and API)
# ---------------------------------------------------------------------------
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


async def init_schema(pool: asyncpg.Pool) -> None:
    """Create sim_clock table if it doesn't exist, seed if empty."""
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sim_clock (
                id          INTEGER PRIMARY KEY DEFAULT 1,
                sim_time    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_wall_checkpoint DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
                speed_multiplier     DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                CHECK (id = 1)  -- singleton row
            )
        """)
        # Seed initial row if not present
        existing = await conn.fetchrow("SELECT id FROM sim_clock WHERE id = 1")
        if not existing:
            await conn.execute("""
                INSERT INTO sim_clock (id, sim_time, last_wall_checkpoint, speed_multiplier)
                VALUES (1, NOW(), EXTRACT(EPOCH FROM NOW()), $1)
                ON CONFLICT DO NOTHING
            """, DEFAULT_SPEED)
            log.info("sim_clock: seeded initial row with speed=%.1f", DEFAULT_SPEED)
        else:
            log.info("sim_clock: existing row found, using current state")


async def tick(pool: asyncpg.Pool) -> None:
    """
    Advance sim_time by wall_elapsed * speed_multiplier since last checkpoint.
    Reads and writes in a single atomic UPDATE to avoid race conditions.
    """
    wall_now = time.time()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT sim_time, last_wall_checkpoint, speed_multiplier FROM sim_clock WHERE id = 1"
        )
        if row is None:
            log.error("sim_clock: no row in sim_clock table — reinitializing")
            await init_schema(pool)
            return

        wall_elapsed = wall_now - row["last_wall_checkpoint"]
        if wall_elapsed < 0:
            # Clock skew — reset checkpoint without advancing time
            wall_elapsed = 0.0

        sim_elapsed_seconds = wall_elapsed * row["speed_multiplier"]

        # Build the new sim_time by adding sim_elapsed_seconds to current sim_time
        await conn.execute("""
            UPDATE sim_clock
            SET sim_time             = sim_time + ($1 || ' seconds')::INTERVAL,
                last_wall_checkpoint = $2
            WHERE id = 1
        """, str(sim_elapsed_seconds), wall_now)


async def ticker_loop(pool: asyncpg.Pool) -> None:
    """Main ticker loop. Runs indefinitely at TICK_INTERVAL_SECONDS intervals."""
    log.info("sim_clock: ticker started, tick_interval=%.1fs", TICK_INTERVAL_SECONDS)
    while True:
        try:
            await tick(pool)
        except Exception as exc:
            log.error("sim_clock: tick error: %s", exc)
        await asyncio.sleep(TICK_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# FastAPI app + lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    log.info("sim_clock: connecting to Postgres at %s", DATABASE_URL.split("@")[-1])
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=5)
    await init_schema(_pool)
    # Start the ticker as a background task
    ticker_task = asyncio.create_task(ticker_loop(_pool))
    log.info("sim_clock: service ready")
    yield
    ticker_task.cancel()
    try:
        await ticker_task
    except asyncio.CancelledError:
        pass
    await _pool.close()
    log.info("sim_clock: shutdown complete")


app = FastAPI(
    title="FakeCo Sim Clock",
    description="Simulation clock service — advances sim_time at a configurable speed multiplier.",
    version="1.0.0",
    lifespan=lifespan,
)

PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class ClockState(BaseModel):
    sim_time: datetime
    last_wall_checkpoint: float
    speed_multiplier: float
    wall_time_utc: datetime


class SetSpeedRequest(BaseModel):
    speed_multiplier: float = Field(
        ...,
        ge=MIN_SPEED,
        le=MAX_SPEED,
        description=f"Speed multiplier ({MIN_SPEED}x–{MAX_SPEED}x). 1.0x = real time.",
    )


class SetSpeedResponse(BaseModel):
    previous_speed: float
    new_speed: float
    sim_time: datetime
    message: str


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    """Liveness probe."""
    return {"status": "ok", "service": "sim-clock"}


@app.get("/clock", response_model=ClockState)
async def get_clock(pool: PoolDep) -> ClockState:
    """Return current clock state (sim_time, speed_multiplier, wall checkpoint)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT sim_time, last_wall_checkpoint, speed_multiplier FROM sim_clock WHERE id = 1"
        )
    if row is None:
        raise HTTPException(status_code=500, detail="sim_clock row not found")
    return ClockState(
        sim_time=row["sim_time"],
        last_wall_checkpoint=row["last_wall_checkpoint"],
        speed_multiplier=row["speed_multiplier"],
        wall_time_utc=datetime.now(timezone.utc),
    )


@app.post("/set_speed", response_model=SetSpeedResponse)
async def set_speed(req: SetSpeedRequest, pool: PoolDep) -> SetSpeedResponse:
    """
    Change the speed multiplier. Change applies immediately on the next tick.
    Spec §19.2: continuous range 0.1x–10.0x; 10x is a hard cap.

    Also flushes the current elapsed time at the OLD speed before switching,
    so the transition is lossless — no simulated time is lost or double-counted.
    """
    wall_now = time.time()

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT sim_time, last_wall_checkpoint, speed_multiplier FROM sim_clock WHERE id = 1"
            )
            if row is None:
                raise HTTPException(status_code=500, detail="sim_clock row not found")

            previous_speed = row["speed_multiplier"]

            # Flush elapsed time at old speed before changing
            wall_elapsed = wall_now - row["last_wall_checkpoint"]
            if wall_elapsed < 0:
                wall_elapsed = 0.0
            sim_elapsed_seconds = wall_elapsed * previous_speed

            await conn.execute("""
                UPDATE sim_clock
                SET sim_time             = sim_time + ($1 || ' seconds')::INTERVAL,
                    last_wall_checkpoint = $2,
                    speed_multiplier     = $3
                WHERE id = 1
            """, str(sim_elapsed_seconds), wall_now, req.speed_multiplier)

            updated = await conn.fetchrow("SELECT sim_time FROM sim_clock WHERE id = 1")

    new_sim_time = updated["sim_time"]
    log.info(
        "sim_clock: speed changed %.1fx → %.1fx at sim_time=%s",
        previous_speed, req.speed_multiplier, new_sim_time.isoformat()
    )

    return SetSpeedResponse(
        previous_speed=previous_speed,
        new_speed=req.speed_multiplier,
        sim_time=new_sim_time,
        message=f"Speed changed from {previous_speed}x to {req.speed_multiplier}x. Next tick reflects new rate.",
    )


@app.get("/sim_time")
async def get_sim_time_only(pool: PoolDep) -> dict:
    """Lightweight endpoint returning only sim_time — for services that just need the current time."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT sim_time, speed_multiplier FROM sim_clock WHERE id = 1")
    if row is None:
        raise HTTPException(status_code=500, detail="sim_clock row not found")
    return {
        "sim_time": row["sim_time"].isoformat(),
        "speed_multiplier": row["speed_multiplier"],
    }
