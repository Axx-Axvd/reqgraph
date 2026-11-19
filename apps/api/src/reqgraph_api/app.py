"""The FastAPI application: create_app() for uvicorn, the tests and the OpenAPI export."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from reqgraph import __version__

from reqgraph_api.auth import TokenVerifier
from reqgraph_api.db import Database, make_pool
from reqgraph_api.keys import RunKeys
from reqgraph_api.routes import health, projects, runs
from reqgraph_api.settings import Settings

DESCRIPTION = (
    "API reqgraph: проекты, прогоны агентов, ответы интервью, граф требований и выгрузки. "
    "Вход — токен Supabase Auth в заголовке Authorization: Bearer."
)


async def start_worker(
    db: Database, settings: Settings, stop: asyncio.Event, keys: RunKeys | None = None
) -> None:
    """The worker loop next to the API (one process on Render Free, ADR-009)."""
    from reqgraph_api.worker.loop import run_worker
    from reqgraph_api.worker.runner import Runner

    assert settings.database_url is not None
    runner = Runner(db, settings.database_url, keys=keys or RunKeys(), tz=settings.demo_timezone)
    await run_worker(
        db, runner, stop, poll=settings.worker_poll_seconds, stale=settings.job_stale_seconds
    )


def create_app(
    settings: Settings | None = None,
    *,
    database: Database | None = None,
    verifier: TokenVerifier | None = None,
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool = None
        if app.state.db is None and settings.database_url:
            pool = make_pool(settings.database_url, max_size=settings.db_pool_max)
            await pool.open()
            app.state.db = Database(pool)
        stop = asyncio.Event()
        worker = None
        if settings.worker_enabled and settings.database_url and app.state.db is not None:
            worker = asyncio.create_task(  # ADR-009: in the API process, sharing its keys
                start_worker(app.state.db, settings, stop, app.state.keys)
            )
        try:
            yield
        finally:
            stop.set()
            if worker is not None:
                worker.cancel()  # a running job stays locked and is taken again after a restart
                with suppress(asyncio.CancelledError):
                    await worker
            if pool is not None:
                await pool.close()

    app = FastAPI(
        title="reqgraph API", version=__version__, description=DESCRIPTION, lifespan=lifespan
    )
    app.state.db = database
    app.state.settings = settings
    app.state.keys = RunKeys()
    app.state.verifier = verifier or TokenVerifier.from_settings(settings)
    if settings.origins():
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.origins(),
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )
    for router in (health.router, projects.router, runs.router):
        app.include_router(router)
    return app
