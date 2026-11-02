"""reqgraph-evals uml (T-207) on stub models: answers, use cases, C4, orphans, roles, CSV."""

import csv
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.models.test import TestModel
from reqgraph_evals.uml import CSV_FIELDS, passed, run_scenario, summary_markdown, write_csv

from .test_modeler_eval import ANALYST, MODELER

pytestmark = pytest.mark.anyio

ACTORS: dict[str, Any] = ANALYST | {
    "actors": [{"ref": "patient", "name": "Пациент", "sources": ["TURN-0001"]}]
}
VIEWS: dict[str, Any] = {
    "use_cases": [{"ref": "uc", "name": "Записаться", "actor": "ACT-01", "realizes": ["FR-001"]}],
    "c4": {
        "system_name": "Запись",
        "containers": [{"ref": "api", "name": "API", "realizes": ["FR-001"]}],
        "externals": [{"ref": "sms", "name": "SMS-шлюз"}],  # realizes nothing: an orphan
        "links": [{"src": "ACT-01", "dst": "api", "label": "Записывается"}],
    },
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_row_counts_views_and_orphans(tmp_path: Path) -> None:
    models = {
        "analyst": TestModel(custom_output_args=ACTORS),
        "modeler": TestModel(custom_output_args=MODELER),
        "modeler_views": TestModel(custom_output_args=VIEWS),
    }
    row = await run_scenario("dev-01", 1, models=models, offline=True)
    assert row.error == "" and row.has_uml and row.has_c4
    assert (row.actors, row.use_cases, row.containers, row.externals) == (1, 1, 1, 1)
    assert row.attempts == 3  # the orphan external system stays in every answer
    assert row.orphans == 1 and row.roles_without_uc == 0
    assert row.sch004 == -1 and row.sch005 == -1  # offline: Kroki is not asked
    assert not passed(row)
    write_csv([row], tmp_path / "u.csv")
    with (tmp_path / "u.csv").open(encoding="utf-8") as fh:
        assert list(next(csv.DictReader(fh))) == CSV_FIELDS
    assert "выполнен: нет" in summary_markdown([row])
