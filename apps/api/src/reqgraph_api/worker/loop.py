"""The worker loop: take a job, run it, look again; one job at a time (Render Free, 0.1 CPU)."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress

from reqgraph_api.db import Database
from reqgraph_api.maintenance import peak_memory_mb
from reqgraph_api.worker import queue
from reqgraph_api.worker.runner import Runner

log = logging.getLogger("reqgraph.worker")


async def run_once(db: Database, runner: Runner, stale: int) -> bool:
    """Take and run one job; False — the queue is empty."""
    async with db.as_service() as conn:
        job = await queue.claim(conn, stale)
    if job is None:
        return False
    log.info(
        "job %s %s run %s (attempt %s)", job["id"], job["kind"], job["run_id"], job["attempts"]
    )
    await runner.handle(job)
    # Render Free has 512 MB for everything (T-506): the peak after each job goes to the log
    log.info("job %s done, peak memory %s MB", job["id"], peak_memory_mb())
    return True


Upkeep = Callable[[], Awaitable[object]]
DAY = 24 * 3600.0


async def run_worker(
    db: Database,
    runner: Runner,
    stop: asyncio.Event,
    *,
    poll: float = 2.0,
    stale: int = 120,
    upkeep: Upkeep | None = None,
    upkeep_every: float = DAY,
) -> None:
    """Jobs until stopped; `upkeep` (the daily cleanup, T-506) at start and then once a day
    between jobs."""
    await runner.setup()
    next_upkeep = time.monotonic()
    while not stop.is_set():
        if upkeep is not None and time.monotonic() >= next_upkeep:
            next_upkeep = time.monotonic() + upkeep_every
            try:
                await upkeep()
            except Exception:  # cleanup is not worth stopping the runs for
                log.exception("upkeep failed")
        try:
            busy = await run_once(db, runner, stale)
        except Exception:  # a broken connection must not kill the worker: try again later
            log.exception("worker step failed")
            busy = False
        if not busy:
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=poll)
