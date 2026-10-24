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


@app.command("init")
def init(
    path: Annotated[Path, typer.Argument(help="New project folder.")],
    name: Annotated[str, typer.Option("--name", help="Project name, any language.")],
    brief: Annotated[Path, typer.Option("--brief", help="Brief file (Markdown).")],
    project_id: Annotated[
        str | None, typer.Option("--id", help="Project id, latin (default: folder name).")
    ] = None,
    profile: Annotated[str, typer.Option("--profile", help="free, cheap or local.")] = "free",
) -> None:
    """Create a project folder: reqgraph.yaml and brief.md."""
    from reqgraph.agents.run import RunFailed, init_project

    if profile not in ("free", "cheap", "local"):
        raise typer.BadParameter("профиль: free, cheap или local")
    try:
        text = brief.read_text(encoding="utf-8")
        root = init_project(path, name=name, brief=text, project_id=project_id, profile=profile)  # type: ignore[arg-type]
    except (RunFailed, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from None
    typer.echo(f"создан проект: {root}")


@app.command("run")
def run(
    path: Annotated[Path, typer.Argument(help="Project folder (with reqgraph.yaml).")],
    brief: Annotated[
        Path | None, typer.Option("--brief", help="Brief file instead of the project's brief.md.")
    ] = None,
    profile: Annotated[
        str | None, typer.Option("--profile", help="Model profile of llm/roles.yaml.")
    ] = None,
    budget_usd: Annotated[
        float | None, typer.Option("--budget-usd", help="Budget of the run, $.")
    ] = None,
    max_iter: Annotated[int | None, typer.Option("--max-iter", help="Repair rounds.")] = None,
    reviewer: Annotated[
        str, typer.Option("--reviewer", help="llm, or template (the ablation without Reviewer).")
    ] = "llm",
    offline: Annotated[
        bool, typer.Option("--offline", help="Skip the checks that need Kroki.")
    ] = False,
    no_write: Annotated[
        bool, typer.Option("--no-write", help="Do not write the project and reports/.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print the summary as JSON.")] = False,
) -> None:
    """Brief -> requirements -> models -> SRS sections -> checks -> repair (brief mode).

    Exit code 0: no errors left; 1: errors left (needs_human, budget, rounds); 2: cannot run.
    """
    import asyncio
    import json

    from reqgraph.agents.run import RunFailed, run_project

    if reviewer not in ("llm", "template"):
        raise typer.BadParameter("reviewer: llm или template")
    try:
        text = brief.read_text(encoding="utf-8") if brief is not None else None
        summary, report = asyncio.run(
            run_project(
                path,
                brief=text,
                profile=profile,
                budget_usd=budget_usd,
                max_iter=max_iter,
                reviewer="llm" if reviewer == "llm" else "template",
                offline=offline,
                write=not no_write,
                on_line=None if as_json else typer.echo,
            )
        )
    except (RunFailed, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from None
    if as_json:
        typer.echo(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    else:
        s = summary
        typer.echo("")
        typer.echo(
            f"Требований: {s.requirements}, ролей: {s.actors}, процессов: {s.processes}, "
            f"сущностей: {s.entities}, разделов SRS: {s.sections}"
        )
        stop = {"needs_human": "нужен человек", "budget": "кончился бюджет"}.get(s.stop or "", "")
        typer.echo(f"Проверки: {s.headline}")
        typer.echo(f"Кругов ремонта: {s.iterations}" + (f" — {stop}" if stop else ""))
        typer.echo(
            f"Вызовов LLM: {s.llm_calls}, токенов: {s.input_tokens + s.output_tokens}, "
            f"${s.cost_usd:.4f}, {s.seconds:.0f} с"
        )
        if not no_write:
            typer.echo(f"Отчёт: {path / 'reports' / 'ci-report.md'}")
    raise typer.Exit(0 if report.ok else 1)


if __name__ == "__main__":
    app()
