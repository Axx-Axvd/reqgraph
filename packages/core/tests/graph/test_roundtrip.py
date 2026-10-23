"""Serialization: lossless, stable order, versioned (T-101)."""

import json

import pytest
from reqgraph.graph import ArtifactGraph
from reqgraph.graph.errors import GraphError

from .conftest import FR, add, link, patch


def test_json_roundtrip_is_lossless(graph: ArtifactGraph) -> None:
    again = ArtifactGraph.from_json(graph.to_json())
    assert again == graph
    assert again.to_json() == graph.to_json()


def test_json_order_does_not_depend_on_patch_order() -> None:
    a = (
        ArtifactGraph.empty()
        .apply(patch(add("FR", "x", **FR), add("FR", "y", **FR), link("y", "depends_on", "x")))
        .graph
    )
    b = ArtifactGraph.empty().apply(patch(add("FR", "x", **FR), add("FR", "y", **FR))).graph
    b = b.apply(patch(link("FR-002", "depends_on", "FR-001"))).graph
    assert a.to_json() == b.to_json()


def test_json_shape(graph: ArtifactGraph) -> None:
    data = json.loads(graph.to_json())
    assert data["schema_version"] == 1
    assert list(data["nodes"]) == sorted(data["nodes"])  # keyed by id, sorted
    assert {"from", "rel", "to"} <= set(data["edges"][0])
    assert data["high_water"]["FR"] == 1


def test_json_uses_utf8_text_not_escapes(graph: ArtifactGraph) -> None:
    assert "Каталог услуг" in graph.to_json()


def test_unknown_schema_version_is_rejected(graph: ArtifactGraph) -> None:
    data = json.loads(graph.to_json())
    data["schema_version"] = 2
    with pytest.raises(GraphError, match="schema_version"):
        ArtifactGraph.from_json(json.dumps(data))


def test_loading_validates_edges_against_nodes(graph: ArtifactGraph) -> None:
    data = json.loads(graph.to_json())
    data["edges"].append({"from": "FR-001", "rel": "refines", "to": "UR-099"})
    with pytest.raises(GraphError, match="UR-099"):
        ArtifactGraph.from_json(json.dumps(data))


def test_loading_validates_key_equals_node_id(graph: ArtifactGraph) -> None:
    data = json.loads(graph.to_json())
    data["nodes"]["FR-002"] = data["nodes"].pop("FR-001")
    with pytest.raises(GraphError, match="FR-002"):
        ArtifactGraph.from_json(json.dumps(data))


def test_high_water_survives_the_roundtrip_after_a_removal() -> None:
    g = ArtifactGraph.empty().apply(patch(add("FR", "a", **FR), add("FR", "b", **FR))).graph
    g = g.apply(patch({"op": "remove", "id": "FR-002", "reason": "дубль"}), actor="user").graph
    again = ArtifactGraph.from_json(g.to_json())
    assert again.apply(patch(add("FR", "c", **FR))).id_map == {"c": "FR-003"}


def test_view_keeps_only_asked_kinds(graph: ArtifactGraph) -> None:
    view = graph.view({"FR", "UR"})
    assert set(view.nodes) == {"FR-001", "UR-001"}
    assert all(e.src in view.nodes and e.dst in view.nodes for e in view.edges)
    assert len(view.edges) == 1  # only FR-001 refines UR-001


def test_lookup_helpers(graph: ArtifactGraph) -> None:
    assert graph.get("FR-001").title == FR["title"]  # type: ignore[union-attr]
    assert graph.get("FR-099") is None
    assert [n.id for n in graph.nodes_of("FR")] == ["FR-001"]
    assert {(e.rel.value, e.dst) for e in graph.edges_of("FR-001")} == {
        ("refines", "UR-001"),
        ("derived_from", "TURN-0001"),
        ("realized_by", "PRC-01"),
    }
