"""Command-line entry point: ``reqgraph``."""

from pathlib import Path
from typing import Annotated

import typer

from reqgraph import __version__

app = typer.Typer(name="reqgraph", no_args_is_help=True, add_completion=False)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"reqgraph {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """reqgraph: interview -> requirements -> models as code -> CI -> SRS and TZ."""


@app.command("schemas")
def schemas(
    out: Annotated[Path, typer.Option("--out", help="Folder for *.schema.json.")] = Path("schemas"),
) -> None:
    """Write the public JSON Schemas (GraphPatch, ArtifactGraph) from the Pydantic models."""
    from reqgraph.schemas import SCHEMAS, render

    out.mkdir(parents=True, exist_ok=True)
    for name in SCHEMAS:
        path = out / f"{name}.schema.json"
        path.write_text(render(name), encoding="utf-8", newline="\n")
        typer.echo(f"записано: {path}")


if __name__ == "__main__":
    app()
