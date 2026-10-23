"""Diagram layout of a process: columns by flow order, rows by lanes (BPMN DI for the compiler).

No ready-made BPMN layout exists for Python (docs/research/2026-10-versions.md), so this is our
code on top of networkx: back flows (loops) are found by DFS, the rest is layered with
`topological_generations`; elements of one column and lane are stacked.
"""

import re
from dataclasses import dataclass, field

import networkx as nx

from reqgraph.dsl.process import EVENTS, GATEWAYS, TASKS, ProcessDSL

SIZE = {"event": (36, 36), "gateway": (50, 50)}
# Tasks: one size per process, the smallest width at which every name wraps into 2 lines
# (3 lines with the taller box); the text then stays below the icon in the top left corner.
TASK_WIDTHS = (120, 150, 180, 210, 240)
TASK_HEIGHT = {2: 100, 3: 120}
GAP_X = 50  # between tasks of neighbouring columns
GAP_Y = 40  # between rows of a lane
TEXT_PADDING = 7  # bpmn-js keeps 5 px on each side; 2 px of reserve for font differences
LABEL_BAND = 30  # left band of a pool / lane with its name
MARGIN = 40


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True)
class Bounds:
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2


@dataclass
class Layout:
    shapes: dict[str, Bounds] = field(default_factory=dict)
    waypoints: dict[str, list[Point]] = field(default_factory=dict)  # flow id -> polyline
    lanes: dict[str, Bounds] = field(default_factory=dict)
    lane_of: dict[str, str | None] = field(default_factory=dict)
    pool: Bounds | None = None
    back_flows: set[str] = field(default_factory=set)


def text_width(text: str) -> float:
    """Width of a label in bpmn-js (Arial / Liberation Sans 12px), measured in Chromium."""
    return sum(3.4 if c == " " else 9.0 if c.isupper() or c.isdigit() else 7.2 for c in text)


def wrap(text: str, width: int) -> list[str] | None:
    """Lines of a label in a box `width` wide, like bpmn-js: by spaces, a long word after `-`.

    None when a piece of a word does not fit into a line: bpmn-js would break the word itself.
    """
    room = width - 2 * TEXT_PADDING
    pieces: list[str] = []
    for word in text.split():
        pieces += [word] if text_width(word) <= room else re.split(r"(?<=-)", word)
    lines: list[str] = []
    for piece in pieces:
        if text_width(piece) > room:
            return None
        if lines and text_width(f"{lines[-1]} {piece}".replace("- ", "-")) <= room:
            joiner = "" if lines[-1].endswith("-") else " "
            lines[-1] = f"{lines[-1]}{joiner}{piece}"
        else:
            lines.append(piece)
    return lines


def task_size(dsl: ProcessDSL) -> tuple[int, int]:
    """(width, height) of every task of the process: names fit without touching the icon."""
    names = [e.name for e in dsl.nodes if e.type in TASKS]
    for max_lines, height in sorted(TASK_HEIGHT.items()):
        for width in TASK_WIDTHS:
            wrapped = [wrap(name, width) for name in names]
            if all(lines is not None and len(lines) <= max_lines for lines in wrapped):
                return width, height
    return TASK_WIDTHS[-1], TASK_HEIGHT[3]  # very long names: the widest box; keep names short


def _size(element_type: str, task: tuple[int, int]) -> tuple[int, int]:
    if element_type in EVENTS:
        return SIZE["event"]
    if element_type in GATEWAYS:
        return SIZE["gateway"]
    return task


def _back_flows(dsl: ProcessDSL) -> set[str]:
    """Flows that close a loop: DFS from the starts in DSL order, an edge into the stack is back."""
    succ: dict[str, list[tuple[str, str]]] = {e.id: [] for e in dsl.nodes}
    for flow in dsl.flow_list():
        succ[flow.src].append((flow.dst, flow.id))
    starts = [e.id for e in dsl.nodes if e.type == "start"]
    targets = {f.dst for f in dsl.flow_list()}
    roots = starts + [e.id for e in dsl.nodes if e.id not in targets] + [e.id for e in dsl.nodes]
    back: set[str] = set()
    state: dict[str, int] = {}  # 1 on the stack, 2 done
    for root in roots:
        if root in state:
            continue
        state[root] = 1
        stack = [(root, iter(succ[root]))]
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                state[node] = 2
                stack.pop()
                continue
            target, flow_id = child
            if state.get(target) == 1:
                back.add(flow_id)
            elif target not in state:
                state[target] = 1
                stack.append((target, iter(succ[target])))
    return back


def layout(dsl: ProcessDSL) -> Layout:
    result = Layout(back_flows=_back_flows(dsl))
    flows = dsl.flow_list()
    dag = nx.DiGraph()
    dag.add_nodes_from(e.id for e in dsl.nodes)
    dag.add_edges_from((f.src, f.dst) for f in flows if f.id not in result.back_flows)
    column: dict[str, int] = {}
    for index, generation in enumerate(nx.topological_generations(dag)):
        for node in generation:
            column[node] = index

    # lanes: given, or inherited from the first predecessor in flow order, or the first lane
    preds: dict[str, list[str]] = {e.id: [] for e in dsl.nodes}
    for f in flows:
        preds[f.dst].append(f.src)
    lane_of: dict[str, str | None] = {}
    order = sorted(dsl.nodes, key=lambda e: column[e.id])
    for _ in range(2):  # a second pass settles elements whose predecessor came later
        for element in order:
            if element.lane is not None or not dsl.lanes:
                lane_of[element.id] = element.lane
                continue
            inherited = next((lane_of[p] for p in preds[element.id] if lane_of.get(p)), None)
            lane_of[element.id] = inherited or lane_of.get(element.id) or dsl.lanes[0]
    result.lane_of = lane_of

    # elements of one lane and column are stacked; how many share a cell sets the lane height
    cells: dict[tuple[str | None, int], list[str]] = {}
    for element in dsl.nodes:
        cells.setdefault((lane_of[element.id], column[element.id]), []).append(element.id)
    rows: dict[str | None, int] = {}
    for (lane, _), members in cells.items():
        rows[lane] = max(rows.get(lane, 1), len(members))

    task = task_size(dsl)
    column_width, row_height = task[0] + GAP_X, task[1] + GAP_Y
    columns = max(column.values()) + 1
    left = MARGIN + (LABEL_BAND if dsl.lanes else 0)
    width = columns * column_width + MARGIN
    lane_y: dict[str | None, int] = {}
    y = MARGIN
    lane_order: list[str | None] = list(dsl.lanes) if dsl.lanes else [None]
    for lane in lane_order:
        height = rows.get(lane, 1) * row_height
        lane_y[lane] = y
        if lane is not None:
            result.lanes[lane] = Bounds(left, y, width, height)
        y += height
    if dsl.lanes:
        result.pool = Bounds(MARGIN, MARGIN, LABEL_BAND + width, y - MARGIN)

    # column by column, a cell is ordered by the height of the predecessors (fewer crossings);
    # elements without placed predecessors keep the DSL order
    size = {e.id: _size(e.type, task) for e in dsl.nodes}
    centre: dict[str, int] = {}
    forward = [f for f in flows if f.id not in result.back_flows]
    for (lane, col), members in sorted(cells.items(), key=lambda item: item[0][1]):

        def level(element_id: str) -> float:
            ys = [centre[f.src] for f in forward if f.dst == element_id and f.src in centre]
            return sum(ys) / len(ys) if ys else float("inf")

        ordered = sorted(members, key=lambda m: (level(m), members.index(m)))
        for index, element_id in enumerate(ordered):
            w, h = size[element_id]
            cx = left + MARGIN + col * column_width + column_width // 2
            cy = lane_y[lane] + index * row_height + row_height // 2
            centre[element_id] = cy
            result.shapes[element_id] = Bounds(cx - w // 2, cy - h // 2, w, h)
    result.shapes = {e.id: result.shapes[e.id] for e in dsl.nodes}

    for f in flows:
        s, d = result.shapes[f.src], result.shapes[f.dst]
        if f.id in result.back_flows:  # loop back: along the gap between rows of the lanes
            below = max(s.cy, d.cy) + row_height // 2 - 6
            points = [
                Point(s.cx, s.y + s.h),
                Point(s.cx, below),
                Point(d.cx, below),
                Point(d.cx, d.y + d.h),
            ]
        elif s.cy == d.cy:
            points = [Point(s.x + s.w, s.cy), Point(d.x, d.cy)]
        else:
            middle = (s.x + s.w + d.x) // 2
            points = [
                Point(s.x + s.w, s.cy),
                Point(middle, s.cy),
                Point(middle, d.cy),
                Point(d.x, d.cy),
            ]
        result.waypoints[f.id] = points
    return result
