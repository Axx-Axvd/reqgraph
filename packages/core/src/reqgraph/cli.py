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


@app.command("render")
def render(
    path: Annotated[Path, typer.Argument(help="Model file: .dbml, .puml, .dsl or .bpmn.")],
    out: Annotated[Path | None, typer.Option("--out", "-o", help="SVG file to write.")] = None,
) -> None:
    """Draw a model as SVG through Kroki (KROKI_URL, default kroki.io); results are cached."""
    import asyncio

    from reqgraph.dsl.kroki import KIND_BY_SUFFIX, render_svg

    kind = KIND_BY_SUFFIX.get(path.suffix)
    if kind is None:
        known = ", ".join(KIND_BY_SUFFIX)
        typer.echo(f"{path}: расширение {path.suffix} не поддерживается, есть {known}", err=True)
        raise typer.Exit(1)
    result = asyncio.run(render_svg(kind, path.read_text(encoding="utf-8")))
    if result.offline:
        typer.echo(f"{path}: {result.error}", err=True)
        raise typer.Exit(2)
    if result.svg is None:
        typer.echo(f"{path}: диаграмма не компилируется: {result.error}", err=True)
        raise typer.Exit(1)
    if out is None:
        typer.echo(result.svg, nl=False)
    else:
        out.write_bytes(result.svg.encode("utf-8"))
        typer.echo(f"записано: {out}")


@app.command("check")
def check(
    path: Annotated[Path, typer.Argument(help="Project folder (with reqgraph.yaml).")],
    no_write: Annotated[
        bool, typer.Option("--no-write", help="Do not write reports/ci-report.*")
    ] = False,
    offline: Annotated[
        bool, typer.Option("--offline", help="Skip the checks that need Kroki.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
) -> None:
    """Run the checks; exit code 1 when there are errors, 2 when the project cannot be read."""
    import asyncio

    from reqgraph.checks.runner import run_checks
    from reqgraph.dsl.readers import model_readers
    from reqgraph.graph.store import FileStore, StoreError

    try:
        project = FileStore(path, readers=model_readers()).load()
    except StoreError as exc:
        typer.echo(f"проект не прочитан: {exc}", err=True)
        raise typer.Exit(2) from None
    for warning in project.warnings:
        typer.echo(f"предупреждение: {warning}", err=True)
    report = asyncio.run(run_checks(project, offline=offline))
    if not no_write:
        reports = path / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "ci-report.json").write_bytes(report.to_json().encode("utf-8"))
        (reports / "ci-report.md").write_bytes(report.to_markdown().encode("utf-8"))
    typer.echo(report.to_json() if as_json else report.to_markdown(), nl=False)
    raise typer.Exit(0 if report.ok else 1)


if __name__ == "__main__":
    app()
