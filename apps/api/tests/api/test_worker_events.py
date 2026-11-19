"""PgEvents without a database (T-502): the core emits synchronously, rows are written in order."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import uuid4

import pytest
from reqgraph_api.db import Database
from reqgraph_api.worker.events import PgEvents

pytestmark = pytest.mark.anyio


class FakeCursor:
    def __init__(self, written: list[tuple[Any, ...]]) -> None:
        self.written = written

    async def __aenter__(self) -> "FakeCursor":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def executemany(self, query: str, rows: list[tuple[Any, ...]]) -> None:
        await asyncio.sleep(0)  # a real insert yields to the loop
        self.written.extend(rows)


class FakeDb:
    def __init__(self) -> None:
        self.written: list[tuple[Any, ...]] = []

    @asynccontextmanager
    async def as_service(self) -> AsyncIterator[Any]:
        class Conn:
            def cursor(inner) -> FakeCursor:
                return FakeCursor(self.written)

        yield Conn()


async def test_events_are_written_in_order_and_close_waits_for_them() -> None:
    db = FakeDb()
    run = uuid4()
    events = PgEvents(cast(Database, db), run)
    events.emit("run_start", mode="brief")
    for n in range(5):
        events.emit("node_start", node=f"n{n}", at=object())  # anything not JSON is kept as text
    await events.close()
    assert [row[1] for row in db.written] == ["run_start"] + ["node_start"] * 5
    assert [row[2].obj["node"] for row in db.written[1:]] == [f"n{n}" for n in range(5)]
    assert all(row[0] == run for row in db.written)
    assert isinstance(db.written[1][2].obj["at"], str)


async def test_close_without_events_does_nothing() -> None:
    await PgEvents(cast(Database, FakeDb()), uuid4()).close()
