"""Broken project folders give a Russian message with the file and the node, never a traceback."""

from pathlib import Path

import pytest
from reqgraph.graph.store import FileStore, StoreError

from .conftest import BUSINESS, write_project


def load(root: Path) -> None:
    FileStore(root).load()


def test_minimal_project_loads(mini: Path) -> None:
    project = FileStore(mini).load()
    assert set(project.graph.nodes) == {"BR-001", "TURN-0001"}
    assert project.config.project.id == "mini"


def test_missing_config(tmp_path: Path) -> None:
    with pytest.raises(StoreError, match=r"reqgraph\.yaml"):
        load(tmp_path)


def test_bad_config_field(mini: Path) -> None:
    write_project(mini, {"reqgraph.yaml": "project: {id: mini, name: x}\ncolour: red\n"})
    with pytest.raises(StoreError, match=r"reqgraph\.yaml.*colour"):
        load(mini)


def test_yaml_syntax_error_names_the_line(mini: Path) -> None:
    write_project(mini, {"requirements/business.yaml": BUSINESS + "  title: [\n"})
    with pytest.raises(StoreError, match=r"business\.yaml.*строка"):
        load(mini)


def test_file_must_hold_a_list(mini: Path) -> None:
    write_project(mini, {"requirements/business.yaml": "id: BR-001\n"})
    with pytest.raises(StoreError, match=r"business\.yaml.*список"):
        load(mini)


def test_node_of_another_kind_in_the_file(mini: Path) -> None:
    write_project(mini, {"requirements/business.yaml": BUSINESS.replace("BR-001", "UR-001")})
    with pytest.raises(StoreError, match=r"business\.yaml.*UR-001"):
        load(mini)


def test_unknown_field(mini: Path) -> None:
    write_project(mini, {"requirements/business.yaml": BUSINESS + '  colour: "red"\n'})
    with pytest.raises(StoreError, match=r"business\.yaml.*BR-001.*colour"):
        load(mini)


def test_duplicate_id(mini: Path) -> None:
    write_project(mini, {"requirements/business.yaml": BUSINESS + BUSINESS})
    with pytest.raises(StoreError, match=r"BR-001.*повтор"):
        load(mini)


def test_dangling_edge(mini: Path) -> None:
    text = BUSINESS.replace("TURN-0001", "TURN-0099")
    write_project(mini, {"requirements/business.yaml": text})
    with pytest.raises(StoreError, match="TURN-0099"):
        load(mini)


def test_forbidden_kind_pair(mini: Path) -> None:
    write_project(mini, {"requirements/business.yaml": BUSINESS + "  refines: [TURN-0001]\n"})
    with pytest.raises(StoreError, match="refines"):
        load(mini)


def test_edge_list_must_be_a_list(mini: Path) -> None:
    text = BUSINESS.replace("[TURN-0001]", "TURN-0001")
    write_project(mini, {"requirements/business.yaml": text})
    with pytest.raises(StoreError, match=r"derived_from.*список"):
        load(mini)


def test_bad_transcript_line(mini: Path) -> None:
    write_project(mini, {"interview/transcript.jsonl": '{"id": "TURN-0001"\n'})
    with pytest.raises(StoreError, match=r"transcript\.jsonl.*строка 1"):
        load(mini)


def test_bad_process_json(mini: Path) -> None:
    write_project(mini, {"models/processes/PRC-01.process.json": "{"})
    with pytest.raises(StoreError, match=r"PRC-01\.process\.json"):
        load(mini)


def test_process_without_id(mini: Path) -> None:
    write_project(mini, {"models/processes/PRC-01.process.json": '{"name": "x"}'})
    with pytest.raises(StoreError, match=r"PRC-01\.process\.json.*id"):
        load(mini)


def test_foreign_files_under_models_are_ignored(mini: Path) -> None:
    (mini / "models" / "pics").mkdir(parents=True)
    (mini / "models" / "pics" / "logo.png").write_bytes(b"\x89PNG\xff\xfe")
    project = FileStore(mini).load()
    assert not any(rel.startswith("models/") for rel in project.files)


def test_stale_trace_file_is_a_warning(mini: Path) -> None:
    write_project(
        mini, {"trace/edges.yaml": "- {from: BR-001, rel: derived_from, to: TURN-0002}\n"}
    )
    project = FileStore(mini).load()
    assert any("edges.yaml" in w for w in project.warnings)
