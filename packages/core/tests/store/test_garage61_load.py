"""The reference project loads into a consistent graph (T-102)."""

from collections import Counter

import yaml
from reqgraph.graph import Edge
from reqgraph.graph.store import FileStore, Project

from .conftest import GARAGE61


def load() -> Project:
    return FileStore(GARAGE61).load()


def test_node_counts() -> None:
    counts = Counter(n.kind for n in load().graph.nodes.values())
    assert counts == {
        "ACT": 3,
        "BR": 3,
        "UR": 4,
        "FR": 14,
        "NFR": 5,
        "CON": 3,
        "PRC": 2,
        "ENT": 8,
        "UC": 8,
        "C4": 6,
        "TURN": 32,
    }


def test_edges_match_the_generated_trace_file() -> None:
    project = load()
    rows = yaml.safe_load((GARAGE61 / "trace" / "edges.yaml").read_text(encoding="utf-8"))
    assert set(project.graph.edges) == {Edge.model_validate(r) for r in rows}
    assert len(project.graph.edges) == 88
    assert project.warnings == []


def test_config() -> None:
    config = load().config
    assert config.project.id == "garage61"
    assert config.project.standards == ["iso29148", "gost34_602"]
    assert config.interview.coverage_need["nfr"] == 4
    assert config.checks.disabled == []


def test_fields_of_requirements_and_turns() -> None:
    g = load().graph
    assert g.nodes["UR-001"].actor == "ACT-01"  # type: ignore[union-attr]
    assert g.nodes["NFR-001"].metric.unit == "с"  # type: ignore[union-attr]
    assert g.nodes["TURN-0002"].role == "client"  # type: ignore[union-attr]
    assert g.nodes["BR-001"].status == "reviewed"


def test_processes_keep_the_whole_dsl() -> None:
    project = load()
    prc = project.graph.nodes["PRC-02"]
    assert prc.name == "Напоминание и отмена записи"  # type: ignore[union-attr]
    assert prc.dsl["flows"][0] == ["S", "T01"]  # type: ignore[union-attr,index]
    assert project.layout["PRC-01"] == "models/processes/PRC-01_booking.process.json"


def test_model_elements_are_found_in_diagram_files() -> None:
    g = load().graph
    assert g.nodes["ENT-05"].name == "Запись"  # type: ignore[union-attr]
    assert {a.name for a in g.nodes["ENT-05"].attributes} >= {"id", "status"}  # type: ignore[union-attr]
    uc = g.nodes["UC-01"]
    assert (uc.name, uc.actor) == ("Записаться на обслуживание", "ACT-01")  # type: ignore[union-attr]
    cnt = g.nodes["C4-CNT-01"]
    assert (cnt.name, cnt.c4_kind, cnt.technology) == ("Веб-приложение", "container", "Next.js")  # type: ignore[union-attr]
    assert g.nodes["C4-SYS"].c4_kind == "system"  # type: ignore[union-attr]
    assert g.nodes["C4-EXT-01"].c4_kind == "external"  # type: ignore[union-attr]


def test_counters_continue_after_the_reference() -> None:
    hw = load().graph.high_water
    assert (hw["FR"], hw["TURN"], hw["ACT"]) == (14, 32, 3)


def test_project_remembers_its_folder() -> None:
    assert load().root == GARAGE61
