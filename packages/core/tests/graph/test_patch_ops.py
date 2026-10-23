"""GraphPatch operations and apply(): every op, every error, atomicity (T-101)."""

import pytest
from pydantic import ValidationError
from reqgraph.graph import ArtifactGraph, GraphPatch, IdAllocator
from reqgraph.graph.edges import Edge, Rel
from reqgraph.graph.errors import BadFields, BadPatch, DuplicateId, InvalidLink, UnknownRef
from reqgraph.graph.nodes import NodeKind

from .conftest import FR, NFR, UR, add, link, patch, remove, unlink, update


def edge(src: str, rel: str, dst: str) -> Edge:
    return Edge.of(src, Rel(rel), dst)


# --- add ---------------------------------------------------------------------------------------


def test_add_gives_ids_from_the_allocator_and_reports_the_map() -> None:
    result = ArtifactGraph.empty().apply(patch(add("FR", "n1", **FR), add("FR", "n2", **FR)))
    assert result.id_map == {"n1": "FR-001", "n2": "FR-002"}
    assert set(result.graph.nodes) == {"FR-001", "FR-002"}
    assert result.diff.added == ["FR-001", "FR-002"]


def test_add_rejects_an_id_chosen_by_the_agent() -> None:
    with pytest.raises(BadFields, match="id выдаёт код"):
        ArtifactGraph.empty().apply(patch(add("FR", "n1", id="FR-077", **FR)))


def test_add_section_needs_its_template_id() -> None:
    sec = dict(id="SEC-SRS-3.2", template="iso29148_srs", text="Функциональные требования")
    result = ArtifactGraph.empty().apply(patch(add("SEC", "s1", **sec)))
    assert "SEC-SRS-3.2" in result.graph.nodes
    with pytest.raises(BadFields, match="SEC"):
        ArtifactGraph.empty().apply(patch(add("SEC", "s1", template="x", text="y")))


def test_add_section_twice_is_a_duplicate() -> None:
    sec = dict(id="SEC-SRS-3.2", template="iso29148_srs", text="Функциональные требования")
    g = ArtifactGraph.empty().apply(patch(add("SEC", "s1", **sec))).graph
    with pytest.raises(DuplicateId, match=r"SEC-SRS-3\.2"):
        g.apply(patch(add("SEC", "s2", **sec)))


def test_add_validates_the_fields_of_the_kind() -> None:
    with pytest.raises(BadFields, match="metric"):
        ArtifactGraph.empty().apply(
            patch(add("NFR", "n1", **{k: v for k, v in NFR.items() if k != "metric"}))
        )


def test_add_c4_system_twice_is_a_duplicate() -> None:
    sys_ = dict(name="Система", c4_kind="system")
    g = ArtifactGraph.empty().apply(patch(add("C4", "c1", **sys_))).graph
    assert "C4-SYS" in g.nodes
    with pytest.raises(DuplicateId):
        g.apply(patch(add("C4", "c2", **sys_)))


def test_unknown_kind_is_rejected_by_the_patch_schema() -> None:
    with pytest.raises(ValidationError, match="kind"):
        patch(add("XX", "n1"))


def test_duplicate_tmp_id_in_one_patch() -> None:
    with pytest.raises(BadPatch, match="tmp_id"):
        ArtifactGraph.empty().apply(patch(add("FR", "n1", **FR), add("FR", "n1", **FR)))


def test_tmp_id_must_not_look_like_a_real_id() -> None:
    with pytest.raises(ValidationError, match="tmp_id"):
        patch(add("FR", "FR-001", **FR))


# --- link / unlink -----------------------------------------------------------------------------


def test_link_between_new_nodes_in_any_order() -> None:
    result = ArtifactGraph.empty().apply(
        patch(
            link("f1", "refines", "u1"), add("UR", "u1", **UR), add("FR", "f1", **FR)
        )  # link comes first
    )
    assert edge("FR-001", "refines", "UR-001") in result.graph.edges
    assert result.diff.linked == [edge("FR-001", "refines", "UR-001")]


def test_link_to_an_existing_node(graph: ArtifactGraph) -> None:
    result = graph.apply(patch(add("FR", "f2", **FR), link("f2", "refines", "UR-001")))
    assert edge("FR-002", "refines", "UR-001") in result.graph.edges


def test_link_to_a_subelement_of_a_process(graph: ArtifactGraph) -> None:
    result = graph.apply(patch(link("FR-001", "realized_by", "PRC-01.T05")))
    assert edge("FR-001", "realized_by", "PRC-01.T05") in result.graph.edges


def test_link_to_a_subelement_of_a_missing_parent(graph: ArtifactGraph) -> None:
    with pytest.raises(UnknownRef, match="PRC-09"):
        graph.apply(patch(link("FR-001", "realized_by", "PRC-09.T05")))


def test_link_with_unknown_node_is_rejected(graph: ArtifactGraph) -> None:
    with pytest.raises(UnknownRef, match="UR-099"):
        graph.apply(patch(link("FR-001", "refines", "UR-099")))


def test_link_with_forbidden_kinds_is_rejected(graph: ArtifactGraph) -> None:
    with pytest.raises(InvalidLink, match="refines"):
        graph.apply(patch(link("FR-001", "refines", "BR-001")))


def test_link_twice_is_a_noop(graph: ArtifactGraph) -> None:
    result = graph.apply(patch(link("FR-001", "refines", "UR-001")))
    assert result.graph.edges == graph.edges
    assert result.diff.linked == []


def test_conflicts_with_is_stored_once_for_both_directions(graph: ArtifactGraph) -> None:
    g = graph.apply(patch(add("FR", "f2", **FR), link("f2", "conflicts_with", "FR-001"))).graph
    g = g.apply(patch(link("FR-001", "conflicts_with", "FR-002"))).graph
    assert sum(e.rel is Rel.CONFLICTS_WITH for e in g.edges) == 1


def test_unlink_removes_the_edge(graph: ArtifactGraph) -> None:
    result = graph.apply(patch(unlink("FR-001", "realized_by", "PRC-01")))
    assert edge("FR-001", "realized_by", "PRC-01") not in result.graph.edges
    assert result.diff.unlinked == [edge("FR-001", "realized_by", "PRC-01")]
    assert "FR-001" in result.graph.nodes  # the node stays


def test_unlink_of_a_missing_edge_is_an_error(graph: ArtifactGraph) -> None:
    with pytest.raises(UnknownRef, match="связи"):
        graph.apply(patch(unlink("FR-001", "refines", "BR-001")))


# --- update ------------------------------------------------------------------------------------


def test_update_changes_only_given_fields_and_reports_before_after(graph: ArtifactGraph) -> None:
    result = graph.apply(patch(update("FR-001", priority="should", status="reviewed")))
    node = result.graph.nodes["FR-001"]
    assert (node.priority, node.status, node.title) == ("should", "reviewed", FR["title"])  # type: ignore[union-attr]
    assert result.diff.changed["FR-001"] == {
        "priority": ("must", "should"),
        "status": ("draft", "reviewed"),
    }


def test_update_does_not_touch_the_source_graph(graph: ArtifactGraph) -> None:
    graph.apply(patch(update("FR-001", priority="could")))
    assert graph.nodes["FR-001"].priority == "must"  # type: ignore[union-attr]


def test_update_unknown_node(graph: ArtifactGraph) -> None:
    with pytest.raises(UnknownRef, match="FR-099"):
        graph.apply(patch(update("FR-099", priority="could")))


def test_update_cannot_change_id_or_kind(graph: ArtifactGraph) -> None:
    for bad in ({"id": "FR-002"}, {"kind": "UR"}):
        with pytest.raises(BadFields, match="нельзя менять"):
            graph.apply(patch(update("FR-001", **bad)))


def test_update_validates_values(graph: ArtifactGraph) -> None:
    with pytest.raises(BadFields, match="priority"):
        graph.apply(patch(update("FR-001", priority="urgent")))
    with pytest.raises(BadFields, match=r"extra|colour"):
        graph.apply(patch(update("FR-001", colour="red")))


def test_noop_update_has_an_empty_diff(graph: ArtifactGraph) -> None:
    result = graph.apply(patch(update("FR-001", priority="must")))
    assert result.diff.changed == {}


def test_update_reference_field_must_point_to_an_actor(graph: ArtifactGraph) -> None:
    with pytest.raises(UnknownRef, match="ACT-09"):
        graph.apply(patch(update("UR-001", actor="ACT-09")))
    with pytest.raises(InvalidLink, match="actor"):
        graph.apply(patch(update("UR-001", actor="BR-001")))


def test_actor_reference_may_use_a_tmp_id(graph: ArtifactGraph) -> None:
    result = graph.apply(
        patch(
            add("ACT", "a2", name="Менеджер", description="Автопарк"), update("UR-001", actor="a2")
        )
    )
    assert result.graph.nodes["UR-001"].actor == "ACT-02"  # type: ignore[union-attr]


# --- remove ------------------------------------------------------------------------------------


def test_remove_deletes_the_node_and_cascades_its_edges(graph: ArtifactGraph) -> None:
    result = graph.apply(patch(remove("FR-001", "дубль, задача RT-12")))
    assert "FR-001" not in result.graph.nodes
    assert not [e for e in result.graph.edges if "FR-001" in (e.src, e.dst)]
    assert result.diff.removed == ["FR-001"]
    assert len(result.diff.unlinked) == 3  # refines, derived_from, realized_by


def test_remove_cascades_edges_to_subelements(graph: ArtifactGraph) -> None:
    g = graph.apply(patch(link("FR-001", "realized_by", "PRC-01.T05"))).graph
    result = g.apply(patch(remove("PRC-01")))
    assert not [e for e in result.graph.edges if e.dst.startswith("PRC-01")]


def test_remove_requires_a_reason() -> None:
    with pytest.raises(ValidationError, match="reason"):
        patch({"op": "remove", "id": "FR-001", "reason": ""})


def test_remove_unknown_node(graph: ArtifactGraph) -> None:
    with pytest.raises(UnknownRef, match="FR-099"):
        graph.apply(patch(remove("FR-099")))


def test_remove_node_referenced_by_a_field_is_rejected(graph: ArtifactGraph) -> None:
    with pytest.raises(UnknownRef, match="UR-001"):  # UR-001.actor points to ACT-01
        graph.apply(patch(remove("ACT-01")))


def test_remove_the_referencing_node_in_the_same_patch_is_fine(graph: ArtifactGraph) -> None:
    result = graph.apply(patch(remove("UR-001"), remove("ACT-01")))
    assert "ACT-01" not in result.graph.nodes


# --- atomicity and bookkeeping -----------------------------------------------------------------


def test_failed_patch_changes_nothing_and_burns_no_ids(graph: ArtifactGraph) -> None:
    ids = IdAllocator.from_graph(graph)
    before_nodes, before_edges = dict(graph.nodes), set(graph.edges)
    with pytest.raises(UnknownRef):
        graph.apply(
            patch(
                add("FR", "f2", **FR),
                update("FR-001", priority="could"),
                link("f2", "refines", "UR-099"),  # fails on the third operation
            ),
            ids=ids,
        )
    assert dict(graph.nodes) == before_nodes and set(graph.edges) == before_edges
    assert ids.allocate(NodeKind.FR) == "FR-002"


def test_successful_patch_advances_the_allocator(graph: ArtifactGraph) -> None:
    ids = IdAllocator.from_graph(graph)
    graph.apply(patch(add("FR", "f2", **FR)), ids=ids)
    assert ids.allocate(NodeKind.FR) == "FR-003"


def test_apply_without_allocator_continues_the_numbering(graph: ArtifactGraph) -> None:
    result = graph.apply(patch(add("FR", "f2", **FR)))
    assert result.id_map == {"f2": "FR-002"}


def test_graph_is_immutable(graph: ArtifactGraph) -> None:
    with pytest.raises(ValidationError):
        graph.schema_version = 2  # type: ignore[assignment]


def test_empty_patch_is_a_noop(graph: ArtifactGraph) -> None:
    result = graph.apply(patch())
    assert result.graph == graph and result.diff.is_empty


def test_patch_stats() -> None:
    p = patch(
        add("FR", "n1", **FR),
        link("n1", "refines", "UR-001"),
        update("FR-001", priority="could"),
        remove("FR-002"),
    )
    assert p.stats() == {"add": 1, "link": 1, "unlink": 0, "update": 1, "remove": 1}


def test_patch_schema_version_is_one() -> None:
    assert GraphPatch.model_validate({"ops": []}).schema_version == 1
    with pytest.raises(ValidationError, match="schema_version"):
        GraphPatch.model_validate({"schema_version": 2, "ops": []})


def test_diff_summary_is_readable_russian(graph: ArtifactGraph) -> None:
    text = graph.apply(
        patch(add("FR", "f2", **FR), update("FR-001", priority="could"))
    ).diff.summary()
    assert "добавлено: FR-002" in text and "изменено: FR-001" in text
