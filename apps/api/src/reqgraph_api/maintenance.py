"""T-506 · upkeep of the public demo: the daily cleanup (07_deploy) and the process memory
(Render Free gives 512 MB to the API, the worker, pandoc and pm4py together)."""

import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from reqgraph_api.db import Database
from reqgraph_api.storage import Storage

log = logging.getLogger("reqgraph.maintenance")
FINISHED = ("succeeded", "failed", "cancelled")
# what LangGraph's Postgres saver keeps per thread (thread_id = run id), schema lg (T-502)
CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")


@dataclass(frozen=True)
class Cleaned:
    exports: int  # files removed from Storage, with their rows
    events: int  # run_events rows
    checkpoints: int  # rows of the lg tables


async def cleanup(
    db: Database,
    storage: Storage | None,
    *,
    now: datetime | None = None,
    export_days: int = 30,
    event_days: int = 30,
    checkpoint_days: int = 14,
) -> Cleaned:
    """Exports older than 30 days (the files first, then the rows: a row without a file would be
    a dead link), run events older than 30 days, checkpoints of runs finished over 14 days ago.
    Without Storage old exports stay: their files cannot be removed."""
    now = now or datetime.now(UTC)
    exports = 0
    async with db.as_service() as conn:
        if storage is not None:
            cur = await conn.execute(
                "select id, storage_path from public.exports where created_at < %s",
                [now - timedelta(days=export_days)],
            )
            old = await cur.fetchall()
            if old:
                await storage.remove([r["storage_path"] for r in old])
                await conn.execute(
                    "delete from public.exports where id = any(%s)", [[r["id"] for r in old]]
                )
                exports = len(old)
        events = (
            await conn.execute(
                "delete from public.run_events where ts < %s", [now - timedelta(days=event_days)]
            )
        ).rowcount
    # schema lg is closed to the API roles (T-502): the checkpoints go on the connection's own
    # user, who owns lg and its tables, as the worker's checkpointer does
    threads = "select id::text from public.runs where status = any(%s) and finished_at < %s"
    params: list[object] = [list(FINISHED), now - timedelta(days=checkpoint_days)]
    checkpoints = 0
    async with db.pool.connection() as conn, conn.transaction():
        for table in CHECKPOINT_TABLES:
            exists = await (
                await conn.execute("select to_regclass(%s) is not null as ok", [f"lg.{table}"])
            ).fetchone()
            if exists and exists["ok"]:
                cur = await conn.execute(
                    f"delete from lg.{table} where thread_id in ({threads})", params
                )
                checkpoints += cur.rowcount
    done = Cleaned(exports=exports, events=events, checkpoints=checkpoints)
    log.info(
        "cleanup: exports %s, run events %s, checkpoint rows %s",
        done.exports,
        done.events,
        done.checkpoints,
    )
    return done


def _status_mb(key: str) -> float | None:
    """A size from /proc/self/status (Linux: Render, CI, the offline stand), in MB."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith(f"{key}:"):
                return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return None


def memory_mb() -> float | None:
    """Resident memory of this process now; None where the system does not say (Windows)."""
    return _status_mb("VmRSS")


def peak_memory_mb() -> float | None:
    """The most resident memory this process has had (child processes such as pandoc are not
    counted: they have their own)."""
    peak = _status_mb("VmHWM")
    if peak is not None or sys.platform == "win32":
        return peak
    import resource

    used = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # KB on Linux, bytes on macOS
    return round(used / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)
