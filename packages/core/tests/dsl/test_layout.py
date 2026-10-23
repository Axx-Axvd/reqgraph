"""Layout of the diagram: columns by flow order, rows by lanes, no overlaps (T-103)."""

import itertools

import pytest
from reqgraph.dsl.layout import (
    MIN_FONT_PT,
    Bounds,
    extent,
    layout,
    page_font_pt,
    task_size,
    wrap,
)
from reqgraph.dsl.process import TASKS, ProcessDSL, parse_process

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


# --- size of tasks: readable names, clear of the icon (feedback of the author on PR #57) ----------


@pytest.mark.parametrize("name", sorted(all_processes()))
def test_task_names_fit_in_their_box(name: str) -> None:
    dsl = parse_process(load(all_processes()[name]))
    width, height = task_size(dsl)
    max_lines = 2 if height == 100 else 3
    for element in dsl.nodes:
        if element.type in TASKS:
            lines = wrap(element.name, width)
            assert lines is not None, f"{element.id}: слово не помещается в строку"
            assert len(lines) <= max_lines, (element.id, lines)


def test_all_tasks_of_a_process_have_one_size() -> None:
    dsl = parse_process(load(all_processes()["PRC-01_booking"]))
    shapes = layout(dsl).shapes
    sizes = {(shapes[e.id].w, shapes[e.id].h) for e in dsl.nodes if e.type in TASKS}
    assert sizes == {task_size(dsl)}


def test_long_names_get_a_wider_box() -> None:
    def process(task_name: str) -> ProcessDSL:
        node = {"id": "T01", "type": "task", "name": task_name}
        return parse_process({"id": "PRC-01", "name": "x", "nodes": [node]})

    assert task_size(process("Шаг")) == (120, 100)
    wide = task_size(process("Сформировать ежемесячный сводный отчёт по корпоративным договорам"))
    assert wide[0] > 120
    assert task_size(process(" ".join(["слово"] * 40))) == (240, 120)  # too long: the widest box


def test_wrap_keeps_words_whole_and_breaks_after_a_hyphen() -> None:
    assert wrap("Отправить SMS-подтверждение", 150) == ["Отправить", "SMS-подтверждение"]
    assert wrap("Отправить SMS-подтверждение", 120) == ["Отправить SMS-", "подтверждение"]
    assert wrap("Зарезервировать", 100) is None  # bpmn-js would break the word itself


# --- one process = one page (decision of the author, 23.10.2026) ---------------------------------


def test_columns_of_events_and_gateways_are_narrow() -> None:
    shapes = layout(parse_process(load(all_processes()["PRC-01_booking"]))).shapes
    start_to_task = shapes["T01"].cx - shapes["S"].cx
    task_to_task = shapes["T02"].cx - shapes["T01"].cx
    assert start_to_task < task_to_task


@pytest.mark.parametrize("name", ["PRC-01_booking", "PRC-02_reminder"])
def test_reference_processes_fit_one_landscape_page(name: str) -> None:
    result = layout(parse_process(load(all_processes()[name])))
    assert page_font_pt(result) >= MIN_FONT_PT


def test_a_long_chain_does_not_fit_one_page() -> None:
    nodes = [{"id": "S", "type": "start"}]
    nodes += [{"id": f"T{i:02d}", "type": "task", "name": f"Шаг {i}"} for i in range(1, 16)]
    nodes += [{"id": "E", "type": "end"}]
    ids = [n["id"] for n in nodes]
    flows = [[a, b] for a, b in itertools.pairwise(ids)]
    result = layout(parse_process({"id": "PRC-01", "name": "x", "nodes": nodes, "flows": flows}))
    assert page_font_pt(result) < MIN_FONT_PT


def test_small_processes_keep_full_size_on_the_page() -> None:
    result = layout(parse_process(load(all_processes()["linear"])))
    assert extent(result)[0] < 400 and page_font_pt(result) == 9.0
