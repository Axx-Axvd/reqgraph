"""The worker loop: take a job, run it, look again; one job at a time (Render Free, 0.1 CPU)."""

import asyncio
import logging
from contextlib import suppress

from reqgraph_api.db import Database
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
    return True


async def run_worker(
    db: Database, runner: Runner, stop: asyncio.Event, *, poll: float = 2.0, stale: int = 120
) -> None:
    await runner.setup()
    while not stop.is_set():
        try:
            busy = await run_once(db, runner, stale)
        except Exception:  # a broken connection must not kill the worker: try again later
            log.exception("worker step failed")
            busy = False
        if not busy:
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=poll)
