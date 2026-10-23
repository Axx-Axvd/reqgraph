"""Training checks for the framework (T-105): the real ones come in T-106, T-107, T-404.

Ids with 9xx are reserved for tests and never used by real checks.
"""

import shutil
from pathlib import Path

import pytest
from reqgraph.checks.base import BaseCheck, CheckContext, CheckSkipped, Finding
from reqgraph.checks.registry import Registry
from reqgraph.graph import ArtifactGraph

GARAGE61 = Path(__file__).resolve().parents[4] / "examples" / "garage61"
SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"


class MustPriority(BaseCheck):
    id = "TRC-900"
    title = "у ФТ приоритет must"
    group = "trc"
    owner = "analyst"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        return [
            self.finding(
                "error",
                [fr.id],
                f"{fr.id}: приоритет {fr.priority}, а не must",  # type: ignore[union-attr]
                hint="поднимите приоритет или уберите требование из первой версии",
            )
            for fr in graph.nodes_of("FR")
            if fr.priority != "must"  # type: ignore[union-attr]
        ]


class ShortStatements(BaseCheck):
    id = "ISO-900"
    title = "формулировки короче 120 символов"
    group = "iso"
    owner = "analyst"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        return [
            self.finding("warning", [n.id], f"{n.id}: формулировка длиннее 120 символов")
            for n in graph.nodes_of("FR")
            if len(n.statement) > 120  # type: ignore[union-attr]
        ]


class DrawsUseCases(BaseCheck):
    id = "SCH-900"
    title = "сценарии использования рисуются"
    group = "sch"
    owner = "modeler"

    async def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        result = await ctx.svg("models/uml/use_cases.puml")
        if result.offline:
            raise CheckSkipped("Kroki недоступен — проверка без сети")
        return [] if result.ok else [self.finding("error", [], str(result.error))]


class Crashes(BaseCheck):
    id = "TPL-900"
    title = "проверка с ошибкой в коде"
    group = "tpl"
    owner = "standards"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        raise RuntimeError("деление на ноль в шаблоне")


class AlwaysGreen(BaseCheck):
    id = "SND-900"
    title = "у процессов есть имя"
    group = "snd"
    owner = "modeler"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        return [self.finding("info", [p.id], f"{p.id}: имя есть") for p in graph.nodes_of("PRC")]


def training_registry() -> Registry:
    registry = Registry()
    for check in (MustPriority, ShortStatements, DrawsUseCases, Crashes, AlwaysGreen):
        registry.register(check)
    return registry


@pytest.fixture
def garage61(tmp_path: Path) -> Path:
    """A copy: `reqgraph check` writes reports/ into the project, the reference stays untouched."""
    return Path(shutil.copytree(GARAGE61, tmp_path / "garage61"))
