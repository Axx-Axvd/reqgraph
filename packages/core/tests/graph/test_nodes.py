"""Node models: fields per kind, id formats, strictness (T-101)."""

from typing import Any

import pytest
from pydantic import ValidationError
from reqgraph.graph.nodes import NODE_ADAPTER, NodeKind, parse_node

GOOD: dict[str, dict[str, Any]] = {
    "BR": dict(
        id="BR-001",
        title="Цель",
        statement="Доля неявок должна снизиться.",
        priority="must",
        goal_metric={
            "name": "доля неявок",
            "unit": "%",
            "baseline": 15,
            "target": "<= 7",
            "horizon": "6 мес",
        },
    ),
    "UR": dict(
        id="UR-001",
        title="Запись",
        statement="Клиент записывается.",
        actor="ACT-01",
        scenario=["выбирает услугу"],
    ),
    "FR": dict(
        id="FR-001",
        title="Каталог",
        statement="Система должна показывать услуги.",
        priority="must",
        acceptance=["есть все услуги"],
    ),
    "NFR": dict(
        id="NFR-001",
        title="Скорость",
        statement="Ответ должен быть быстрым.",
        iso25010="performance_efficiency",
        metric={"name": "p95", "unit": "с", "threshold": "<= 2", "method": "тест"},
    ),
    "CON": dict(id="CON-001", title="152-ФЗ", type="legal", statement="Данные хранятся в РФ."),
    "ACT": dict(id="ACT-01", name="Клиент", description="Владелец автомобиля"),
    "PRC": dict(
        id="PRC-01", name="Запись", dsl={"nodes": []}, bpmn_path="models/processes/PRC-01.bpmn"
    ),
    "ENT": dict(id="ENT-01", name="Клиент", attributes=[{"name": "phone", "type": "varchar"}]),
    "UC": dict(id="UC-01", name="Записаться", actor="ACT-01", goal="получить запись"),
    "C4": dict(id="C4-CNT-01", name="Веб-сайт", c4_kind="container", technology="Next.js"),
    "TURN": dict(
        id="TURN-0001",
        role="agent",
        text="Расскажите, как записываются клиенты?",
        area_tags=["goals"],
    ),
    "SEC": dict(
        id="SEC-SRS-3.2", template="iso29148_srs", text="Функциональные требования", refs=["FR-001"]
    ),
}


@pytest.mark.parametrize("kind", list(GOOD))
def test_valid_node_of_every_kind(kind: str) -> None:
    node = parse_node({"kind": kind, **GOOD[kind]})
    assert node.kind == kind
    assert node.id == GOOD[kind]["id"]
    assert node.status == "draft"


def test_there_are_twelve_kinds() -> None:
    assert {k.value for k in NodeKind} == set(GOOD)


@pytest.mark.parametrize(
    ("kind", "bad_id"),
    [
        ("FR", "FR-1"),
        ("FR", "UR-001"),
        ("ACT", "ACT-1"),
        ("TURN", "TURN-01"),
        ("C4", "C4-XYZ-01"),
        ("PRC", "PRC-01.T01"),
    ],
)
def test_wrong_id_format_is_rejected(kind: str, bad_id: str) -> None:
    with pytest.raises(ValidationError, match="id"):
        parse_node({"kind": kind, **{**GOOD[kind], "id": bad_id}})


def test_c4_system_has_fixed_id() -> None:
    node = parse_node({"kind": "C4", "id": "C4-SYS", "name": "Система", "c4_kind": "system"})
    assert node.id == "C4-SYS"


def test_nfr_requires_metric_with_all_parts() -> None:
    data = {"kind": "NFR", **GOOD["NFR"]}
    del data["metric"]
    with pytest.raises(ValidationError, match="metric"):
        parse_node(data)
    data["metric"] = {"name": "p95", "unit": "с"}
    with pytest.raises(ValidationError, match="threshold"):
        parse_node(data)


def test_nfr_characteristic_must_be_iso25010() -> None:
    with pytest.raises(ValidationError, match="iso25010"):
        parse_node({"kind": "NFR", **{**GOOD["NFR"], "iso25010": "быстрота"}})


def test_fr_acceptance_must_not_be_empty_strings() -> None:
    with pytest.raises(ValidationError, match="acceptance"):
        parse_node({"kind": "FR", **{**GOOD["FR"], "acceptance": [""]}})


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="extra"):
        parse_node({"kind": "FR", **GOOD["FR"], "colour": "red"})


def test_status_values() -> None:
    for status in ("draft", "reviewed", "approved"):
        assert parse_node({"kind": "FR", **GOOD["FR"], "status": status}).status == status
    with pytest.raises(ValidationError, match="status"):
        parse_node({"kind": "FR", **GOOD["FR"], "status": "done"})


def test_nodes_are_immutable() -> None:
    node = parse_node({"kind": "FR", **GOOD["FR"]})
    with pytest.raises(ValidationError):
        node.title = "другое"  # type: ignore[union-attr]


def test_discriminator_picks_the_model() -> None:
    assert (
        type(NODE_ADAPTER.validate_python({"kind": "ACT", **GOOD["ACT"]})).__name__ == "ActorNode"
    )
    with pytest.raises(ValidationError, match="kind"):
        NODE_ADAPTER.validate_python({"kind": "XX", "id": "XX-1"})


def test_prefix_of_every_kind_is_consistent() -> None:
    from reqgraph.graph.nodes import KIND_PREFIX

    assert set(KIND_PREFIX) == set(NodeKind)
