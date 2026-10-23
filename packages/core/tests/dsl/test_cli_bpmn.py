"""`reqgraph bpmn`: compile a process file for Camunda Modeler or bpmn-js (T-103)."""

from pathlib import Path

from reqgraph.cli import app
from typer.testing import CliRunner

from .conftest import FIXTURES, GARAGE61


def test_writes_a_valid_file(tmp_path: Path) -> None:
    out = tmp_path / "PRC-01.bpmn"
    result = CliRunner().invoke(
        app, ["bpmn", str(GARAGE61 / "PRC-01_booking.process.json"), "-o", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.read_text(encoding="utf-8").startswith("<?xml")


def test_prints_to_stdout_without_out() -> None:
    result = CliRunner().invoke(app, ["bpmn", str(FIXTURES / "linear.process.json")])
    assert result.exit_code == 0 and "PRC-11.T01" in result.output


def test_bad_dsl_exits_with_a_message(tmp_path: Path) -> None:
    bad = tmp_path / "bad.process.json"
    bad.write_text('{"dsl_version": 1, "id": "PRC-01", "name": "x", "nodes": []}', encoding="utf-8")
    result = CliRunner().invoke(app, ["bpmn", str(bad)])
    assert result.exit_code == 1 and "nodes" in result.output
