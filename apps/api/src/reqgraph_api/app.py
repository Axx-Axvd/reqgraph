"""The FastAPI application: create_app() for uvicorn, the tests and the OpenAPI export."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from reqgraph import __version__

from reqgraph_api.auth import TokenVerifier
from reqgraph_api.db import Database, make_pool
from reqgraph_api.routes import health, projects, runs
from reqgraph_api.settings import Settings

DESCRIPTION = (
    "API reqgraph: проекты, прогоны агентов, ответы интервью, граф требований и выгрузки. "
    "Вход — токен Supabase Auth в заголовке Authorization: Bearer."
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
        try:
            yield
        finally:
            if pool is not None:
                await pool.close()

    app = FastAPI(
        title="reqgraph API", version=__version__, description=DESCRIPTION, lifespan=lifespan
    )
    app.state.db = database
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
