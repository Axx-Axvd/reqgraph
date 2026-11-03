"""Command line: ``reqgraph-evals probe | rescore | analyst | modeler | uml | standards | repair |
scenarios | interview | metrics | matrix | label | agreement | human``."""

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, cast

import typer

from reqgraph_evals import analyst, interview, modeler, probe, repair, standards, uml
from reqgraph_evals import scenario as scenario_files

if TYPE_CHECKING:
    from reqgraph.sim.stakeholder import Character

    from reqgraph_evals import human as human_session
    from reqgraph_evals.metrics import harness

app = typer.Typer(name="reqgraph-evals", no_args_is_help=True, add_completion=False)
REPORTS = Path(__file__).resolve().parent.parent / "reports"


@app.callback()
def main() -> None:
    """reqgraph evaluation tools."""


MAX_USD = 5.0  # dollars of one matrix run without --allow-over-5 (T-406)


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
    brief: Annotated[
        bool, typer.Option(help="считать найденные факты брифа (судья, T-311)")
    ] = True,
    save: Annotated[
        bool, typer.Option("--save-runs", help="требования каждого прогона в evals/runs/ (T-311)")
    ] = False,
) -> None:
    """Прогнать Analyst на dev-брифах (T-202): валидность патча, доля нарушений ISO-001/003,
    факты брифа и разброс ФТ по повторам (T-311)."""
    rows: list[analyst.Row] = []
    stem = f"analyst-{date.today().isoformat()}-{profile}{'-' + tag if tag else ''}"
    runs = Path(__file__).resolve().parent.parent / "runs" / stem if save else None
    for scenario in [s.strip() for s in scenarios.split(",") if s.strip()]:
        for index in range(1, repeat + 1):
            typer.echo(f"analyst: {scenario} #{index}")
            rows.append(
                asyncio.run(
                    analyst.run_scenario(
                        scenario, index, profile=profile, brief_recall=brief, save=runs
                    )
                )
            )
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


@app.command("uml")
def uml_cmd(
    scenarios: Annotated[str, typer.Option(help="сценарии через запятую")] = ",".join(analyst.DEV),
    repeat: Annotated[int, typer.Option(min=1, help="сколько раз прогнать каждый")] = 1,
    profile: Annotated[str, typer.Option(help="профиль llm/roles.yaml")] = "free",
    out: Annotated[Path, typer.Option(help="папка отчётов")] = REPORTS,
    tag: Annotated[str, typer.Option(help="суффикс имени файла")] = "",
) -> None:
    """Прогнать Analyst → Modeler на dev-брифах (T-207): сценарии использования и C4 через Kroki."""
    rows: list[uml.Row] = []
    for scenario in [s.strip() for s in scenarios.split(",") if s.strip()]:
        for index in range(1, repeat + 1):
            typer.echo(f"uml: {scenario} #{index}")
            rows.append(asyncio.run(uml.run_scenario(scenario, index, profile=profile)))
    stem = f"modeler-uml-{date.today().isoformat()}-{profile}{'-' + tag if tag else ''}"
    uml.write_csv(rows, out / f"{stem}.csv")
    summary = uml.summary_markdown(rows)
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
            r.method or ("M2" if r.interviewer == "coverage" else "M1"),  # type: ignore[arg-type]
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
    methods: Annotated[
        str,
        typer.Option(
            help="M2 (с покрытием), M1 (без), B1 one-shot, B2 без проверок, B3 анкета, "
            "A1-A3 абляции M2 (T-405)"
        ),
    ] = "M2",
    repeat: Annotated[int, typer.Option(min=1, help="повторов")] = 1,
    profile: Annotated[str, typer.Option(help="профиль моделей roles.yaml")] = "free",
    max_turns: Annotated[int, typer.Option(min=1, help="вопросов не больше")] = 30,
    out: Annotated[Path, typer.Option(help="папка отчётов")] = REPORTS,
    tag: Annotated[str, typer.Option(help="суффикс имени файла")] = "",
    max_usd: Annotated[
        float, typer.Option(min=0, help="лимит $ на весь запуск: прогоны, симулятор и судья")
    ] = 1.0,
    allow_over_5: Annotated[
        bool, typer.Option("--allow-over-5", help="разрешить лимит больше $5 (потолок $20 в месяц)")
    ] = False,
) -> None:
    """Прогнать интервью с симулятором и сразу посчитать метрики (pydantic-evals): results-*.csv.
    Новые прогоны не начинаются, когда потрачен --max-usd: каждый пропущенный — строка с причиной.
    Test-сценарии не запускаются до финальной матрицы (S6)."""
    from reqgraph_evals.metrics import harness

    if any(s.strip().startswith("test") for s in scenarios.split(",")):
        typer.echo("--scenarios: test-сценарии — только в финальной матрице (S6)", err=True)
        raise typer.Exit(2)
    if max_usd > MAX_USD and not allow_over_5:
        typer.echo(
            f"--max-usd {max_usd}: больше ${MAX_USD:g} за запуск — только с --allow-over-5 "
            "(потолок $20 в месяц, CLAUDE.md)",
            err=True,
        )
        raise typer.Exit(2)
    unknown = [m for m in methods.split(",") if m.strip() and m.strip() not in harness.METHODS]
    if unknown:
        typer.echo(f"--methods: нет методов {', '.join(unknown)}", err=True)
        raise typer.Exit(2)

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
    results, pairs = asyncio.run(harness.evaluate(cases, task, profile=profile, max_usd=max_usd))
    _metrics_out(results, pairs, out, stem)
    skipped = sum(r.error.startswith(harness.LIMIT_SPENT) for r in results)
    spent = sum(r.cost_usd for r in results)
    typer.echo(f"потрачено ${spent:.4f} из ${max_usd:g}; не начато из-за лимита: {skipped}")


@app.command("groups")
def groups_cmd(
    scenarios: Annotated[
        str, typer.Argument(help="сценарии через запятую; test — все test-сценарии")
    ] = "test",
    check: Annotated[
        bool,
        typer.Option(help="вторая разметка: выборка уже размеченных, метки скрыты, затем каппа"),
    ] = False,
    share: Annotated[float, typer.Option(min=0.01, max=1.0, help="доля для --check")] = 0.2,
    out: Annotated[Path, typer.Option(help="папка отчётов (для --check)")] = REPORTS,
    root: Annotated[Path, typer.Option(hidden=True)] = scenario_files.SCENARIOS,
) -> None:
    """Разметка скрытых требований: t — типовое, u — уникальное (T-308, правило — README
    сценариев); ответ сразу записывается в hidden.yaml, q — закончить, потом можно продолжить."""
    from reqgraph_evals import groups

    ids = (
        scenario_files.scenario_ids(split="test")
        if scenarios == "test"
        else [s.strip() for s in scenarios.split(",") if s.strip()]
    )
    if check:
        result = groups.check_groups(ids, input, out=out, share=share, root=root, echo=typer.echo)
        typer.echo(
            f"проверено {result['checked']}: совпадение {result['agreement']:.0%}, "
            f"каппа {result['kappa']} -> {groups.check_path(out)}"
        )
        return
    done = groups.label_groups(ids, input, root=root, echo=typer.echo)
    typer.echo(f"размечено: типовых {done['typical']}, уникальных {done['unique']}")
    left = sum(
        r.group is None
        for i in ids
        for r in scenario_files.load_scenario(i, root, final=True).hidden.requirements
    )
    if left:
        typer.echo(f"осталось без метки: {left} — продолжить той же командой")
    elif any(i.startswith("test") for i in ids):
        typer.echo("всё размечено: uv run reqgraph-evals scenarios --seal, затем коммит")


@app.command("label")
def label_cmd(
    pairs: Annotated[Path, typer.Argument(help="labels/pairs-*.csv", exists=True, dir_okay=False)],
    share: Annotated[
        float, typer.Option(min=0.01, max=1.0, help="доля эталонов для разметки")
    ] = 0.2,
    seed: Annotated[int, typer.Option(help="seed выборки")] = 42,
) -> None:
    """Ручная разметка случайных 20% эталонов со всеми кандидатами: f — полностью, p — частично,
    n — нет; q — закончить и сохранить."""
    from reqgraph_evals.metrics import label

    done = label.label(pairs, input, share=share, seed=seed, echo=typer.echo)
    typer.echo(f"размечено эталонов: {done} -> {label.human_path(pairs)}")


@app.command("agreement")
def agreement_cmd(
    pairs: Annotated[Path, typer.Argument(help="labels/pairs-*.csv", exists=True, dir_okay=False)],
) -> None:
    """Согласие судьи с ручной разметкой по эталонам: каппа Коэна «найдено полностью или нет»
    (порог 0.8), «найдено хоть как-то» и по трём уровням."""
    from reqgraph_evals.metrics import label

    try:
        result = label.compare(pairs)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from None
    verdict = "да" if result["kappa"] >= 0.8 else "нет"
    text = (
        f"# Согласие судьи с ручной разметкой\n\nЭталонов: {result['references']}. "
        f"«Найдено полностью или нет» (это считает recall): каппа Коэна {result['kappa']}, доля "
        f"совпадений {result['agreement']}; полностью у судьи {result['judge_full']}, у человека "
        f"{result['human_full']}. «Найдено хоть как-то»: каппа {result['kappa_found']}. "
        f"Три уровня: каппа {result['kappa_3']}, доля совпадений {result['agreement_3']}; "
        f"частично у судьи {result['judge_partial']}, у человека {result['human_partial']}. "
        f"Порог T-304 (каппа «полностью» ≥ 0.8) выполнен: {verdict}.\n"
    )
    (pairs.parent / f"agreement-{pairs.stem.removeprefix('pairs-')}.md").write_text(
        text, encoding="utf-8"
    )
    typer.echo(text)


human_app = typer.Typer(
    no_args_is_help=True,
    help="Пилот «человек вместо симулятора» (T-306): один ход за вызов, ответ — в JSON.",
)
app.add_typer(human_app, name="human")


def _human_state(session: "human_session.Session") -> None:
    pending = session.pending
    typer.echo(
        json.dumps(
            {
                "session": str(session.folder),
                "status": session.status,
                "turn": pending.turn if pending else None,
                "question": pending.question if pending else None,
                "area": pending.area if pending else None,
                "csv": str(session.csv) if session.status == "done" else None,
                "dialog": str(session.dialog) if session.status == "done" else None,
            },
            ensure_ascii=False,
        )
    )


@human_app.command("card")
def human_card_cmd(scenario: Annotated[str, typer.Argument(help="dev-сценарий")]) -> None:
    """Карточка для человека: персона, бриф, правила ответа, скрытые требования по областям."""
    from reqgraph_evals import human as human_session

    typer.echo(json.dumps(human_session.card(scenario), ensure_ascii=False, indent=2))


@human_app.command("start")
def human_start_cmd(
    scenario: Annotated[str, typer.Argument(help="dev-сценарий")],
    max_turns: Annotated[int, typer.Option(min=1, help="вопросов не больше")] = 30,
    profile: Annotated[str, typer.Option(help="профиль моделей roles.yaml")] = "free",
) -> None:
    """Новая сессия: проект из брифа сценария и первый вопрос интервьюера."""
    from reqgraph_evals import human as human_session

    if scenario.strip().startswith("test"):
        typer.echo("test-сценарии — только в финальной матрице (S6)", err=True)
        raise typer.Exit(2)
    _human_state(asyncio.run(human_session.start(scenario, max_turns=max_turns, profile=profile)))


@human_app.command("answer")
def human_answer_cmd(
    session: Annotated[Path, typer.Argument(help="папка сессии", exists=True, file_okay=False)],
    text_file: Annotated[
        Path, typer.Option(help="ответ человека, UTF-8, как написан", exists=True, dir_okay=False)
    ],
    told: Annotated[str, typer.Option(help="отметки: H-013,H-014 (необязательно)")] = "",
) -> None:
    """Ответ на текущий вопрос; печатает следующий вопрос или итог интервью."""
    from reqgraph_evals import human as human_session

    text = text_file.read_text(encoding="utf-8")
    try:
        state = asyncio.run(human_session.answer(session, text, told.split(",")))
    except (human_session.UnknownMark, ValueError, RuntimeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from None
    _human_state(state)


@human_app.command("finish")
def human_finish_cmd(
    session: Annotated[Path, typer.Argument(help="папка сессии", exists=True, file_okay=False)],
) -> None:
    """Закончить интервью: агенты, проверки, строка CSV и диалог, как у симулятора."""
    from reqgraph_evals import human as human_session

    _human_state(asyncio.run(human_session.finish(session)))


@human_app.command("status")
def human_status_cmd(
    session: Annotated[Path, typer.Argument(help="папка сессии", exists=True, file_okay=False)],
) -> None:
    """Текущий вопрос сессии (после паузы или перезапуска)."""
    from reqgraph_evals import human as human_session

    _human_state(human_session.load(session))
