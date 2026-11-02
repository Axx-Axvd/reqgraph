"""SRS sections built by code (T-408): features, NFR by characteristic, interfaces, issues."""

from pathlib import Path

from reqgraph.graph import ArtifactGraph, GraphPatch
from reqgraph.graph.store import FileStore
from reqgraph.standards import Section, load_structure
from reqgraph.standards.content import code_content

GARAGE61 = Path(__file__).resolve().parents[4] / "examples" / "garage61"
STRUCTURE = load_structure("iso29148_srs")


def graph() -> ArtifactGraph:
    return FileStore(GARAGE61).load().graph


def section(section_id: str) -> Section:
    return next(s for s in STRUCTURE.sections if s.id == section_id)


def text(section_id: str, g: ArtifactGraph | None = None) -> tuple[str, list[str]]:
    built = code_content(section(section_id), g or graph())
    assert built is not None
    return built


def test_the_structure_follows_wiegers_with_originals() -> None:
    titles = [s.title_en for s in STRUCTURE.sections]
    assert titles[:2] == ["Introduction", "Purpose"]
    assert "System features" in titles and "Appendix C: Issues list" in titles
    assert all(s.title_en for s in STRUCTURE.sections)
    llm_required = {s.llm_field for s in STRUCTURE.required if s.llm_field}
    assert llm_required == {"purpose", "scope", "perspective", "glossary"}
    assert [s.number for s in STRUCTURE.sections][-5:] == ["", "", "", "", ""]  # appendices


def test_a_feature_is_a_user_requirement_with_its_scenario_and_frs() -> None:
    body, refs = text("SEC-SRS-3")
    assert "### 3.1 Онлайн-запись частного клиента (UR-001)" in body
    first = body.split("### 3.2")[0]
    assert (
        "**Описание и приоритет.**" in first
        and "**Последовательность «стимул — отклик».**" in first
    )
    assert "- FR-001 Каталог услуг:" in first and "FR-006" not in first  # FR-006 refines UR-004
    assert "UR-001" in refs and "FR-001" in refs


def test_frs_without_a_user_requirement_go_to_other_features() -> None:
    g = graph()
    op = {
        "op": "add",
        "kind": "FR",
        "tmp_id": "f",
        "fields": {"title": "Отчёт", "statement": "Система должна строить отчёт по выручке."},
    }
    g = g.apply(GraphPatch.model_validate({"ops": [op]}), actor="user").graph
    body, _ = text("SEC-SRS-3", g)
    assert "Прочие функции" in body and "Отчёт: Система должна строить отчёт" in body


def test_nfrs_are_split_by_their_iso_25010_characteristic() -> None:
    g = graph()
    sections = ("SEC-SRS-5.1", "SEC-SRS-5.2", "SEC-SRS-5.3", "SEC-SRS-5.4")
    found = [set(text(s, g)[1]) for s in sections]
    every = {n.id for n in g.nodes_of("NFR")}
    assert set().union(*found) == every  # each NFR lands somewhere
    assert sum(len(f) for f in found) == len(every)  # and only once


def test_software_interfaces_are_integrations_and_external_systems() -> None:
    _body, refs = text("SEC-SRS-4.2")
    assert any(r.startswith("C4-EXT") for r in refs)


def test_issues_list_conflicts_and_assumptions() -> None:
    g = graph()
    ops = [
        {"op": "link", "from": "FR-007", "rel": "conflicts_with", "to": "FR-008"},
        {"op": "update", "id": "FR-012", "fields": {"assumption": True}},
    ]
    g = g.apply(GraphPatch.model_validate({"ops": ops}), actor="user").graph
    body, _refs = text("SEC-SRS-C", g)
    assert "FR-007 ↔ FR-008" in body and "FR-012" in body
    assert body.count("FR-007 ↔") + body.count("FR-008 ↔") == 1  # a symmetric pair once
    empty, _ = text("SEC-SRS-C")
    assert empty == ""


def test_models_list_entities_with_fields_and_processes() -> None:
    _body, refs = text("SEC-SRS-B")
    assert "ENT-01" in refs and "PRC-01" in refs


def test_trace_is_a_table() -> None:
    body, _refs = text("SEC-SRS-E")
    assert (
        body.startswith("| ФТ |")
        and "| FR-006 Расписание мастеров | UR-004 | BR-001, BR-002 |" in body
    )
