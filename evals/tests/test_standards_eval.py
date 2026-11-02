"""reqgraph-evals standards (T-204) on stub models: filled share of the required SRS sections."""

from typing import Any

import pytest
from pydantic_ai.models.test import TestModel
from reqgraph_evals.standards import run_scenario, summary_markdown

from .test_modeler_eval import ANALYST, MODELER

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_row_counts_empty_required_sections() -> None:
    srs: dict[str, Any] = {
        "purpose": "Назначение.",
        "scope": "Область.",
        "perspective": "Новая система.",
        "glossary": [],
    }
    models = {
        "analyst": TestModel(custom_output_args=ANALYST),
        "modeler": TestModel(custom_output_args=MODELER),
        "standards": TestModel(custom_output_args=srs),
    }
    row = await run_scenario("dev-01", 1, models=models)
    assert row.error == "" and row.sections == 32 and row.required == 10
    assert row.retried  # an empty glossary is asked again
    # empty: glossary (the stub repeats itself) and actors (the stub Analyst wrote none);
    # NFR sections are not required in the structure after Wiegers (T-408)
    assert row.empty_required == 2 and row.filled_share == 0.8
    assert "заполнено: 8 (80%)" in summary_markdown([row]) and ": да." in summary_markdown([row])
