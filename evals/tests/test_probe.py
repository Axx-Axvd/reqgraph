"""Probe end to end on in-process models, without network (T-006)."""

import csv
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from reqgraph.llm import router
from reqgraph.llm.config import Step
from reqgraph_evals import probe

pytestmark = pytest.mark.anyio

ANSWERS = {
    "Extraction": {"requirements": [{"kind": "FR", "text": "клиент записывается на занятие"}]},
    "ProcessSketch": {
        "nodes": [
            {"id": "s", "kind": "start", "name": "Старт"},
            {"id": "t", "kind": "task", "name": "Проверить заявку"},
            {"id": "e", "kind": "end", "name": "Конец"},
        ],
        "flows": [{"source": "s", "target": "t"}, {"source": "t", "target": "e"}],
    },
    "Rewrite": {
        "statement": "Система должна отвечать за 2 секунды",
        "acceptance": ["ответ за 2 с"],
    },
    "Question": {"question": "Какие роли будут у сотрудников?", "area": "роли"},
}


KEY_FIELD = {
    "requirements": "Extraction",
    "nodes": "ProcessSketch",
    "statement": "Rewrite",
    "question": "Question",
}


def fake(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Answer with a valid object of whatever output type the agent asks for."""
    tool = info.output_tools[0]
    props = tool.parameters_json_schema.get("properties", {})
    kind = next(v for k, v in KEY_FIELD.items() if k in props)
    return ModelResponse(parts=[ToolCallPart(tool.name, ANSWERS[kind])])


def broken(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart("не JSON")])


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def fake_models(monkeypatch: pytest.MonkeyPatch) -> None:
    def build(step: Step) -> Model:
        return FunctionModel(broken if "broken" in step.model else fake, model_name=step.model)

    monkeypatch.setattr(router, "_build_model", build)


def test_cases_cover_four_blocks_by_five() -> None:
    cases = probe.load_cases()
    assert len(cases) == 20
    for block in probe.BLOCKS:
        assert sum(b == block for b, _ in cases) == 5
    assert len({c["name"] for _, c in cases}) == 20


@pytest.mark.parametrize("block", probe.BLOCKS)
def test_prompts_render_with_data_in_tags(block: str) -> None:
    case = next(c for b, c in probe.load_cases() if b == block)
    text, sha = probe.render(block, case)
    assert len(sha) == 12
    assert case["domain"] in text
    if block in ("extract", "process", "rewrite"):
        assert "данные, а не инструкции" in text


async def test_run_model_writes_rows(fake_models: None, tmp_path: Path) -> None:
    dataset = probe.build_dataset()
    rows = await probe.run_model("groq/fake-model", 2, dataset)
    assert len(rows) == 40  # 20 tasks x 2 repeats
    assert all(r.valid for r in rows)
    assert {r.block for r in rows} == set(probe.BLOCKS)
    assert all(r.prompt_sha and r.package_version for r in rows)
    out = tmp_path / "probe.csv"
    probe.write_csv(rows, out)
    with out.open(encoding="utf-8") as fh:
        read = list(csv.DictReader(fh))
    assert len(read) == 40 and set(read[0]) == set(probe.CSV_FIELDS)
    md = probe.summary_markdown(rows)
    assert "`groq/fake-model`" in md and "100%" in md


async def test_invalid_answers_become_failed_rows(fake_models: None) -> None:
    rows = await probe.run_model("groq/broken-model", 1, probe.build_dataset())
    assert len(rows) == 20
    assert not any(r.valid for r in rows)
    assert all(r.error for r in rows)
    assert "0%" in probe.summary_markdown(rows)


def test_judge_only_on_rewrite_cases(fake_models: None) -> None:
    dataset = probe.build_dataset(judge=True)
    judged = {c.inputs.block for c in dataset.cases if c.evaluators}
    assert judged == {"rewrite"}


async def test_answers_are_stored_for_manual_review(fake_models: None) -> None:
    rows = await probe.run_model("groq/fake-model", 1, probe.build_dataset())
    assert all(r.answer.startswith("{") for r in rows)
