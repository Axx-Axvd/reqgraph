"""The job queue in Postgres (ADR-009): one worker takes a job with FOR UPDATE SKIP LOCKED.

A running job is renewed by a heartbeat; one without it for `stale` seconds was abandoned (the
process died, Render put it to sleep) and is taken again, up to MAX_ATTEMPTS times. The jobs of
one run go strictly in order and never two at once.
"""

from typing import Any
from uuid import UUID

from psycopg.rows import DictRow

from reqgraph_api.db import Conn

MAX_ATTEMPTS = 3
JOB = "id, run_id, kind, payload, attempts"

CLAIM = f"""
update public.jobs set status = 'running', locked_at = now(), attempts = attempts + 1
where id = (
  select j.id from public.jobs j
  where (j.status = 'queued'
         or (j.status = 'running' and j.locked_at < now() - make_interval(secs => %(stale)s)))
    and j.attempts < %(max)s
    and not exists (
      select 1 from public.jobs e
      where e.run_id = j.run_id and e.id < j.id and e.status in ('queued', 'running'))
    and not exists (
      select 1 from public.jobs o
      where o.run_id = j.run_id and o.id <> j.id and o.status = 'running'
        and o.locked_at >= now() - make_interval(secs => %(stale)s))
  order by j.id
  for update skip locked
  limit 1)
returning {JOB}
"""

EXHAUSTED = """
update public.jobs set status = 'failed', finished_at = now(),
  error = coalesce(error, 'задача брошена ' || attempts || ' раза подряд')
where (status = 'running' and locked_at < now() - make_interval(secs => %(stale)s)
       or status = 'queued') and attempts >= %(max)s
returning run_id, error
"""


async def claim(conn: Conn, stale: int) -> DictRow | None:
    """The next job to run, or None; jobs that used up their attempts fail their run first."""
    params: dict[str, Any] = {"stale": stale, "max": MAX_ATTEMPTS}
    for row in await (await conn.execute(EXHAUSTED, params)).fetchall():
        await fail_run(conn, row["run_id"], row["error"])
    return await (await conn.execute(CLAIM, params)).fetchone()


async def heartbeat(conn: Conn, job_id: int) -> None:
    await conn.execute("update public.jobs set locked_at = now() where id = %s", [job_id])


async def finish(conn: Conn, job_id: int, status: str, error: str | None = None) -> None:
    await conn.execute(
        "update public.jobs set status = %s, error = %s, finished_at = now() where id = %s",
        [status, error, job_id],
    )


async def retry_or_fail(conn: Conn, job: DictRow, error: str) -> bool:
    """After an error the job waits for another attempt from the checkpoint; True — no attempts
    are left and the run failed."""
    if job["attempts"] >= MAX_ATTEMPTS:
        await finish(conn, job["id"], "failed", error)
        await fail_run(conn, job["run_id"], error)
        return True
    await conn.execute(
        "update public.jobs set status = 'queued', locked_at = null, error = %s where id = %s",
        [error, job["id"]],
    )
    return False


async def fail_run(conn: Conn, run_id: UUID, error: str) -> None:
    await conn.execute(
        "update public.runs set status = 'failed', error = %s, finished_at = now() "
        "where id = %s and status not in ('succeeded', 'failed', 'cancelled')",
        [error, run_id],
    )
    await conn.execute(
        "update public.jobs set status = 'failed', finished_at = now(), "
        "error = 'прогон остановлен' where run_id = %s and status = 'queued'",
        [run_id],
    )


async def cancel_requested(conn: Conn, run_id: UUID, after: int) -> bool:
    row = await (
        await conn.execute(
            "select 1 from public.jobs where run_id = %s and kind = 'cancel' and id > %s "
            "and status = 'queued' limit 1",
            [run_id, after],
        )
    ).fetchone()
    return row is not None


async def cancel_run(conn: Conn, run_id: UUID) -> None:
    """The run is cancelled; its waiting jobs (answers, the cancel itself) are done."""
    await conn.execute(
        "update public.runs set status = 'cancelled', finished_at = now() "
        "where id = %s and status not in ('succeeded', 'failed', 'cancelled')",
        [run_id],
    )
    await conn.execute(
        "update public.jobs set status = 'done', finished_at = now() "
        "where run_id = %s and status = 'queued'",
        [run_id],
    )
