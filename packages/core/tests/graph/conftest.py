"""Helpers for graph tests: a small realistic graph built only through patches."""

from typing import Any

import pytest
from reqgraph.graph import ArtifactGraph, GraphPatch, IdAllocator


def patch(*ops: dict[str, Any], rationale: str = "тест") -> GraphPatch:
    return GraphPatch.model_validate({"ops": list(ops), "rationale": rationale})


def add(kind: str, tmp_id: str, **fields: Any) -> dict[str, Any]:
    return {"op": "add", "kind": kind, "tmp_id": tmp_id, "fields": fields}


def link(src: str, rel: str, dst: str) -> dict[str, Any]:
    return {"op": "link", "from": src, "rel": rel, "to": dst}


def unlink(src: str, rel: str, dst: str) -> dict[str, Any]:
    return {"op": "unlink", "from": src, "rel": rel, "to": dst}


def update(node_id: str, **fields: Any) -> dict[str, Any]:
    return {"op": "update", "id": node_id, "fields": fields}


def remove(node_id: str, reason: str = "тест") -> dict[str, Any]:
    return {"op": "remove", "id": node_id, "reason": reason}


BR = dict(
    title="Снизить неявки", statement="Доля неявок должна снизиться с 15% до 7%.", priority="must"
)
UR = dict(title="Онлайн-запись", statement="Клиент записывается через сайт.", priority="must")
FR = dict(
    title="Каталог услуг",
    statement="Система должна показывать список услуг.",
    priority="must",
    acceptance=["в списке есть все услуги"],
)
NFR = dict(
    title="Время ответа",
    statement="Показ слотов должен занимать не более 2 с.",
    iso25010="performance_efficiency",
    metric={"name": "p95", "unit": "с", "threshold": "<= 2", "method": "нагрузочный тест"},
)


@pytest.fixture
def ids() -> IdAllocator:
    return IdAllocator()


@pytest.fixture
def graph(ids: IdAllocator) -> ArtifactGraph:
    """BR-001 <- UR-001 <- FR-001 -> TURN-0001, ACT-01, FR-001 realized_by PRC-01 (all draft)."""
    g = ArtifactGraph.empty()
    result = g.apply(
        patch(
            add("TURN", "t1", role="client", text="Хотим онлайн-запись"),
            add("ACT", "a1", name="Частный клиент", description="Владелец автомобиля"),
            add("BR", "b1", **BR),
            add("UR", "u1", actor="a1", **UR),
            add("FR", "f1", **FR),
            add("PRC", "p1", name="Запись на обслуживание"),
            link("b1", "derived_from", "t1"),
            link("u1", "refines", "b1"),
            link("f1", "refines", "u1"),
            link("f1", "derived_from", "t1"),
            link("f1", "realized_by", "p1"),
        ),
        ids=ids,
        actor="user",
    )
    return result.graph
