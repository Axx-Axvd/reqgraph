"""reqgraph-evals interview (T-302) on stub models: the row, the dialog file, the CSV."""

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from reqgraph_evals.interview import CSV_FIELDS, run_interview, summary_markdown, write_csv

pytestmark = pytest.mark.anyio

QUESTION = "Как пациент отменяет запись?"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def simulator(ids: list[str]) -> FunctionModel:
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompt = str(messages[-1].parts[-1].content)  # type: ignore[union-attr]
        data: dict[str, Any] = (
            {"ids": ids} if "только выбрать" in prompt else {"text": "Не позже чем за 3 часа."}
        )
        return ModelResponse(parts=[TextPart(json.dumps(data, ensure_ascii=False))])

    return FunctionModel(fn)


def agents() -> dict[str, Any]:
    srs = {"purpose": "П.", "scope": "О.", "glossary": [{"term": "a", "definition": "b"}]}
    return {
        "*": TestModel(custom_output_args={"ops": []}),
        "analyst": TestModel(custom_output_args={"requirements": []}),
        "interviewer": TestModel(custom_output_args={"text": QUESTION, "area": "exceptions"}),
        "standards": TestModel(custom_output_args=srs),
    }


async def test_a_dialog_with_the_simulator_is_recorded(tmp_path: Path) -> None:
    row = await run_interview(
        "dev-01",
        "cooperative",
        1,
        max_turns=2,
        max_iter=0,
        models=agents(),
        sim_model=simulator(["H-013", "H-404"]),
        dialogs=tmp_path / "dialogs",
        keep=tmp_path / "runs",
    )
    assert row.error == "" and row.turns == 2 and row.end == "limit"
    assert (row.revealed, row.hidden) == (1, 20)  # H-013 once; 5 of 25 are in the brief
    assert row.off_topic == 0  # H-013 is about exceptions, as the question
    assert row.empty == 1  # the second answer only repeats H-013
    assert "stakeholder=function/" in row.models and "interviewer=test/test" in row.models
    assert row.sim_temperature == 0.7 and row.seed == 43  # roles.yaml seed + the repeat
    assert "interviewer/ask=" in row.prompt_hashes
    dialog = (tmp_path / "dialogs" / "dev-01-cooperative-r1.md").read_text(encoding="utf-8")
    assert f"**Интервьюер:** {QUESTION}" in dialog and "H-013 (exceptions) — рассказал" in dialog
    assert "## Не рассказано" in dialog and "H-001 (goals)" in dialog
    assert (tmp_path / "runs" / "dev-01-cooperative-r1" / "reqgraph.yaml").is_file()
    assert not (tmp_path / "runs" / "dev-01-cooperative-r1" / ".reqgraph").exists()

    write_csv([row], tmp_path / "interview.csv")
    with (tmp_path / "interview.csv").open(encoding="utf-8") as fh:
        assert next(iter(csv.DictReader(fh))).keys() == set(CSV_FIELDS)
    assert "| dev-01 | cooperative | 1 | 2 | limit | 1/20 (5%) | 1 |" in summary_markdown([row])


async def test_test_scenarios_stay_sealed() -> None:
    from reqgraph_evals.scenario import SealedScenario

    with pytest.raises(SealedScenario):
        await run_interview("test-01", "vague", 1, models=agents(), sim_model=simulator([]))
