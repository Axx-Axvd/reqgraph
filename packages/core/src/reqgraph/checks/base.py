"""What a check is and what it finds (05_ci «Интерфейс проверки»). Checks are deterministic and
never call an LLM (ADR-006); a check sees the graph and the project through CheckContext."""

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Awaitable
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from reqgraph.dsl.dbml import DataModel, parse_dbml
from reqgraph.dsl.kroki import KIND_BY_SUFFIX, RenderResult, render_svg
from reqgraph.dsl.process import DslError, ProcessDSL, parse_process
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import ProcessNode
from reqgraph.graph.store.project import Project

Severity = Literal["error", "warning", "info"]
Owner = Literal["analyst", "modeler", "standards"]
Group = Literal["sch", "snd", "iso", "trc", "tpl"]
CHECK_ID = r"^(SCH|SND|ISO|TRC|TPL)-\d{3}$"
GROUP_ORDER: dict[str, int] = {"sch": 0, "snd": 1, "iso": 2, "trc": 3, "tpl": 4}  # as in 05_ci
GROUP_TITLES: dict[str, str] = {
    "sch": "Схемы моделей",
    "snd": "Корректность процессов",
    "iso": "Качество требований (ISO/IEC/IEEE 29148)",
    "trc": "Трассировка",
    "tpl": "Разделы документов",
}


class Finding(BaseModel):
    """One problem: which check, how serious, which nodes, what to do and who fixes it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    check_id: str = Field(pattern=CHECK_ID)
    severity: Severity
    node_ids: list[str] = []
    message: str = Field(min_length=1)  # in Russian, names the nodes
    hint: str | None = None  # how to fix it, for the Reviewer
    owner: Owner

    @property
    def fingerprint(self) -> str:
        """Check and nodes, not the text: the repeat detector of the repair loop (S2)."""
        key = f"{self.check_id}|{','.join(sorted(self.node_ids))}"
        return hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()


class CheckSkipped(Exception):
    """Raised by a check that cannot run now (no network for Kroki): skipped, not failed."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class CheckContext:
    """The project around the graph, with models parsed once and shared by all checks."""

    project: Project
    offline: bool = False  # --offline: checks that need Kroki are skipped
    _processes: dict[str, ProcessDSL | DslError] | None = field(default=None, repr=False)
    _data_model: DataModel | DslError | None = field(default=None, repr=False)

    def model_files(self, suffix: str) -> dict[str, str]:
        """Texts of the project's model files with this suffix, by relative path."""
        return {
            rel: text
            for rel, text in sorted(self.project.files.items())
            if rel.startswith("models/") and Path(rel).suffix == suffix
        }

    def processes(self) -> dict[str, ProcessDSL | DslError]:
        """DSL of every process node, or the error that stops it from parsing (SCH-002)."""
        if self._processes is None:
            self._processes = {}
            for node in self.project.graph.nodes_of("PRC"):
                assert isinstance(node, ProcessNode)
                try:
                    self._processes[node.id] = parse_process(node.dsl or {})
                except DslError as exc:
                    self._processes[node.id] = exc
        return self._processes

    def data_model(self) -> DataModel | DslError | None:
        """The ERD (first .dbml file), the error that stops it from parsing, or None."""
        files = self.model_files(".dbml")
        if self._data_model is None and files:
            rel, text = next(iter(files.items()))
            try:
                self._data_model = parse_dbml(text, rel)
            except DslError as exc:
                self._data_model = exc
        return self._data_model

    async def svg(self, rel: str) -> RenderResult:
        """SVG of a model file through Kroki; `offline` when there is no network or --offline."""
        if self.offline:
            return RenderResult(offline=True, error="проверка без сети (--offline)")
        kind = KIND_BY_SUFFIX[Path(rel).suffix]
        return await render_svg(kind, self.project.files[rel])


class BaseCheck(ABC):
    """A check: `id`, `title`, `group`, `owner` and `run()`; registered with @register."""

    id: ClassVar[str]
    title: ClassVar[str]
    group: ClassVar[Group]
    owner: ClassVar[Owner]

    @abstractmethod
    def run(
        self, graph: ArtifactGraph, ctx: CheckContext
    ) -> list[Finding] | Awaitable[list[Finding]]:
        """Findings for the graph; `async def run` for checks that wait for the network."""

    def finding(
        self, severity: Severity, node_ids: list[str], message: str, hint: str | None = None
    ) -> Finding:
        return Finding(
            check_id=self.id,
            severity=severity,
            node_ids=node_ids,
            message=message,
            hint=hint,
            owner=self.owner,
        )
