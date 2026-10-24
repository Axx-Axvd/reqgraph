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
    srs: dict[str, Any] = {"purpose": "Назначение.", "scope": "Область.", "glossary": []}
    models = {
        "analyst": TestModel(custom_output_args=ANALYST),
        "modeler": TestModel(custom_output_args=MODELER),
        "standards": TestModel(custom_output_args=srs),
    }
    row = await run_scenario("dev-01", 1, models=models)
    assert row.error == "" and row.sections == 15 and row.required == 10
    assert row.retried  # an empty glossary is asked again
    # empty: glossary (the stub repeats itself), actors and NFR (the stub Analyst wrote none)
    assert row.empty_required == 3 and row.filled_share == 0.7
    assert "заполнено: 7 (70%)" in summary_markdown([row]) and ": нет." in summary_markdown([row])
