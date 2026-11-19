"""reqgraph-api serve | openapi."""

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
