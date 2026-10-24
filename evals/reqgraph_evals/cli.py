"""Command line: ``reqgraph-evals probe | rescore | analyst``."""

import asyncio
from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from reqgraph_evals import analyst, probe

app = typer.Typer(name="reqgraph-evals", no_args_is_help=True, add_completion=False)
REPORTS = Path(__file__).resolve().parent.parent / "reports"


@app.callback()
def main() -> None:
    """reqgraph evaluation tools."""


@app.command("probe")
def probe_cmd(
    models: Annotated[str, typer.Option(help="модели через запятую: провайдер/модель")],
    repeat: Annotated[int, typer.Option(min=1, help="сколько раз прогнать все задачи")] = 1,
    judge: Annotated[
        bool, typer.Option(help="LLM-судья для блока rewrite (отдельная колонка)")
    ] = False,
    concurrency: Annotated[int, typer.Option(min=1, help="параллельных задач на модель")] = 1,
    out: Annotated[Path, typer.Option(help="папка отчётов")] = REPORTS,
    tag: Annotated[str, typer.Option(help="суффикс имени файла")] = "",
) -> None:
    """Прогнать 20 задач probe на моделях и сохранить CSV и сводку в Markdown."""
    dataset = probe.build_dataset(judge=judge)
    rows: list[probe.Row] = []
    for model_id in [m.strip() for m in models.split(",") if m.strip()]:
        typer.echo(f"probe: {model_id} x{repeat}")
        rows += asyncio.run(probe.run_model(model_id, repeat, dataset, concurrency))
    stem = f"probe-{date.today().isoformat()}{'-' + tag if tag else ''}"
    probe.write_csv(rows, out / f"{stem}.csv")
    summary = probe.summary_markdown(rows)
    (out / f"{stem}.md").write_text(summary, encoding="utf-8")
    typer.echo(summary)
    typer.echo(f"-> {out / stem}.csv, {stem}.md")


@app.command("rescore")
def rescore_cmd(
    report: Annotated[Path, typer.Argument(help="CSV отчёта probe", exists=True, dir_okay=False)],
) -> None:
    """Пересчитать оценки по сохранённым ответам (модели не вызываются); перезаписать CSV и MD."""
    rows = probe.rescore(probe.read_csv(report))
    probe.write_csv(rows, report)
    summary = probe.summary_markdown(rows)
    report.with_suffix(".md").write_text(summary, encoding="utf-8")
    typer.echo(summary)


@app.command("analyst")
def analyst_cmd(
    scenarios: Annotated[str, typer.Option(help="сценарии через запятую")] = ",".join(analyst.DEV),
    repeat: Annotated[int, typer.Option(min=1, help="сколько раз прогнать каждый")] = 1,
    profile: Annotated[str, typer.Option(help="профиль llm/roles.yaml")] = "free",
    out: Annotated[Path, typer.Option(help="папка отчётов")] = REPORTS,
    tag: Annotated[str, typer.Option(help="суффикс имени файла")] = "",
) -> None:
    """Прогнать Analyst на dev-брифах (T-202): валидность патча и доля нарушений ISO-001/003."""
    rows: list[analyst.Row] = []
    for scenario in [s.strip() for s in scenarios.split(",") if s.strip()]:
        for index in range(1, repeat + 1):
            typer.echo(f"analyst: {scenario} #{index}")
            rows.append(asyncio.run(analyst.run_scenario(scenario, index, profile=profile)))
    stem = f"analyst-{date.today().isoformat()}-{profile}{'-' + tag if tag else ''}"
    analyst.write_csv(rows, out / f"{stem}.csv")
    summary = analyst.summary_markdown(rows)
    (out / f"{stem}.md").write_text(summary, encoding="utf-8")
    typer.echo(summary)
    typer.echo(f"-> {out / stem}.csv, {stem}.md")
