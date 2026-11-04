"""The methods of the matrix (T-405): B1 one-shot, B2 without checks, B3 the questionnaire,
A1-A3 the ablations of M2 — on stub models, with the same inputs, model and budget."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.embeddings import TestEmbeddingModel
from pydantic_ai.models.test import TestModel
from reqgraph.agents.nodes import questionnaire
from reqgraph_evals.metrics import harness

from .test_interview_eval import agents, simulator
from .test_metrics import judge_first

pytestmark = pytest.mark.anyio

ONE_SHOT: dict[str, Any] = {
    "requirements": [
        {
            "ref": "fr_cancel",
            "kind": "FR",
            "title": "Отмена",
            "statement": "Система должна позволять отменить запись за 3 часа.",
            "acceptance": ["отмена позже 3 часов недоступна"],
            "sources": ["TURN-0002"],
        }
    ],
    "entities": [
        {
            "ref": "ent_visit",
            "name": "Запись",
            "table": "visit",
            "columns": [{"name": "id", "type": "int", "pk": True}],
            "realizes": ["fr_cancel"],  # one answer: the models name requirements by their ref
        }
    ],
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_every_method_differs_only_in_its_switches() -> None:
    m = harness.METHODS
    assert set(m) == {"M2", "M1", "B1", "B2", "B3", "A1", "A2", "A3"}
    assert m["B2"].self_checks is False and m["B2"].max_iter == 0 and m["B2"].interviewer == "free"
    assert m["B3"].interviewer == "questionnaire" and m["B1"].one_shot
    assert m["A1"].max_iter == 0 and m["A3"].reviewer == "template"
    assert m["A2"].disabled == harness.TRC and m["M2"] == harness.MethodOptions("coverage")


async def test_the_matrix_runs_every_method_with_the_same_inputs(tmp_path: Path) -> None:
    models = agents() | {"analyst": TestModel(custom_output_args=ONE_SHOT)}
    cases = [harness.RunInputs("dev-01", "cooperative", m) for m in ("B1", "B3", "B2", "M1")]
    task = harness.run_task(
        max_turns=2,
        runs=tmp_path / "runs",
        dialogs=tmp_path / "dialogs",
        models=models,
        sim_model=simulator(["H-013"]),
    )
    results, _ = await harness.evaluate(
        cases, task, judge_model=judge_first(), embedder=TestEmbeddingModel()
    )
    by = {r.method: r for r in results}
    assert [r.method for r in results] == ["M1", "B1", "B2", "B3"]  # M1 first: B1 reads it
    assert {r.error for r in results} == {""}
    assert len({r.seed for r in results}) == 1  # the same simulator seed for every method
    assert by["B3"].turns == len(questionnaire()) and by["M1"].turns == by["B2"].turns == 2
    assert by["B1"].turns == by["M1"].turns and by["B1"].llm_calls >= 1
    assert by["B1"].requirements >= 1 and "analyst=test/" in by["B1"].models
    kept = tmp_path / "runs" / "B1" / "dev-01-cooperative-r1"
    turns = json.dumps(sorted(p.name for p in kept.rglob("*")))
    assert "erd.dbml" in turns  # the one-shot entities are built into the ERD by code
    answer = json.loads((kept / "reports" / "oneshot.json").read_text(encoding="utf-8"))
    assert answer["answer"] == {"actors": 0, "requirements": 1, "processes": 0, "entities": 1}
    assert answer["dropped"] == []
    dialogs = sorted(
        p.relative_to(tmp_path / "dialogs").as_posix() for p in (tmp_path / "dialogs").rglob("*.md")
    )
    assert dialogs == [
        f"{m}/dev-01-cooperative-r1.md" for m in ("B2", "B3", "M1")
    ]  # one per method


async def test_b1_without_its_m1_run_is_a_row_with_the_error(tmp_path: Path) -> None:
    from reqgraph_evals.oneshot import run_one_shot

    row = await run_one_shot("dev-01", "cooperative", 1, source=tmp_path / "none")
    assert row.error.startswith("B1 нужен прогон M1") and row.method == "B1"


async def test_the_run_stops_starting_cases_once_the_dollar_limit_is_spent(tmp_path: Path) -> None:
    """T-406: a case that would start past the limit is a row with the reason, not a silent gap."""
    inner = harness.run_task(
        max_turns=2, runs=tmp_path / "runs", models=agents(), sim_model=simulator(["H-013"])
    )

    async def priced(inputs: harness.RunInputs) -> harness.RunOutput:
        out = await inner(inputs)
        out.row.cost_usd = 0.02  # the stub models cost nothing
        return out

    cases = [harness.RunInputs("dev-01", "cooperative", "M2", r) for r in (1, 2, 3)]
    results, _ = await harness.evaluate(
        cases, priced, judge_model=judge_first(), embedder=TestEmbeddingModel(), max_usd=0.03
    )
    done = [r for r in results if not r.error]
    skipped = [r for r in results if r.error]
    assert len(done) == 2  # 0.02 spent < 0.03: the second starts, then 0.04 stops the third
    assert [r.repeat for r in skipped] == [3]
    assert skipped[0].error == "лимит $ запуска исчерпан: потрачено $0.0400 из $0.0300"
    assert skipped[0].llm_calls == 0 and skipped[0].cost_usd == 0


def test_the_summary_averages_each_method_and_draws_charts() -> None:
    def result(method: str, recall: float, usd: float, error: str = "") -> harness.Result:
        return harness.Result(
            f"dev-01-cooperative-{method}",
            "dev-01",
            "cooperative",
            method,
            1,
            recall=recall,
            recall_partial=recall,
            requirements=10,
            cost_usd=usd,
            error=error,
        )

    results = [
        result("M1", 0.4, 0.02),
        result("M2", 0.8, 0.02),
        result("M2", 0.6, 0.02),
        result("B3", 0.0, 0.01, error="ModelRateLimitError: 429"),
    ]
    text = harness.summary_markdown(results)
    assert "| M2 | 2 | 2 | 70% | 70% | 10.0 | 0.0 | 0.0400 | 0.0 |" in text
    assert "| B3 | 1 | 0 | — | — | — | — | 0.0100 | 0.0 |" in text
    chart = text[text.index("```mermaid") :]
    assert 'x-axis ["M2", "M1"]' in chart and "bar [70, 40]" in chart  # the order of METHODS
    assert 'x-axis ["M2", "M1", "B3"]' in chart  # money: every method that spent it


def test_the_matrix_refuses_test_scenarios_and_a_limit_over_5_dollars() -> None:
    from reqgraph_evals.cli import app
    from typer.testing import CliRunner

    refused = CliRunner().invoke(app, ["matrix", "--scenarios", "test-01"])
    assert refused.exit_code == 2 and "только в финальной матрице (S6)" in refused.output
    costly = CliRunner().invoke(app, ["matrix", "--scenarios", "dev-01", "--max-usd", "6"])
    assert costly.exit_code == 2 and "--allow-over-5" in costly.output


async def test_a_stopped_matrix_goes_on_from_its_progress_file(tmp_path: Path) -> None:
    """T-406: a case is written to the progress file as soon as it is scored; a new run with the
    same file skips the cases it has and runs the rest."""
    calls: list[str] = []
    inner = harness.run_task(
        max_turns=2, runs=tmp_path / "runs", models=agents(), sim_model=simulator(["H-013"])
    )

    async def counted(inputs: harness.RunInputs) -> harness.RunOutput:
        calls.append(inputs.name)
        return await inner(inputs)

    progress = tmp_path / "results.progress.jsonl"
    first = [harness.RunInputs("dev-01", "cooperative", "M2", 1)]
    both = [*first, harness.RunInputs("dev-01", "cooperative", "M2", 2)]
    scoring = {"judge_model": judge_first(), "embedder": TestEmbeddingModel()}
    _, first_pairs = await harness.evaluate(first, counted, progress=progress, **scoring)
    assert len(progress.read_text(encoding="utf-8").splitlines()) == 1
    results, pairs = await harness.evaluate(both, counted, progress=progress, **scoring)
    assert calls == ["dev-01-cooperative-M2-r1", "dev-01-cooperative-M2-r2"]  # r1 not run again
    assert [r.repeat for r in results] == [1, 2] and all(not r.error for r in results)
    assert [p for p in pairs if p["run"].endswith("-r1")] == first_pairs  # kept with the case


def test_the_progress_file_keeps_a_result_with_its_judged_pairs(tmp_path: Path) -> None:
    path = tmp_path / "p.jsonl"
    result = harness.Result("dev-01-vague-M1-r1", "dev-01", "vague", "M1", 1, recall=0.4, turns=7)
    pair = {"run": result.run, "hidden_id": "H-013", "judge": True, "level": "full"}
    harness._write_progress(path, result, [pair])
    assert harness._read_progress(path) == {result.run: (result, [pair])}


async def test_a_case_that_failed_runs_again_on_resume(tmp_path: Path) -> None:
    """A free model out of quota fails a case; the resumed run tries it again, not skips it."""
    progress = tmp_path / "p.jsonl"
    failed = harness.Result(
        "dev-01-cooperative-M2-r1", "dev-01", "cooperative", "M2", 1, error="429"
    )
    harness._write_progress(progress, failed, [])
    calls: list[str] = []
    inner = harness.run_task(
        max_turns=2, runs=tmp_path / "runs", models=agents(), sim_model=simulator(["H-013"])
    )

    async def counted(inputs: harness.RunInputs) -> harness.RunOutput:
        calls.append(inputs.name)
        return await inner(inputs)

    results, _ = await harness.evaluate(
        [harness.RunInputs("dev-01", "cooperative", "M2", 1)],
        counted,
        progress=progress,
        judge_model=judge_first(),
        embedder=TestEmbeddingModel(),
    )
    assert calls == ["dev-01-cooperative-M2-r1"] and results[0].error == ""
    assert harness._read_progress(progress)[failed.run][0].error == ""  # the later line wins
