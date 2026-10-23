"""Layout of the diagram: columns by flow order, rows by lanes, no overlaps (T-103)."""

import itertools

import pytest
from reqgraph.dsl.layout import Bounds, layout
from reqgraph.dsl.process import parse_process

from .conftest import all_processes, load


def overlap(a: Bounds, b: Bounds) -> bool:
    return a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h


@pytest.mark.parametrize("name", sorted(all_processes()))
def test_no_shapes_overlap(name: str) -> None:
    result = layout(parse_process(load(all_processes()[name])))
    for (i, a), (j, b) in itertools.combinations(result.shapes.items(), 2):
        assert not overlap(a, b), (i, j)


@pytest.mark.parametrize("name", sorted(all_processes()))
def test_shapes_sit_inside_their_lane(name: str) -> None:
    dsl = parse_process(load(all_processes()[name]))
    result = layout(dsl)
    for element_id, lane in result.lane_of.items():
        if lane is None:
            continue
        box, shape = result.lanes[lane], result.shapes[element_id]
        assert box.x <= shape.x and shape.x + shape.w <= box.x + box.w, element_id
        assert box.y <= shape.y and shape.y + shape.h <= box.y + box.h, element_id


@pytest.mark.parametrize("name", sorted(all_processes()))
def test_forward_flows_go_left_to_right(name: str) -> None:
    dsl = parse_process(load(all_processes()[name]))
    result = layout(dsl)
    for flow in dsl.flow_list():
        if flow.id in result.back_flows:
            continue
        assert result.shapes[flow.dst].x > result.shapes[flow.src].x, flow
        assert len(result.waypoints[flow.id]) >= 2


def test_the_loop_of_prc01_is_a_back_flow() -> None:
    dsl = parse_process(load(all_processes()["PRC-01_booking"]))
    result = layout(dsl)
    back = [f for f in dsl.flow_list() if f.id in result.back_flows]
    assert [(f.src, f.dst) for f in back] == [("T06", "G02")]


def test_lanes_follow_the_dsl_order_top_down() -> None:
    dsl = parse_process(load(all_processes()["PRC-01_booking"]))
    lanes = layout(dsl).lanes
    assert lanes["Клиент"].y < lanes["Система"].y


def test_element_without_lane_takes_the_lane_of_its_predecessor() -> None:
    dsl = parse_process(load(all_processes()["message_start"]))
    assert layout(dsl).lane_of["G01"] == "Оператор"


def test_without_lanes_there_is_no_pool() -> None:
    result = layout(parse_process(load(all_processes()["linear"])))
    assert result.pool is None and result.lanes == {}
