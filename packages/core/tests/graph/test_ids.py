"""IdAllocator: formats, max+1, never reuse (T-101)."""

import pytest
from reqgraph.graph import ArtifactGraph, IdAllocator
from reqgraph.graph.errors import DuplicateId
from reqgraph.graph.nodes import NodeKind

from .conftest import FR, add, patch, remove


def test_formats() -> None:
    ids = IdAllocator()
    assert ids.allocate(NodeKind.BR) == "BR-001"
    assert ids.allocate(NodeKind.UR) == "UR-001"
    assert ids.allocate(NodeKind.FR) == "FR-001"
    assert ids.allocate(NodeKind.NFR) == "NFR-001"
    assert ids.allocate(NodeKind.CON) == "CON-001"
    assert ids.allocate(NodeKind.ACT) == "ACT-01"
    assert ids.allocate(NodeKind.PRC) == "PRC-01"
    assert ids.allocate(NodeKind.ENT) == "ENT-01"
    assert ids.allocate(NodeKind.UC) == "UC-01"
    assert ids.allocate(NodeKind.TURN) == "TURN-0001"


def test_sequence_and_independent_prefixes() -> None:
    ids = IdAllocator()
    assert [ids.allocate(NodeKind.FR) for _ in range(3)] == ["FR-001", "FR-002", "FR-003"]
    assert ids.allocate(NodeKind.UR) == "UR-001"


def test_c4_ids_by_element_kind() -> None:
    ids = IdAllocator()
    assert ids.allocate(NodeKind.C4, c4_kind="system") == "C4-SYS"
    assert ids.allocate(NodeKind.C4, c4_kind="container") == "C4-CNT-01"
    assert ids.allocate(NodeKind.C4, c4_kind="container") == "C4-CNT-02"
    assert ids.allocate(NodeKind.C4, c4_kind="external") == "C4-EXT-01"


def test_c4_requires_element_kind_and_system_is_single() -> None:
    ids = IdAllocator()
    with pytest.raises(ValueError, match="c4_kind"):
        ids.allocate(NodeKind.C4)
    ids.allocate(NodeKind.C4, c4_kind="system")
    with pytest.raises(DuplicateId):
        ids.allocate(NodeKind.C4, c4_kind="system")


def test_sections_are_not_allocated() -> None:
    with pytest.raises(ValueError, match="SEC"):
        IdAllocator().allocate(NodeKind.SEC)


def test_starts_after_existing_nodes(graph: ArtifactGraph) -> None:
    ids = IdAllocator.from_graph(graph)
    assert ids.allocate(NodeKind.FR) == "FR-002"
    assert ids.allocate(NodeKind.TURN) == "TURN-0002"


def test_removed_ids_are_never_reused() -> None:
    g = ArtifactGraph.empty()
    ids = IdAllocator()
    g = g.apply(patch(add("FR", "f1", **FR), add("FR", "f2", **FR)), ids=ids, actor="user").graph
    g = g.apply(patch(remove("FR-002")), ids=ids, actor="user").graph
    again = g.apply(patch(add("FR", "f3", **FR)), ids=IdAllocator.from_graph(g), actor="user")
    assert again.id_map == {
        "f3": "FR-003"
    }  # not FR-002, even for a fresh allocator built from the graph


def test_snapshot_roundtrip() -> None:
    ids = IdAllocator()
    ids.allocate(NodeKind.FR)
    ids.allocate(NodeKind.FR)
    assert IdAllocator(ids.snapshot()).allocate(NodeKind.FR) == "FR-003"
