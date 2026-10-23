"""`reqgraph check`: exit codes 0/1/2, reports in reports/, --no-write, --json (T-105)."""

import json
from pathlib import Path

import pytest
from reqgraph.checks import runner
from reqgraph.cli import app
from typer.testing import CliRunner

from .conftest import training_registry


@pytest.fixture
def training(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "all_checks", lambda: training_registry().checks())


def test_errors_give_exit_code_1_and_reports(garage61: Path, training: None) -> None:
    result = CliRunner().invoke(app, ["check", str(garage61), "--offline"])
    assert result.exit_code == 1, result.output
    assert "ошиб" in result.output
    data = json.loads((garage61 / "reports" / "ci-report.json").read_text(encoding="utf-8"))
    assert data["summary"]["errors"] > 0
    assert (garage61 / "reports" / "ci-report.md").read_text(encoding="utf-8").startswith("# ")


def test_no_errors_give_exit_code_0(garage61: Path) -> None:
    result = CliRunner().invoke(app, ["check", str(garage61), "--offline"])
    assert result.exit_code == 0, result.output


def test_no_write_leaves_the_project_untouched(garage61: Path, training: None) -> None:
    result = CliRunner().invoke(app, ["check", str(garage61), "--offline", "--no-write"])
    assert result.exit_code == 1
    assert not (garage61 / "reports" / "ci-report.json").exists()


def test_json_output(garage61: Path, training: None) -> None:
    result = CliRunner().invoke(app, ["check", str(garage61), "--offline", "--no-write", "--json"])
    assert json.loads(result.output)["project"] == "garage61"


def test_unreadable_project_gives_exit_code_2(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["check", str(tmp_path)])
    assert result.exit_code == 2 and "reqgraph.yaml" in result.output
