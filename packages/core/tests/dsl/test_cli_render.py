"""`reqgraph render`: SVG of a model file through Kroki (T-104)."""

from pathlib import Path

import pytest
from reqgraph.cli import app
from typer.testing import CliRunner

from .conftest import GARAGE61


@pytest.fixture(autouse=True)
def private_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQGRAPH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KROKI_URL", "https://kroki.io")


@pytest.mark.vcr
def test_writes_svg(tmp_path: Path) -> None:
    out = tmp_path / "use_cases.svg"
    source = GARAGE61.parent / "uml" / "use_cases.puml"
    result = CliRunner().invoke(app, ["render", str(source), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert "<svg" in out.read_text(encoding="utf-8")


def test_offline_exit_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KROKI_URL", "http://127.0.0.1:9")
    source = tmp_path / "a.puml"
    source.write_text("@startuml\nA -> B\n@enduml\n", encoding="utf-8")
    result = CliRunner().invoke(app, ["render", str(source)])
    assert result.exit_code == 2 and "Kroki" in result.output


def test_unknown_suffix(tmp_path: Path) -> None:
    source = tmp_path / "a.txt"
    source.write_text("x", encoding="utf-8")
    result = CliRunner().invoke(app, ["render", str(source)])
    assert result.exit_code == 1 and ".txt" in result.output
