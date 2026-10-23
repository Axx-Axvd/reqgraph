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
    """Write the public JSON Schemas (GraphPatch, ArtifactGraph, ProjectConfig) from Pydantic."""
    from reqgraph.schemas import SCHEMAS, render

    out.mkdir(parents=True, exist_ok=True)
    for name in SCHEMAS:
        path = out / f"{name}.schema.json"
        path.write_text(render(name), encoding="utf-8", newline="\n")
        typer.echo(f"записано: {path}")


@app.command("bpmn")
def bpmn(
    path: Annotated[Path, typer.Argument(help="Process DSL file (*.process.json).")],
    out: Annotated[Path | None, typer.Option("--out", "-o", help="BPMN file to write.")] = None,
) -> None:
    """Compile a process DSL file to BPMN 2.0 (for Camunda Modeler or bpmn-js)."""
    import json

    from reqgraph.dsl.bpmn_compile import compile_bpmn
    from reqgraph.dsl.bpmn_xsd import validate_bpmn
    from reqgraph.dsl.process import DslError, parse_process

    try:
        xml = compile_bpmn(parse_process(json.loads(path.read_text(encoding="utf-8"))))
    except (DslError, json.JSONDecodeError) as exc:
        typer.echo(f"{path}: {exc}", err=True)
        raise typer.Exit(1) from None
    errors = validate_bpmn(xml)
    if errors:  # a compiler bug: the DSL was valid
        typer.echo("\n".join(f"{path}: XSD: {e}" for e in errors), err=True)
        raise typer.Exit(2)
    if out is None:
        typer.echo(xml, nl=False)
    else:
        out.write_bytes(xml.encode("utf-8"))
        typer.echo(f"записано: {out}")


if __name__ == "__main__":
    app()
