"""guard(): what an agent may not do is dropped before apply(), with the reason (T-202)."""

from typing import Any

import pytest
from reqgraph.agents.common import ALLOWED
from reqgraph.agents.guard import guard
from reqgraph.agents.state import RepairTask
from reqgraph.graph import ArtifactGraph, GraphPatch
from reqgraph.graph.store import FileStore

from .conftest import GARAGE61

ANALYST = ALLOWED["analyst"]


@pytest.fixture(scope="module")
def graph() -> ArtifactGraph:
    """garage61 with BR-001 approved by a person."""
    base = FileStore(GARAGE61).load().graph
    approve = {"ops": [{"op": "update", "id": "BR-001", "fields": {"status": "approved"}}]}
    return base.apply(GraphPatch.model_validate(approve), actor="user").graph


def patch(*ops: Any) -> GraphPatch:
    return GraphPatch.model_validate({"ops": list(ops)})


NEW_FR = {
    "op": "add",
    "kind": "FR",
    "tmp_id": "fr",
    "fields": {"title": "Отмена", "statement": "Система должна позволять отменить запись."},
}


def test_a_clean_patch_passes_untouched(graph: ArtifactGraph) -> None:
    clean = patch(
        NEW_FR,
        {"op": "link", "from": "fr", "rel": "refines", "to": "UR-002"},
        {"op": "link", "from": "fr", "rel": "derived_from", "to": "TURN-0014"},
        {"op": "update", "id": "FR-001", "fields": {"title": "Список услуг"}},
    )
    result = guard(clean, graph, allowed=ANALYST)
    assert result.patch == clean and result.dropped == []
    graph.apply(result.patch, actor="agent")  # and apply() takes it


@pytest.mark.parametrize(
    ("op", "reason"),
    [
        (
            {"op": "add", "kind": "ENT", "tmp_id": "car", "fields": {"name": "Машина"}},
            "add ENT: чужой тип узла",
        ),
        (
            {"op": "update", "id": "ENT-02", "fields": {"name": "Работа"}},
            "update ENT-02: чужой тип узла",
        ),
        (
            {"op": "update", "id": "FR-099", "fields": {"title": "x"}},
            "update FR-099: такого узла нет",
        ),
        (
            {"op": "update", "id": "BR-001", "fields": {"title": "x"}},
            "update BR-001: узел утверждён человеком",
        ),
        (
            {"op": "update", "id": "FR-001", "fields": {"status": "approved"}},
            "update FR-001: статус approved ставит только человек",
        ),
        (
            {"op": "remove", "id": "FR-003", "reason": "лишнее"},
            "remove FR-003: удалять можно только по задаче ремонта",
        ),
        (
            {"op": "link", "from": "FR-001", "rel": "refines", "to": "BR-002"},
            "link FR-001 refines BR-002: такая связь недопустима",
        ),
        (
            {"op": "link", "from": "FR-001", "rel": "derived_from", "to": "TURN-9999"},
            "link FR-001 derived_from TURN-9999: нет узла TURN-9999",
        ),
        (
            {"op": "link", "from": "nobody", "rel": "refines", "to": "UR-001"},
            "link nobody refines UR-001: узел nobody не создаётся в этом патче",
        ),
        (
            {"op": "unlink", "from": "UR-001", "rel": "refines", "to": "BR-003"},
            "unlink UR-001 refines BR-003: такой связи нет",
        ),
    ],
)
def test_each_forbidden_op_is_dropped_with_its_reason(
    graph: ArtifactGraph, op: dict[str, Any], reason: str
) -> None:
    result = guard(patch(NEW_FR, op), graph, allowed=ANALYST)
    assert result.dropped == [reason]
    assert [o.op for o in result.patch.ops] == ["add"]  # the good op stays


def test_links_of_a_dropped_node_go_with_it(graph: ArtifactGraph) -> None:
    entity = {"op": "add", "kind": "ENT", "tmp_id": "car", "fields": {"name": "Машина"}}
    link = {"op": "link", "from": "FR-001", "rel": "realized_by", "to": "car"}
    result = guard(patch(entity, link), graph, allowed=ANALYST)
    assert result.patch.ops == []
    assert result.dropped[1] == "link FR-001 realized_by car: узел car не создаётся в этом патче"


def test_links_from_approved_nodes_are_dropped(graph: ArtifactGraph) -> None:
    link = {
        "op": "link",
        "from": "UR-003",
        "rel": "refines",
        "to": "BR-001",
    }  # target may be approved
    approved_source = {"op": "link", "from": "BR-001", "rel": "derived_from", "to": "TURN-0002"}
    result = guard(patch(link, approved_source), graph, allowed=ANALYST)
    assert result.dropped == ["link BR-001 derived_from TURN-0002: узел утверждён человеком"]


def test_removal_by_a_repair_task_is_allowed(graph: ArtifactGraph) -> None:
    task = RepairTask(owner="analyst", node_ids=["FR-012"], instruction="…", check_ids=["TRC-003"])
    remove = {"op": "remove", "id": "FR-012", "reason": "задача ремонта"}
    result = guard(patch(remove), graph, allowed=ANALYST, tasks=[task])
    assert result.dropped == [] and len(result.patch.ops) == 1


def test_links_may_name_the_ids_the_adds_will_get(graph: ArtifactGraph) -> None:
    """The Modeler predicts the ids apply() issues (PRC-03 after PRC-02) and links to them."""
    prc = {"op": "add", "kind": "PRC", "tmp_id": "p", "fields": {"name": "Новый"}}
    link = {"op": "link", "from": "FR-001", "rel": "realized_by", "to": "PRC-03.T01"}
    wrong = {"op": "link", "from": "FR-001", "rel": "realized_by", "to": "PRC-04.T01"}
    result = guard(patch(prc, link, wrong), graph, allowed=ALLOWED["modeler"])
    assert result.dropped == ["link FR-001 realized_by PRC-04.T01: нет узла PRC-04"]
