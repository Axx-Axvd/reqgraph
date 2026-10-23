"""CheckContext: models parsed once for all checks, errors kept, Kroki behind one call (T-105)."""

import asyncio
import shutil
from pathlib import Path

import pytest
from reqgraph.checks import base
from reqgraph.checks.base import CheckContext
from reqgraph.dsl.dbml import DataModel
from reqgraph.dsl.kroki import RenderResult
from reqgraph.dsl.process import DslError, ProcessDSL
from reqgraph.dsl.readers import model_readers
from reqgraph.graph.store import FileStore, StoreError

from .conftest import GARAGE61


def context(folder: Path, offline: bool = False) -> CheckContext:
    return CheckContext(FileStore(folder, readers=model_readers()).load(), offline=offline)


def test_processes_and_data_model_of_the_reference() -> None:
    ctx = context(GARAGE61)
    processes = ctx.processes()
    assert set(processes) == {"PRC-01", "PRC-02"}
    assert all(isinstance(p, ProcessDSL) for p in processes.values())
    assert ctx.processes() is processes  # parsed once
    model = ctx.data_model()
    assert isinstance(model, DataModel) and len(model.tables) == 8
    assert list(ctx.model_files(".puml")) == [
        "models/uml/seq_booking.puml",
        "models/uml/use_cases.puml",
    ]


def test_broken_process_is_kept_as_its_error(tmp_path: Path) -> None:
    folder = Path(shutil.copytree(GARAGE61, tmp_path / "garage61"))
    path = folder / "models/processes/PRC-02_reminder.process.json"
    path.write_text(path.read_text(encoding="utf-8").replace('"T02"', '"T99"', 1), encoding="utf-8")
    processes = context(folder).processes()
    assert isinstance(processes["PRC-02"], DslError) and "T99" not in str(processes["PRC-01"])


def test_project_without_erd(tmp_path: Path) -> None:
    folder = Path(shutil.copytree(GARAGE61, tmp_path / "garage61"))
    (folder / "models/data/erd.dbml").unlink()
    store = FileStore(folder, readers=model_readers())
    with pytest.raises(StoreError, match="ENT-"):  # requirements point to entities of the ERD
        store.load()


def test_broken_erd_is_kept_as_its_error() -> None:
    ctx = context(GARAGE61)
    ctx.project.files["models/data/erd.dbml"] = "Table a {\n  id int [pk\n}\n"
    assert isinstance(ctx.data_model(), DslError)


def test_svg_goes_to_kroki_by_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake(kind: str, source: str) -> RenderResult:
        calls.append(kind)
        return RenderResult(svg="<svg/>")

    monkeypatch.setattr(base, "render_svg", fake)
    result = asyncio.run(context(GARAGE61).svg("models/c4/workspace.dsl"))
    assert result.ok and calls == ["structurizr"]


def test_svg_offline_does_not_call_kroki(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail(kind: str, source: str) -> RenderResult:
        raise AssertionError("no network in --offline")

    monkeypatch.setattr(base, "render_svg", fail)
    result = asyncio.run(context(GARAGE61, offline=True).svg("models/uml/use_cases.puml"))
    assert result.offline
