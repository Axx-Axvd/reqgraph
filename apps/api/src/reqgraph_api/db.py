"""Postgres access: a small pool (Render Free) and transactions on behalf of the user.

`as_user` sets the role `authenticated` and the JWT claims for the transaction, so the RLS
policies of supabase/migrations apply to every read, as for supabase-js in the browser.
Writes the users have no policy for (runs, jobs, graph revisions) go through `elevate`
after the API has checked under RLS that the project is the user's.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import HTTPException, Request
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from reqgraph_api.auth import User

Conn = AsyncConnection[DictRow]


def make_pool(url: str, *, min_size: int = 1, max_size: int = 4) -> AsyncConnectionPool[Conn]:
    """Supavisor session pooler: autocommit (explicit transactions), no prepared statements."""
    kwargs: dict[str, Any] = {
        "autocommit": True,
        "prepare_threshold": None,
        "row_factory": dict_row,
    }
    return AsyncConnectionPool(
        url, min_size=min_size, max_size=max_size, kwargs=kwargs, open=False, connection_class=Conn
    )


class Database:
    def __init__(self, pool: AsyncConnectionPool[Conn]) -> None:
        self.pool = pool

    @asynccontextmanager
    async def as_user(self, user: User) -> AsyncIterator[Conn]:
        claims = json.dumps({"sub": str(user.id), "role": "authenticated"})
        async with self.pool.connection() as conn, conn.transaction():
            # both, as supabase/tests/rls_test.sql: older auth.uid() reads request.jwt.claim.sub
            await conn.execute(
                "select set_config('request.jwt.claims', %s, true), "
                "set_config('request.jwt.claim.sub', %s, true)",
                [claims, str(user.id)],
            )
            await conn.execute("set local role authenticated")
            yield conn

    async def ping(self) -> bool:
        async with self.pool.connection() as conn:
            row = await (await conn.execute("select 1 as ok")).fetchone()
            return row is not None and row["ok"] == 1


async def elevate(conn: Conn) -> None:
    """The rest of the transaction as the backend (service_role bypasses RLS): only after the
    ownership check under the user's role."""
    await conn.execute("set local role service_role")


def database(request: Request) -> Database:
    db: Database | None = request.app.state.db
    if db is None:
        raise HTTPException(503, "база не настроена: задайте DATABASE_URL")
    return db
