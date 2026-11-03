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
            "realizes": ["FR-001"],
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
