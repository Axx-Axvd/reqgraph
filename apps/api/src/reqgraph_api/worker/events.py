"""Run events into run_events as they come (the browser follows them by Realtime or polling).

The core's EventSink is synchronous; `emit` only queues the event and a background task writes
the queue in order. `close` waits until everything is written."""

import asyncio
import json
from contextlib import suppress
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from reqgraph_api.db import Database

Event = tuple[str, dict[str, Any]]


class PgEvents:
    def __init__(self, db: Database, run_id: UUID) -> None:
        self.db, self.run_id = db, run_id
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    def emit(self, type: str, **payload: Any) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._write())
        clean = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
        self._queue.put_nowait((type, clean))

    async def _write(self) -> None:
        while True:
            batch = [await self._queue.get()]
            while not self._queue.empty():
                batch.append(self._queue.get_nowait())
            try:
                async with self.db.as_service() as conn, conn.cursor() as cur:
                    await cur.executemany(
                        "insert into public.run_events (run_id, type, payload) values (%s, %s, %s)",
                        [(self.run_id, kind, Jsonb(data)) for kind, data in batch],
                    )
            finally:
                for _ in batch:
                    self._queue.task_done()

    async def close(self) -> None:
        if self._task is None:
            return
        await self._queue.join()
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
