"""reqgraph-api serve | worker | openapi."""

import json
import os
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(name="reqgraph-api", no_args_is_help=True, add_completion=False)


def openapi_text() -> str:
    """The OpenAPI description with a stable key order (the web types are generated from it)."""
    from reqgraph_api.app import create_app
    from reqgraph_api.settings import Settings

    schema = create_app(Settings(database_url=None)).openapi()
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="адрес")] = "0.0.0.0",
    port: Annotated[int | None, typer.Option(help="порт; без него — $PORT или 8000")] = None,
) -> None:
    """Запустить API (uvicorn); настройки — из переменных окружения (07_deploy)."""
    import uvicorn

    from reqgraph_api.app import create_app

    uvicorn.run(create_app(), host=host, port=port or int(os.environ.get("PORT", "8000")))


@app.command()
def worker() -> None:
    """Только исполнитель задач, без API: локально и на офлайн-стенде (на Render — вместе с API)."""
    import asyncio
    import logging

    from reqgraph_api.app import start_worker
    from reqgraph_api.db import Database, make_pool
    from reqgraph_api.settings import Settings

    settings = Settings()
    if not settings.database_url:
        raise typer.BadParameter("нужна переменная DATABASE_URL")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    async def main() -> None:
        assert settings.database_url is not None
        pool = make_pool(settings.database_url, max_size=2)
        await pool.open()
        try:
            storage = None
            if settings.supabase_url and settings.supabase_service_role_key:
                from reqgraph_api.storage import SupabaseStorage

                storage = SupabaseStorage(settings.supabase_url, settings.supabase_service_role_key)
            await start_worker(Database(pool), settings, asyncio.Event(), storage=storage)
        finally:
            await pool.close()

    asyncio.run(main())


@app.command()
def openapi(
    out: Annotated[Path | None, typer.Option(help="файл; без него — в stdout")] = None,
) -> None:
    """Описание API в OpenAPI (schemas/openapi.json): из него — типы для сайта."""
    text = openapi_text()
    if out is None:
        typer.echo(text, nl=False)
    else:
        out.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
