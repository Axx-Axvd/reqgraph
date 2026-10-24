"""reqgraph-evals modeler (T-203) on stub models: attempts, processes, SND-001 share, CSV."""

import csv
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.models.test import TestModel
from reqgraph_evals.modeler import CSV_FIELDS, run_scenario, summary_markdown, write_csv

pytestmark = pytest.mark.anyio

ANALYST: dict[str, Any] = {
    "requirements": [
        {
            "ref": "br",
            "kind": "BR",
            "title": "Цель",
            "statement": "Доля онлайн-записей 50%.",
            "sources": ["TURN-0001"],
        },
        {
            "ref": "ur",
            "kind": "UR",
            "title": "Запись",
            "statement": "Пациент записывается.",
            "refines": ["br"],
            "sources": ["TURN-0002"],
        },
        {
            "ref": "fr",
            "kind": "FR",
            "title": "Слоты",
            "statement": "Система должна показать слоты.",
            "acceptance": ["слоты на 14 дней"],
            "refines": ["ur"],
            "sources": ["TURN-0002"],
        },
    ]
}
MODELER: dict[str, Any] = {
    "processes": [
        {
            "ref": "p",
            "name": "Запись",
            "refines": ["UR-001"],
            "nodes": [
                {"id": "S", "type": "start", "name": "Пациент открыл сайт"},
                {
                    "id": "T01",
                    "type": "service_task",
                    "name": "Показать слоты",
                    "realizes": ["FR-001"],
                },
                {"id": "T02", "type": "task", "name": "Шаг в никуда", "realizes": ["FR-001"]},
                {"id": "E1", "type": "end", "name": "Готово"},
            ],
            "flows": [{"src": "S", "dst": "T01"}, {"src": "T01", "dst": "E1"}],
        }
    ],
    "entities": [
        {
            "ref": "e",
            "name": "Слот",
            "table": "slot",
            "columns": [{"name": "id", "type": "int", "pk": True}],
        }
    ],
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def models() -> dict[str, Any]:
    return {
        "analyst": TestModel(custom_output_args=ANALYST),
        "modeler": TestModel(custom_output_args=MODELER),
    }


async def test_row_counts_attempts_and_unreachable_processes(tmp_path: Path) -> None:
    row = await run_scenario("dev-01", 1, models=models())
    assert row.error == "" and row.applied
    assert row.attempts == 3  # T02 is never reached: three answers, the best one applied
    assert (row.processes, row.tasks, row.entities) == (1, 2, 1)
    assert row.snd001_processes == 1 and row.reachable_share == 0.0
    write_csv([row], tmp_path / "m.csv")
    with (tmp_path / "m.csv").open(encoding="utf-8") as fh:
        assert list(next(csv.DictReader(fh))) == CSV_FIELDS
    summary = summary_markdown([row])
    assert "без SND-001: 0 (0%)" in summary and "выполнен: нет" in summary
