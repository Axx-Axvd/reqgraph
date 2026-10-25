"""Command line: ``reqgraph-evals probe | rescore | analyst | modeler | standards | repair |
scenarios | interview | metrics | matrix | label | agreement``."""

import asyncio
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, cast

import typer

from reqgraph_evals import analyst, interview, modeler, probe, repair, standards
from reqgraph_evals import scenario as scenario_files

if TYPE_CHECKING:
    from reqgraph.sim.stakeholder import Character

    from reqgraph_evals.metrics import harness

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


@app.command("modeler")
def modeler_cmd(
    scenarios: Annotated[str, typer.Option(help="сценарии через запятую")] = ",".join(analyst.DEV),
    repeat: Annotated[int, typer.Option(min=1, help="сколько раз прогнать каждый")] = 1,
    profile: Annotated[str, typer.Option(help="профиль llm/roles.yaml")] = "free",
    out: Annotated[Path, typer.Option(help="папка отчётов")] = REPORTS,
    tag: Annotated[str, typer.Option(help="суффикс имени файла")] = "",
) -> None:
    """Прогнать Analyst → Modeler на dev-брифах (T-203): SCH-002 и доля процессов без SND-001."""
    rows: list[modeler.Row] = []
    for scenario in [s.strip() for s in scenarios.split(",") if s.strip()]:
        for index in range(1, repeat + 1):
            typer.echo(f"modeler: {scenario} #{index}")
            rows.append(asyncio.run(modeler.run_scenario(scenario, index, profile=profile)))
    stem = f"modeler-{date.today().isoformat()}-{profile}{'-' + tag if tag else ''}"
    modeler.write_csv(rows, out / f"{stem}.csv")
    summary = modeler.summary_markdown(rows)
    (out / f"{stem}.md").write_text(summary, encoding="utf-8")
    typer.echo(summary)
    typer.echo(f"-> {out / stem}.csv, {stem}.md")


@app.command("standards")
def standards_cmd(
    scenarios: Annotated[str, typer.Option(help="сценарии через запятую")] = ",".join(analyst.DEV),
    repeat: Annotated[int, typer.Option(min=1, help="сколько раз прогнать каждый")] = 1,
    profile: Annotated[str, typer.Option(help="профиль llm/roles.yaml")] = "free",
    out: Annotated[Path, typer.Option(help="папка отчётов")] = REPORTS,
    tag: Annotated[str, typer.Option(help="суффикс имени файла")] = "",
) -> None:
    """Прогнать Analyst → Modeler → Standards на dev-брифах (T-204): заполненность разделов SRS."""
    rows: list[standards.Row] = []
    for scenario in [s.strip() for s in scenarios.split(",") if s.strip()]:
        for index in range(1, repeat + 1):
            typer.echo(f"standards: {scenario} #{index}")
            rows.append(asyncio.run(standards.run_scenario(scenario, index, profile=profile)))
    stem = f"standards-{date.today().isoformat()}-{profile}{'-' + tag if tag else ''}"
    standards.write_csv(rows, out / f"{stem}.csv")
    summary = standards.summary_markdown(rows)
    (out / f"{stem}.md").write_text(summary, encoding="utf-8")
    typer.echo(summary)
    typer.echo(f"-> {out / stem}.csv, {stem}.md")


@app.command("repair")
def repair_cmd(
    scenarios: Annotated[str, typer.Option(help="сценарии через запятую")] = ",".join(analyst.DEV),
    repeat: Annotated[int, typer.Option(min=1, help="сколько раз прогнать каждый")] = 1,
    profile: Annotated[str, typer.Option(help="профиль llm/roles.yaml")] = "free",
    reviewer: Annotated[
        str, typer.Option(help="llm или template (абляция «без Reviewer»)")
    ] = "llm",
    out: Annotated[Path, typer.Option(help="папка отчётов")] = REPORTS,
    tag: Annotated[str, typer.Option(help="суффикс имени файла")] = "",
) -> None:
    """Весь конвейер с циклом ремонта на dev-брифах (T-205): сходится или needs_human."""
    if reviewer not in ("llm", "template"):
        raise typer.BadParameter("reviewer: llm или template")
    rows: list[repair.Row] = []
    for scenario in [s.strip() for s in scenarios.split(",") if s.strip()]:
        for index in range(1, repeat + 1):
            typer.echo(f"repair: {scenario} #{index}")
            mode: Literal["llm", "template"] = "llm" if reviewer == "llm" else "template"
            rows.append(
                asyncio.run(repair.run_scenario(scenario, index, profile=profile, reviewer=mode))
            )
    stem = f"repair-{date.today().isoformat()}-{profile}-{reviewer}{'-' + tag if tag else ''}"
    repair.write_csv(rows, out / f"{stem}.csv")
    summary = repair.summary_markdown(rows)
    (out / f"{stem}.md").write_text(summary, encoding="utf-8")
    typer.echo(summary)
    typer.echo(f"-> {out / stem}.csv, {stem}.md")


@app.command("scenarios")
def scenarios_cmd(
    seal: Annotated[
        bool, typer.Option(help="переписать печать test-сценариев (после проверки автором)")
    ] = False,
) -> None:
    """Проверить 15 сценариев: формат, размер, области, долю в брифе и печать test-сценариев.

    Тексты test-сценариев не печатаются: только id, размер и найденные проблемы."""
    bad = 0
    for scenario_id in scenario_files.scenario_ids():
        item = scenario_files.load_scenario(scenario_id, final=True)  # only checked, not printed
        found = scenario_files.problems(item)
        hidden = item.hidden.requirements
        share = sum(r.in_brief for r in hidden) / len(hidden)
        typer.echo(
            f"{scenario_id}: {item.info.size}, требований {len(hidden)}, в брифе {share:.0%}"
            + ("" if found else " — ок")
        )
        for problem in found:
            typer.echo(f"  {problem}")
        bad += bool(found)
    if seal:
        path = scenario_files.SCENARIOS / scenario_files.MANIFEST
        path.write_text(scenario_files.manifest(), encoding="utf-8", newline="\n")
        typer.echo(f"печать обновлена: {path}")
    broken = scenario_files.seal_broken()
    if broken:
        typer.echo("печать test-сценариев нарушена (файлы менялись после печати):")
        for line in broken:
            typer.echo(f"  {line.split('  ', 1)[-1]}")
    raise typer.Exit(1 if bad or broken else 0)


@app.command("interview")
def interview_cmd(
    scenarios: Annotated[str, typer.Option(help="сценарии через запятую")] = ",".join(analyst.DEV),
    characters: Annotated[
        str, typer.Option(help="характеры: cooperative, vague, contradictory")
    ] = ",".join(interview.CHARACTERS),
    repeat: Annotated[int, typer.Option(min=1, help="повторов на сценарий и характер")] = 1,
    profile: Annotated[str, typer.Option(help="профиль моделей roles.yaml")] = "free",
    interviewer: Annotated[str, typer.Option(help="coverage (M2) или free (M1)")] = "coverage",
    max_turns: Annotated[int, typer.Option(min=1, help="вопросов не больше")] = 30,
    out: Annotated[Path, typer.Option(help="папка отчётов")] = REPORTS,
    tag: Annotated[str, typer.Option(help="суффикс имени файла")] = "",
) -> None:
    """Интервью «интервьюер ↔ симулятор заказчика» на dev-сценариях (T-302): CSV, сводка и
    диалоги для ручной проверки; проекты прогонов — в evals/runs/<дата>/interview/."""
    if interviewer not in ("coverage", "free"):
        raise typer.BadParameter("interviewer: coverage или free")
    picked = [c.strip() for c in characters.split(",") if c.strip()]
    if unknown := [c for c in picked if c not in interview.CHARACTERS]:
        raise typer.BadParameter(f"нет характера: {', '.join(unknown)}")
    stem = f"interview-{date.today().isoformat()}-{profile}-{interviewer}{'-' + tag if tag else ''}"
    keep = REPORTS.parent / "runs" / date.today().isoformat() / "interview"
    rows: list[interview.Row] = []
    for scenario_id in [s.strip() for s in scenarios.split(",") if s.strip()]:
        for character in picked:
            for index in range(1, repeat + 1):
                typer.echo(f"interview: {scenario_id} {character} #{index}")
                rows.append(
                    asyncio.run(
                        interview.run_interview(
                            scenario_id,
                            character,  # type: ignore[arg-type]
                            index,
                            profile=profile,
                            interviewer="coverage" if interviewer == "coverage" else "free",
                            max_turns=max_turns,
                            dialogs=out / "dialogs" / stem,
                            keep=keep,
                        )
                    )
                )
    interview.write_csv(rows, out / f"{stem}.csv")
    summary = interview.summary_markdown(rows)
    (out / f"{stem}.md").write_text(summary, encoding="utf-8")
    typer.echo(summary)
    typer.echo(f"-> {out / stem}.csv, {stem}.md, dialogs/{stem}/")


def _metrics_out(
    results: list["harness.Result"], pairs: list[dict[str, object]], out: Path, stem: str
) -> None:
    from reqgraph_evals.metrics import harness

    harness.write_results(results, out / f"{stem}.csv")
    harness.write_pairs(pairs, out / "labels" / f"pairs-{stem}.csv")
    summary = harness.summary_markdown(results)
    (out / f"{stem}.md").write_text(summary, encoding="utf-8")
    typer.echo(summary)
    typer.echo(f"-> {out / stem}.csv, {stem}.md, labels/pairs-{stem}.csv")


@app.command("metrics")
def metrics_cmd(
    interviews: Annotated[
        Path,
        typer.Argument(help="CSV отчёта reqgraph-evals interview", exists=True, dir_okay=False),
    ],
    runs: Annotated[
        Path, typer.Option(help="папка проектов этих прогонов (runs/<дата>/interview)")
    ],
    profile: Annotated[str, typer.Option(help="профиль: судья и эмбеддинги")] = "free",
    out: Annotated[Path, typer.Option(help="папка отчётов")] = REPORTS,
    tag: Annotated[str, typer.Option(help="суффикс имени файла")] = "",
) -> None:
    """Посчитать метрики (recall, ambiguity, validity, soundness, trace) по сохранённым прогонам
    интервью: results-*.csv и пары для ручной проверки судьи (labels/pairs-*.csv)."""
    from reqgraph_evals.metrics import harness

    rows = harness.read_interview_rows(interviews)
    cases = [
        harness.RunInputs(
            r.scenario,
            cast("Character", r.character),
            "M2" if r.interviewer == "coverage" else "M1",
            r.repeat,
        )
        for r in rows.values()
    ]
    results, pairs = asyncio.run(
        harness.evaluate(cases, harness.saved_task(rows, runs), profile=profile)
    )
    stem = f"results-{date.today().isoformat()}-{profile}{'-' + tag if tag else ''}"
    _metrics_out(results, pairs, out, stem)


@app.command("matrix")
def matrix_cmd(
    scenarios: Annotated[str, typer.Option(help="сценарии через запятую")] = ",".join(analyst.DEV),
    characters: Annotated[str, typer.Option(help="характеры через запятую")] = ",".join(
        interview.CHARACTERS
    ),
    methods: Annotated[str, typer.Option(help="M2 (с покрытием), M1 (без)")] = "M2",
    repeat: Annotated[int, typer.Option(min=1, help="повторов")] = 1,
    profile: Annotated[str, typer.Option(help="профиль моделей roles.yaml")] = "free",
    max_turns: Annotated[int, typer.Option(min=1, help="вопросов не больше")] = 30,
    out: Annotated[Path, typer.Option(help="папка отчётов")] = REPORTS,
    tag: Annotated[str, typer.Option(help="суффикс имени файла")] = "",
) -> None:
    """Прогнать интервью с симулятором и сразу посчитать метрики (pydantic-evals): results-*.csv.
    Test-сценарии не запускаются до финальной матрицы (S6)."""
    from reqgraph_evals.metrics import harness

    cases = [
        harness.RunInputs(s.strip(), c.strip(), m.strip(), r)  # type: ignore[arg-type]
        for s in scenarios.split(",")
        if s.strip()
        for c in characters.split(",")
        if c.strip()
        for m in methods.split(",")
        if m.strip()
        for r in range(1, repeat + 1)
    ]
    stem = f"results-{date.today().isoformat()}-{profile}{'-' + tag if tag else ''}"
    runs = REPORTS.parent / "runs" / date.today().isoformat() / "matrix"
    task = harness.run_task(
        profile=profile, max_turns=max_turns, runs=runs, dialogs=out / "dialogs" / stem
    )
    results, pairs = asyncio.run(harness.evaluate(cases, task, profile=profile))
    _metrics_out(results, pairs, out, stem)


@app.command("label")
def label_cmd(
    pairs: Annotated[Path, typer.Argument(help="labels/pairs-*.csv", exists=True, dir_okay=False)],
    share: Annotated[float, typer.Option(min=0.01, max=1.0, help="доля пар для разметки")] = 0.2,
    seed: Annotated[int, typer.Option(help="seed выборки")] = 42,
) -> None:
    """Ручная разметка случайных 20% пар «эталон — найденное»: y / n; q — закончить и сохранить."""
    from reqgraph_evals.metrics import label

    done = label.label(pairs, input, share=share, seed=seed, echo=typer.echo)
    typer.echo(f"размечено пар: {done} -> {label.human_path(pairs)}")


@app.command("agreement")
def agreement_cmd(
    pairs: Annotated[Path, typer.Argument(help="labels/pairs-*.csv", exists=True, dir_okay=False)],
) -> None:
    """Согласие судьи с ручной разметкой: каппа Коэна (порог 0.8) и доля совпадений."""
    from reqgraph_evals.metrics import label

    try:
        result = label.compare(pairs)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from None
    verdict = "да" if result["kappa"] >= 0.8 else "нет"
    text = (
        f"# Согласие судьи с ручной разметкой\n\nПар: {result['pairs']}; каппа Коэна "
        f"{result['kappa']}; доля совпадений {result['agreement']}; «да» у судьи "
        f"{result['judge_yes']}, у человека {result['human_yes']}. Порог T-304 (каппа ≥ 0.8) "
        f"выполнен: {verdict}.\n"
    )
    (pairs.parent / f"agreement-{pairs.stem.removeprefix('pairs-')}.md").write_text(
        text, encoding="utf-8"
    )
    typer.echo(text)
