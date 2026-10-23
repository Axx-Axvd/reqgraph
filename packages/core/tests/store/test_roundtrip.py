"""Round trip: load -> save -> load gives the same project; untouched files stay byte-identical."""

from pathlib import Path

import pytest
from reqgraph.graph import GraphPatch
from reqgraph.graph.nodes import NodeKind
from reqgraph.graph.store import FileStore, StoreError
from reqgraph.graph.store.formats import parse_requirements, render_requirements

from .conftest import GARAGE61, tree_hash

OWNED = {
    "reqgraph.yaml",
    "brief.md",
    "requirements/actors.yaml",
    "requirements/business.yaml",
    "requirements/constraints.yaml",
    "requirements/functional.yaml",
    "requirements/nonfunctional.yaml",
    "requirements/user.yaml",
    "models/processes/PRC-01_booking.process.json",
    "models/processes/PRC-02_reminder.process.json",
    "models/data/erd.dbml",
    "models/uml/use_cases.puml",
    "models/uml/seq_booking.puml",
    "models/c4/workspace.dsl",
    "interview/transcript.jsonl",
    "trace/edges.yaml",
}


def patch(*ops: dict[str, object]) -> GraphPatch:
    return GraphPatch.model_validate({"ops": list(ops), "rationale": "тест"})


def test_save_to_a_new_folder_is_byte_identical(tmp_path: Path) -> None:
    project = FileStore(GARAGE61).load()
    out = tmp_path / "out"
    written = FileStore(out).save(project)
    assert {p.relative_to(out).as_posix() for p in written} == OWNED
    for rel in OWNED:
        assert (out / rel).read_bytes() == (GARAGE61 / rel).read_bytes(), rel


def test_load_save_load_gives_the_same_project(tmp_path: Path) -> None:
    first = FileStore(GARAGE61).load()
    FileStore(tmp_path).save(first)
    again = FileStore(tmp_path).load()
    assert again.graph == first.graph
    assert again.config == first.config
    assert again.files == first.files


def test_saving_in_place_changes_nothing(garage61: Path) -> None:
    before = tree_hash(garage61)
    store = FileStore(garage61)
    store.save(store.load())
    assert tree_hash(garage61) == before


def test_reference_project_is_never_touched(tmp_path: Path) -> None:
    before = tree_hash(GARAGE61)
    FileStore(tmp_path).save(FileStore(GARAGE61).load())
    assert tree_hash(GARAGE61) == before


def test_changed_node_is_written_and_read_back(garage61: Path) -> None:
    store = FileStore(garage61)
    project = store.load()
    graph = project.graph.apply(
        patch({"op": "update", "id": "FR-001", "fields": {"priority": "should"}}), actor="user"
    ).graph
    store.save(project.with_graph(graph))
    again = store.load()
    assert again.graph.nodes["FR-001"].priority == "should"  # type: ignore[union-attr]
    assert again.graph == graph
    for rel in OWNED - {"requirements/functional.yaml"}:
        assert (garage61 / rel).read_bytes() == (GARAGE61 / rel).read_bytes(), rel


def test_new_node_and_edge_regenerate_the_trace_file(garage61: Path) -> None:
    store = FileStore(garage61)
    project = store.load()
    fields = {"title": "Экспорт", "statement": "Система должна выгружать записи в CSV."}
    result = project.graph.apply(
        patch(
            {"op": "add", "kind": "FR", "tmp_id": "f", "fields": fields},
            {"op": "link", "from": "f", "rel": "refines", "to": "UR-003"},
        )
    )
    store.save(project.with_graph(result.graph))
    again = store.load()
    assert result.id_map == {"f": "FR-015"}
    assert again.graph == result.graph
    assert again.warnings == []
    assert "FR-015" in (garage61 / "trace" / "edges.yaml").read_text(encoding="utf-8")


def test_removed_process_deletes_its_file(garage61: Path) -> None:
    store = FileStore(garage61)
    project = store.load()
    graph = project.graph.apply(
        patch({"op": "remove", "id": "PRC-02", "reason": "тест"}), actor="user"
    ).graph
    store.save(project.with_graph(graph))
    assert not (garage61 / "models/processes/PRC-02_reminder.process.json").exists()
    assert "PRC-02" not in store.load().graph.nodes


def test_new_process_gets_a_default_file(garage61: Path) -> None:
    store = FileStore(garage61)
    project = store.load()
    dsl = {"dsl_version": 1, "name": "Счёт", "nodes": [], "flows": []}
    result = project.graph.apply(
        patch({"op": "add", "kind": "PRC", "tmp_id": "p", "fields": {"name": "Счёт", "dsl": dsl}})
    )
    store.save(project.with_graph(result.graph))
    assert (garage61 / "models/processes/PRC-03.process.json").is_file()
    assert store.load().graph.nodes["PRC-03"].dsl == {**dsl, "id": "PRC-03"}  # type: ignore[union-attr]


def test_removed_ids_survive_a_reload(garage61: Path) -> None:
    store = FileStore(garage61)
    project = store.load()
    graph = project.graph.apply(
        patch({"op": "remove", "id": "FR-014", "reason": "тест"}), actor="user"
    ).graph
    store.save(project.with_graph(graph))
    assert (garage61 / "trace" / "ids.yaml").is_file()
    again = store.load()
    fields = {"title": "Новое", "statement": "Система должна делать новое."}
    added = again.graph.apply(patch({"op": "add", "kind": "FR", "tmp_id": "n", "fields": fields}))
    assert added.id_map == {"n": "FR-015"}  # FR-014 is not issued again


def test_reference_needs_no_counter_file(tmp_path: Path) -> None:
    FileStore(tmp_path).save(FileStore(GARAGE61).load())
    assert not (tmp_path / "trace" / "ids.yaml").exists()


def test_changed_diagram_element_is_refused_until_t104(garage61: Path) -> None:
    store = FileStore(garage61)
    project = store.load()
    graph = project.graph.apply(
        patch({"op": "update", "id": "ENT-01", "fields": {"name": "customer"}}), actor="user"
    ).graph
    with pytest.raises(StoreError, match="ENT-01"):
        store.save(project.with_graph(graph))


@pytest.mark.parametrize(
    "kind", [NodeKind.BR, NodeKind.UR, NodeKind.FR, NodeKind.NFR, NodeKind.CON, NodeKind.ACT]
)
def test_canonical_requirement_files_are_stable(kind: NodeKind) -> None:
    graph = FileStore(GARAGE61).load().graph
    text = render_requirements(kind, graph)
    nodes, edges = parse_requirements(kind, text, "x.yaml")
    assert {n.id: n for n in nodes} == {n.id: n for n in graph.nodes_of(kind)}
    owned = {e for e in graph.edges if e.src in {n.id for n in nodes}}
    assert set(edges) == owned
    assert text.startswith("# ")  # the standard header comment


def test_canonical_text_is_idempotent() -> None:
    graph = FileStore(GARAGE61).load().graph
    for kind in (NodeKind.FR, NodeKind.NFR, NodeKind.BR):
        text = render_requirements(kind, graph)
        nodes, _ = parse_requirements(kind, text, "x.yaml")
        others = [n for n in graph.nodes.values() if n.kind != kind]
        rebuilt = graph.from_parts(others + nodes, graph.edges)
        assert render_requirements(kind, rebuilt) == text
