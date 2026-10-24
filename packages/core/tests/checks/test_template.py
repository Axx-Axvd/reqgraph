"""TPL-001: required SRS sections are filled (standards/iso29148_srs.yaml, T-204)."""

from dataclasses import replace

import pytest
from reqgraph.checks.base import CheckContext, CheckSkipped
from reqgraph.checks.template import SrsSections
from reqgraph.graph import ArtifactGraph, GraphPatch
from reqgraph.graph.store import FileStore
from reqgraph.graph.store.project import Project
from reqgraph.standards import load_structure

from .conftest import GARAGE61

STRUCTURE = load_structure("iso29148_srs")


def with_sections(empty: frozenset[str] = frozenset()) -> tuple[ArtifactGraph, Project]:
    project = FileStore(GARAGE61).load()
    ops = [
        {
            "op": "add",
            "kind": "SEC",
            "tmp_id": f"s{i}",
            "fields": {"id": s.id, "template": "srs", "text": "" if s.id in empty else "текст"},
        }
        for i, s in enumerate(STRUCTURE.sections)
    ]
    graph = project.graph.apply(GraphPatch.model_validate({"ops": ops}), actor="user").graph
    return graph, project.with_graph(graph)


def test_structure_is_own_list_of_section_names() -> None:
    assert STRUCTURE.sections[0].id == "SEC-SRS-1" and len(STRUCTURE.required) == 10
    assert {s.fill for s in STRUCTURE.sections} >= {"llm:glossary", "nodes:FR", "acceptance"}


def test_all_required_sections_filled() -> None:
    graph, project = with_sections()
    assert SrsSections().run(graph, CheckContext(project)) == []


def test_empty_or_missing_required_section_is_an_error() -> None:
    graph, project = with_sections(empty=frozenset({"SEC-SRS-1.4", "SEC-SRS-1"}))  # 1 is a heading
    found = SrsSections().run(graph, CheckContext(project))
    assert [(f.severity, f.node_ids) for f in found] == [("error", ["SEC-SRS-1.4"])]
    assert "Термины и определения" in found[0].message and found[0].owner == "standards"


def test_skipped_before_sections_are_built() -> None:
    project = FileStore(GARAGE61).load()
    with pytest.raises(CheckSkipped, match="ещё не собраны"):
        SrsSections().run(project.graph, CheckContext(project))


def test_skipped_when_the_project_does_not_need_an_srs() -> None:
    graph, project = with_sections()
    info = project.config.project.model_copy(update={"standards": ["gost34_602"]})
    config = project.config.model_copy(update={"project": info})
    with pytest.raises(CheckSkipped, match="iso29148"):
        SrsSections().run(graph, CheckContext(replace(project, config=config)))
