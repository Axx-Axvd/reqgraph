"""The project folder read with the real model parsers of dsl/ (T-104)."""

import shutil
from pathlib import Path

import pytest
from reqgraph.dsl.readers import model_readers
from reqgraph.graph import GraphPatch
from reqgraph.graph.store import FileStore, StoreError

from .conftest import GARAGE61

PROJECT = GARAGE61.parents[1]


def test_reference_project_with_real_parsers() -> None:
    project = FileStore(PROJECT, readers=model_readers()).load()
    booking = project.graph.nodes["ENT-05"]
    status = next(a for a in booking.attributes if a.name == "status")  # type: ignore[union-attr]
    assert status.type == "booking_status"
    assert len(project.graph.nodes_of("ENT")) == 8
    assert len(project.graph.nodes_of("UC")) == 8 and len(project.graph.nodes_of("C4")) == 6


def test_same_nodes_as_the_simple_scanner_apart_from_notes() -> None:
    simple = FileStore(PROJECT).load().graph
    real = FileStore(PROJECT, readers=model_readers()).load().graph
    assert set(simple.nodes) == set(real.nodes) and simple.edges == real.edges
    for node_id in simple.nodes:
        if node_id.startswith("ENT-"):
            names = [a.name for a in simple.nodes[node_id].attributes]  # type: ignore[union-attr]
            assert names == [a.name for a in real.nodes[node_id].attributes]  # type: ignore[union-attr]


def test_save_with_real_parsers_keeps_files(tmp_path: Path) -> None:
    folder = Path(shutil.copytree(PROJECT, tmp_path / "garage61"))
    store = FileStore(folder, readers=model_readers())
    store.save(store.load())
    erd = "models/data/erd.dbml"
    assert (folder / erd).read_bytes() == (PROJECT / erd).read_bytes()


def test_changed_entity_is_refused(tmp_path: Path) -> None:
    folder = Path(shutil.copytree(PROJECT, tmp_path / "garage61"))
    store = FileStore(folder, readers=model_readers())
    project = store.load()
    patch = GraphPatch.model_validate(
        {"ops": [{"op": "update", "id": "ENT-01", "fields": {"name": "customer"}}]}
    )
    graph = project.graph.apply(patch, actor="user").graph
    with pytest.raises(StoreError, match="ENT-01"):
        store.save(project.with_graph(graph))


def test_broken_dbml_is_a_store_error(tmp_path: Path) -> None:
    folder = Path(shutil.copytree(PROJECT, tmp_path / "garage61"))
    (folder / "models/data/erd.dbml").write_text("Table a {\n  id int [pk\n}\n", encoding="utf-8")
    with pytest.raises(StoreError, match=r"erd\.dbml"):
        FileStore(folder, readers=model_readers()).load()
