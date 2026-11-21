"""T-506 · the daily cleanup of the demo: old exports (files and rows), old run events and the
checkpoints of runs finished long ago; the rest stays."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import psycopg
import pytest
from httpx import AsyncClient
from reqgraph_api import maintenance
from reqgraph_api.db import Database
from reqgraph_api.worker.loop import run_once
from reqgraph_api.worker.runner import Runner

from .conftest import Token
from .test_worker import STALE, auth, rows, start, stub_models

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
OLD = timedelta(days=40)


class FakeStorage:
    def __init__(self) -> None:
        self.removed: list[str] = []

    async def upload(self, path: str, data: bytes, content_type: str) -> None:
        raise AssertionError("cleanup uploads nothing")

    async def remove(self, paths: list[str]) -> None:
        self.removed += paths


def sql(database_url: str, query: str, params: list[object]) -> None:
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(query, params)


async def test_cleanup_removes_only_what_is_old(
    client: AsyncClient,
    token: Token,
    new_user: Callable[[], UUID],
    database: Database,
    database_url: str,
) -> None:
    runner = Runner(
        database, database_url, options={"models": stub_models(), "offline": True, "max_iter": 0}
    )
    await runner.setup()
    with psycopg.connect(database_url, autocommit=True) as conn:  # other tests' jobs are not ours
        conn.execute("update jobs set status = 'done' where status in ('queued', 'running')")
    headers = auth(token, new_user())
    old_run = await start(client, headers, "brief")
    new_run = await start(client, headers, "brief")
    assert await run_once(database, runner, STALE) and await run_once(database, runner, STALE)
    pid = rows(database_url, "select project_id from runs where id = %s", [old_run])[0][0]
    now = datetime.now(UTC)
    sql(database_url, "update runs set finished_at = %s where id = %s", [now - OLD, old_run])
    sql(database_url, "update run_events set ts = %s where run_id = %s", [now - OLD, old_run])
    for path, age in [(f"{pid}/1/srs.docx", OLD), (f"{pid}/2/srs.docx", timedelta(days=1))]:
        sql(
            database_url,
            "insert into exports (project_id, rev, format, storage_path, created_at) "
            "values (%s, %s, 'docx', %s, %s)",
            [pid, int(path.split("/")[1]), path, now - age],
        )
    checkpoints = "select count(*) from lg.checkpoints where thread_id = %s"
    assert rows(database_url, checkpoints, [old_run])[0][0] > 0

    storage = FakeStorage()
    done = await maintenance.cleanup(database, storage, now=now)

    assert storage.removed == [f"{pid}/1/srs.docx"]
    left = rows(database_url, "select storage_path from exports where project_id = %s", [pid])
    assert left == [(f"{pid}/2/srs.docx",)]
    assert rows(database_url, "select count(*) from run_events where run_id = %s", [old_run]) == [
        (0,)
    ]
    assert (
        rows(database_url, "select count(*) from run_events where run_id = %s", [new_run])[0][0] > 0
    )
    assert rows(database_url, checkpoints, [old_run]) == [(0,)]
    assert rows(database_url, checkpoints, [new_run])[0][0] > 0
    assert done.exports == 1 and done.events > 0 and done.checkpoints > 0

    again = await maintenance.cleanup(database, storage, now=now)
    assert (again.exports, again.events, again.checkpoints) == (0, 0, 0)


async def test_without_storage_old_export_rows_stay(
    client: AsyncClient,
    token: Token,
    new_user: Callable[[], UUID],
    database: Database,
    database_url: str,
) -> None:
    headers = auth(token, new_user())
    created = await client.post("/projects", json={"name": "A", "brief": "Б."}, headers=headers)
    pid = created.json()["id"]
    sql(
        database_url,
        "insert into exports (project_id, rev, format, storage_path, created_at) "
        "values (%s, 0, 'md', %s, %s)",
        [pid, f"{pid}/0/srs.md", datetime.now(UTC) - OLD],
    )
    done = await maintenance.cleanup(database, None)
    assert done.exports == 0  # the file cannot be removed: its row is kept, the link still works
    assert rows(database_url, "select count(*) from exports where project_id = %s", [pid]) == [(1,)]
