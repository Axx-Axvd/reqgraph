"""The CI report: stable JSON and Russian Markdown, compared with snapshots (T-105).

Regenerate after an intended change:
  REQGRAPH_UPDATE_GOLDEN=1 uv run pytest packages/core/tests/checks
"""

import asyncio
import json
import os
from pathlib import Path

import pytest
from reqgraph.checks.report import CIReport, plural
from reqgraph.checks.runner import run_checks
from reqgraph.dsl.readers import model_readers
from reqgraph.graph.store import FileStore

from .conftest import SNAPSHOTS, training_registry


def report_of(folder: Path) -> CIReport:
    project = FileStore(folder, readers=model_readers()).load()
    return asyncio.run(run_checks(project, training_registry().checks(), offline=True))


@pytest.mark.parametrize("suffix", ["json", "md"])
def test_report_matches_the_snapshot(garage61: Path, suffix: str) -> None:
    report = report_of(garage61)
    text = report.to_json() if suffix == "json" else report.to_markdown()
    path = SNAPSHOTS / f"garage61.{suffix}"
    if os.environ.get("REQGRAPH_UPDATE_GOLDEN") == "1":
        path.write_bytes(text.encode("utf-8"))
    assert path.read_bytes().decode("utf-8") == text, f"{path.name}: REQGRAPH_UPDATE_GOLDEN=1"


def test_json_round_trip(garage61: Path) -> None:
    report = report_of(garage61)
    assert CIReport.model_validate_json(report.to_json()) == report


def test_json_shape(garage61: Path) -> None:
    data = json.loads(report_of(garage61).to_json())
    assert data["schema_version"] == 1 and data["project"] == "garage61"
    assert set(data["summary"]) == {
        "errors",
        "warnings",
        "infos",
        "passed",
        "failed",
        "warned",
        "skipped",
    }
    assert "generated_at" not in data  # no time: the same project gives the same bytes


def test_markdown_is_readable_russian(garage61: Path) -> None:
    text = report_of(garage61).to_markdown()
    assert text.startswith("# Отчёт проверок: ")
    assert "как исправить" in text and "TRC-900" in text and "Трассировка" in text


def test_empty_report_says_so(garage61: Path) -> None:
    project = FileStore(garage61).load()
    report = asyncio.run(run_checks(project, [], offline=True))
    assert report.ok and "Проверок не запускалось" in report.to_markdown()


@pytest.mark.parametrize(
    ("n", "word"),
    [(1, "ошибка"), (2, "ошибки"), (5, "ошибок"), (11, "ошибок"), (21, "ошибка"), (22, "ошибки")],
)
def test_russian_plural(n: int, word: str) -> None:
    assert plural(n, "ошибка", "ошибки", "ошибок") == f"{n} {word}"
