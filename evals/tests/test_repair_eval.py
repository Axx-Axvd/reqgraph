"""reqgraph-evals repair (T-205) on stub models: the loop stops with needs_human; row, summary."""

import json
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from reqgraph_evals.repair import run_scenario, summary_markdown

from .test_modeler_eval import ANALYST, MODELER

pytestmark = pytest.mark.anyio


def first_then_nothing(answer: dict[str, Any]) -> FunctionModel:
    calls: list[int] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(1)
        data = answer if len(calls) == 1 else {"requirements": []}
        return ModelResponse(parts=[TextPart(json.dumps(data, ensure_ascii=False))])

    return FunctionModel(fn)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.parametrize("reviewer", ["llm", "template"])
async def test_stub_agents_that_never_fix_stop_with_needs_human(reviewer: str) -> None:
    srs: dict[str, Any] = {
        "purpose": "Назначение.",
        "scope": "Область.",
        "glossary": [{"term": "a", "definition": "b"}],
    }
    models = {
        "analyst": first_then_nothing(ANALYST),  # repair rounds change nothing
        "modeler": TestModel(custom_output_args=MODELER),  # T02 is never reached: SND-001 stays
        "standards": TestModel(custom_output_args=srs),
        "reviewer": TestModel(custom_output_args={"tasks": []}),
    }
    row = await run_scenario("dev-01", 1, models=models, reviewer=reviewer)  # type: ignore[arg-type]
    assert row.error == "" and row.stop == "needs_human" and not row.converged
    assert row.errors_final > 0 and row.iterations <= 5
    assert ("reviewer=" in row.models) is (reviewer == "llm")
    assert "остановились с needs_human: 1" in summary_markdown([row])
