"""Process DSL v1: the format agents write (T-103). Logic (reachability, soundness): T-106."""

from typing import Any

import pytest
from reqgraph.dsl.process import DslError, ProcessDSL, parse_process, ref

from .conftest import FIXTURES, GARAGE61, load


def base(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "dsl_version": 1,
        "id": "PRC-01",
        "name": "Процесс",
        "lanes": ["Клиент"],
        "nodes": [
            {"id": "S", "type": "start", "lane": "Клиент"},
            {"id": "T01", "type": "task", "name": "Шаг", "lane": "Клиент"},
            {"id": "E", "type": "end", "lane": "Клиент"},
        ],
        "flows": [["S", "T01"], ["T01", "E"]],
    }
    return data | changes


def test_reference_processes_parse() -> None:
    prc1 = parse_process(load(GARAGE61 / "PRC-01_booking.process.json"))
    assert prc1.id == "PRC-01" and prc1.lanes == ["Клиент", "Система"]
    assert prc1.element("T05").realizes == ["FR-005"]
    labels = {(f.src, f.dst): f.label for f in prc1.flow_list()}
    assert labels[("G01", "T04")] == "да"
    prc2 = parse_process(load(GARAGE61 / "PRC-02_reminder.process.json"))
    start = prc2.element("S")
    assert (start.event, start.timer) == ("timer", "booking.starts_at - PT24H")
    assert prc2.element("G01").type == "event_based"


def test_fixtures_parse() -> None:
    for path in FIXTURES.glob("*.process.json"):
        assert isinstance(parse_process(load(path)), ProcessDSL)


def test_flow_ids_are_numbered_in_order() -> None:
    flows = parse_process(base()).flow_list()
    assert [(f.id, f.src, f.dst, f.label) for f in flows] == [
        ("F01", "S", "T01", ""),
        ("F02", "T01", "E", ""),
    ]


def test_reference_of_an_element() -> None:
    assert ref(parse_process(base()), "T01") == "PRC-01.T01"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (base(nodes=[{"id": "S", "type": "begin"}]), "type"),
        (base(id="P-1"), "id"),
        (base(dsl_version=2), "dsl_version"),
        (base(colour="red"), "colour"),
        (
            base(nodes=base()["nodes"] + [{"id": "T01", "type": "task", "lane": "Клиент"}]),
            "T01.*повтор",
        ),
        (base(flows=[["S", "T09"]]), "T09"),
        (base(flows=[["S"]]), "flows"),
        (base(lanes=["Клиент", "Клиент"]), "дорожк"),
        (base(nodes=[{"id": "S", "type": "start", "lane": "Склад"}], flows=[]), "Склад"),
        (base(nodes=[{"id": "W", "type": "timer"}], lanes=[], flows=[]), "timer"),
        (base(nodes=[{"id": "S", "type": "start", "event": "timer"}], lanes=[], flows=[]), "timer"),
        (
            base(nodes=[{"id": "T", "type": "task", "event": "message"}], lanes=[], flows=[]),
            "event",
        ),
        (base(nodes=[{"id": "T", "type": "task", "timer": "P1D"}], lanes=[], flows=[]), "timer"),
        (base(nodes=[{"id": "t1", "type": "task"}], lanes=[], flows=[]), "id"),
        (
            base(nodes=[{"id": "T", "type": "task", "realizes": ["UR-001"]}], lanes=[], flows=[]),
            "realizes",
        ),
        (base(nodes=[]), "nodes"),
        (base(nodes=[{"id": "T", "type": "task", "lane": "Клиент"}], lanes=[], flows=[]), "дорожк"),
    ],
)
def test_invalid_dsl_is_rejected_with_a_message(data: dict[str, Any], message: str) -> None:
    with pytest.raises(DslError, match=message):
        parse_process(data)


def test_error_names_the_process() -> None:
    with pytest.raises(DslError, match="PRC-01"):
        parse_process(base(flows=[["S", "T09"]]))
