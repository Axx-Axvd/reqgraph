"""Edge cases of SCH-* and SND-* that a mutation of garage61 does not reach (T-106)."""

import asyncio
import shutil
from pathlib import Path

import pytest
from reqgraph.checks import base, schema
from reqgraph.checks.base import CheckContext, CheckSkipped
from reqgraph.checks.schema import BpmnXsd, PlantUmlCompiles, StructurizrCompiles
from reqgraph.checks.sound import Gateways, Reachable
from reqgraph.dsl.kroki import RenderResult
from reqgraph.dsl.readers import model_readers
from reqgraph.graph.store import FileStore

from .conftest import GARAGE61


def context(folder: Path = GARAGE61, offline: bool = False) -> CheckContext:
    return CheckContext(FileStore(folder, readers=model_readers()).load(), offline=offline)


def with_process(tmp_path: Path, dsl: str) -> CheckContext:
    folder = Path(shutil.copytree(GARAGE61, tmp_path / "garage61"))
    (folder / "models/processes/PRC-93.process.json").write_text(dsl, encoding="utf-8")
    return context(folder)


def test_sch001_reports_xsd_errors_of_the_compiler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schema, "validate_bpmn", lambda xml: ["строка 3: что-то не так"])
    found = BpmnXsd().run(context().project.graph, context())
    assert {f.node_ids[0] for f in found} == {"PRC-01", "PRC-02"}
    assert "строка 3" in found[0].message


def test_kroki_compile_error_names_the_file(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(kind: str, source: str) -> RenderResult:
        if kind == "structurizr":
            return RenderResult(error='Error 400: element "b" does not exist at line 4')
        return RenderResult(svg="<svg/>")

    monkeypatch.setattr(base, "render_svg", fake)
    ctx = context()
    assert asyncio.run(PlantUmlCompiles().run(ctx.project.graph, ctx)) == []
    (found,) = asyncio.run(StructurizrCompiles().run(ctx.project.graph, ctx))
    assert "workspace.dsl" in found.message and "line 4" in found.message


def test_kroki_offline_skips_the_check() -> None:
    ctx = context(offline=True)
    with pytest.raises(CheckSkipped, match="Kroki"):
        asyncio.run(PlantUmlCompiles().run(ctx.project.graph, ctx))


def test_process_without_end(tmp_path: Path) -> None:
    ctx = with_process(
        tmp_path,
        '{"id": "PRC-93", "name": "x", "nodes": [{"id": "S", "type": "start"}, '
        '{"id": "T", "type": "task"}], "flows": [["S", "T"]]}',
    )
    found = [f for f in Reachable().run(ctx.project.graph, ctx) if f.node_ids == ["PRC-93"]]
    assert found and "конечного" in found[0].message


def test_gateway_that_does_nothing_and_wrong_event_gateway(tmp_path: Path) -> None:
    ctx = with_process(
        tmp_path,
        '{"id": "PRC-93", "name": "x", "nodes": [{"id": "S", "type": "start"}, '
        '{"id": "G01", "type": "xor"}, {"id": "G02", "type": "event_based"}, '
        '{"id": "T", "type": "task"}, {"id": "E", "type": "end"}], '
        '"flows": [["S", "G01"], ["G01", "G02"], ["G02", "T"], ["T", "E"]]}',
    )
    messages = {f.node_ids[0]: f.message for f in Gateways().run(ctx.project.graph, ctx)}
    assert "ничего не разветвляет" in messages["PRC-93.G01"]
    assert "событийного шлюза" in messages["PRC-93.G02"]
