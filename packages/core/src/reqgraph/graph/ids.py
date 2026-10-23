"""IdAllocator: ids are issued by code, never by an LLM, and are never reused."""

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from reqgraph.graph.errors import DuplicateId
from reqgraph.graph.nodes import NodeKind

if TYPE_CHECKING:
    from reqgraph.graph.graph import ArtifactGraph

# prefix of the counter -> digits (BR-001, ACT-01, TURN-0001)
WIDTH: dict[str, int] = {
    "BR": 3,
    "UR": 3,
    "FR": 3,
    "NFR": 3,
    "CON": 3,
    "ACT": 2,
    "PRC": 2,
    "ENT": 2,
    "UC": 2,
    "C4-CNT": 2,
    "C4-EXT": 2,
    "TURN": 4,
}
SYSTEM_KEY = "C4-SYS"  # one per project, fixed id
_INDEXED = re.compile(r"^(BR|UR|FR|NFR|CON|ACT|PRC|ENT|UC|C4-CNT|C4-EXT|TURN)-(\d+)$")

_C4_KEYS = {"container": "C4-CNT", "external": "C4-EXT"}


def counter_of(node_id: str) -> tuple[str, int] | None:
    """Counter key and number encoded in an id: `FR-012` -> (`FR`, 12); sections have none."""
    if node_id == SYSTEM_KEY:
        return SYSTEM_KEY, 1
    match = _INDEXED.match(node_id)
    return (match.group(1), int(match.group(2))) if match else None


class IdAllocator:
    """Counters per prefix. Numbers only grow: a removed node's number is not issued again."""

    def __init__(self, counters: Mapping[str, int] | None = None) -> None:
        self._counters: dict[str, int] = dict(counters or {})

    @classmethod
    def from_graph(cls, graph: "ArtifactGraph") -> "IdAllocator":
        """Continue after both the graph's high-water marks and the ids it still contains."""
        allocator = cls(graph.high_water)
        for node_id in graph.nodes:
            found = counter_of(node_id)
            if found:
                key, number = found
                allocator._counters[key] = max(allocator._counters.get(key, 0), number)
        return allocator

    def allocate(self, kind: NodeKind | str, *, c4_kind: str | None = None) -> str:
        kind = NodeKind(kind)
        if kind is NodeKind.SEC:
            raise ValueError("id раздела SEC-… задаёт шаблон документа, код его не выдаёт")
        if kind is NodeKind.C4:
            if c4_kind is None:
                raise ValueError("для узла C4 нужно поле c4_kind: system, container или external")
            if c4_kind == "system":
                if self._counters.get(SYSTEM_KEY):
                    raise DuplicateId("узел C4-SYS уже был создан: система в проекте одна")
                self._counters[SYSTEM_KEY] = 1
                return SYSTEM_KEY
            key = _C4_KEYS.get(c4_kind)
            if key is None:
                raise ValueError(f"неизвестный c4_kind «{c4_kind}»")
        else:
            key = kind.value
        self._counters[key] = self._counters.get(key, 0) + 1
        return f"{key}-{self._counters[key]:0{WIDTH[key]}d}"

    def snapshot(self) -> dict[str, int]:
        return dict(sorted(self._counters.items()))

    def fork(self) -> "IdAllocator":
        return IdAllocator(self._counters)

    def merged(self, other: "IdAllocator") -> "IdAllocator":
        """Counter-wise maximum: an allocator can never hand out a number either side has used."""
        keys = self._counters.keys() | other._counters.keys()
        return IdAllocator(
            {k: max(self._counters.get(k, 0), other._counters.get(k, 0)) for k in keys}
        )

    def commit(self, other: "IdAllocator") -> None:
        """Take over the counters of a fork after a successful apply()."""
        self._counters = dict(other._counters)
