"""Text formats of a project folder: requirement YAML, transcript JSONL, process JSON, trace files.

Every `parse_*` raises StoreError with the file path; every `render_*` gives the canonical text
(stable: same graph -> same bytes on every OS).
"""

import json
import re
from typing import Any

import yaml
from pydantic import ValidationError

from reqgraph.graph.edges import Edge, Rel, kind_of
from reqgraph.graph.errors import GraphError
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import (
    InterviewTurn,
    Node,
    NodeKind,
    ProcessNode,
    node_from_dict,
    validation_text,
)
from reqgraph.graph.store.config import ProjectConfig
from reqgraph.graph.store.errors import StoreError

REQUIREMENT_FILES: dict[NodeKind, str] = {
    NodeKind.ACT: "requirements/actors.yaml",
    NodeKind.BR: "requirements/business.yaml",
    NodeKind.UR: "requirements/user.yaml",
    NodeKind.FR: "requirements/functional.yaml",
    NodeKind.NFR: "requirements/nonfunctional.yaml",
    NodeKind.CON: "requirements/constraints.yaml",
}
HEADERS: dict[NodeKind, str] = {
    NodeKind.ACT: "# Акторы (ACT): роли людей, которые работают с системой.\n",
    NodeKind.BR: "# Бизнес-требования (BR): зачем заказчику система. Каждое — с измеримой целью.\n",
    NodeKind.UR: (
        "# Пользовательские требования (UR): что пользователь делает с системой. refines -> BR.\n"
    ),
    NodeKind.FR: (
        "# Функциональные требования (FR): что должна делать система. "
        "Формулировки по шаблонам EARS:\n"
        "#   «Система должна ...», «Когда <событие>, система должна ...», "
        "«Если <нежелательное>, система должна ...».\n"
        "# refines -> UR; derived_from -> TURN; realized_by -> элементы моделей "
        "(задачи процессов, ENT, UC, C4).\n"
    ),
    NodeKind.NFR: (
        "# Нефункциональные требования (NFR): характеристика ISO/IEC 25010 + метрика + единица "
        "+ порог + метод проверки.\n"
    ),
    NodeKind.CON: "# Ограничения (CON): законы, бюджет, сроки, технологии.\n",
}
CONFIG_FILE = "reqgraph.yaml"
BRIEF_FILE = "brief.md"
TRANSCRIPT_FILE = "interview/transcript.jsonl"
PROCESS_DIR = "models/processes"
PROCESS_SUFFIX = ".process.json"
EDGES_FILE = "trace/edges.yaml"
IDS_FILE = "trace/ids.yaml"
EDGES_HEADER = (
    "# СГЕНЕРИРОВАНО из requirements/*.yaml — не править руками.\n"
    "# Канонический источник рёбер — поля refines / realized_by / derived_from "
    "в узлах требований.\n"
)
IDS_HEADER = (
    "# Счётчики id: номера удалённых узлов не выдаются повторно. "
    "Пишет FileStore, руками не править.\n"
)

# Relations stored in the source node, in the order they are written. `rendered_in` is not stored:
# document sections are rebuilt by the exporters.
EDGE_KEYS: tuple[Rel, ...] = (
    Rel.REFINES,
    Rel.DERIVED_FROM,
    Rel.REALIZED_BY,
    Rel.DEPENDS_ON,
    Rel.CONFLICTS_WITH,
)
_EDGE_NAMES = frozenset(r.value for r in EDGE_KEYS)
# Field order in requirement files (as in garage61); fields not listed follow in model order.
FIELD_ORDER: dict[NodeKind, tuple[str, ...]] = {
    NodeKind.ACT: ("id", "name", "description", "status", "area", "assumption"),
    NodeKind.BR: ("id", "title", "statement", "goal_metric", "priority", "status", "area"),
    NodeKind.UR: ("id", "actor", "title", "statement", "scenario", "priority", "status", "area"),
    NodeKind.FR: ("id", "title", "statement", "priority", "status", "area", "assumption"),
    NodeKind.NFR: ("id", "title", "statement", "iso25010", "metric", "priority", "status", "area"),
    NodeKind.CON: ("id", "type", "title", "statement", "status", "area"),
}
# Values written without quotes: ids and enumerations.
_SYMBOL_FIELDS = frozenset({"id", "actor", "priority", "status", "area", "iso25010", "type"})
_BARE = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-]*$")
_YAML_WORDS = frozenset({"y", "n", "yes", "no", "true", "false", "on", "off", "null"})
# order of the generated trace file: by kind of the source node, then id, relation, target
_TRACE_KINDS = tuple(REQUIREMENT_FILES)
_TRACE_RELS = (Rel.REFINES, Rel.REALIZED_BY, Rel.DERIVED_FROM, Rel.DEPENDS_ON, Rel.CONFLICTS_WITH)


# --- helpers -------------------------------------------------------------------------------


def load_yaml(text: str, path: str) -> Any:
    try:
        return yaml.safe_load(text)
    except yaml.MarkedYAMLError as exc:
        line = exc.problem_mark.line + 1 if exc.problem_mark else "?"
        raise StoreError(f"{path}: ошибка YAML, строка {line}: {exc.problem}") from None
    except yaml.YAMLError as exc:
        raise StoreError(f"{path}: ошибка YAML: {exc}") from None


def _node(data: dict[str, Any], label: str) -> Node:
    try:
        return node_from_dict(data, label)
    except GraphError as exc:
        raise StoreError(str(exc)) from None


def stored_edges(graph: ArtifactGraph) -> set[Edge]:
    """Edges a project folder keeps: those of EDGE_KEYS that start at a requirement or an actor."""
    return {e for e in graph.edges if e.rel in EDGE_KEYS and kind_of(e.src) in REQUIREMENT_FILES}


# --- reqgraph.yaml ---------------------------------------------------------------------------


def parse_config(text: str, path: str = CONFIG_FILE) -> ProjectConfig:
    data = load_yaml(text, path)
    try:
        return ProjectConfig.model_validate(data)
    except ValidationError as exc:
        raise StoreError(f"{path}: {validation_text(exc, '')}") from None


def render_config(config: ProjectConfig) -> str:
    data = config.model_dump(mode="json", exclude_defaults=True)
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100)


# --- requirements/*.yaml ---------------------------------------------------------------------


def parse_requirements(kind: NodeKind, text: str, path: str) -> tuple[list[Node], list[Edge]]:
    """Nodes of one kind and the edges kept in them (`refines: [UR-001]` and the like)."""
    data = load_yaml(text, path)
    if data is None:
        return [], []
    if not isinstance(data, list):
        raise StoreError(f"{path}: ожидается список узлов (строки «- id: …»)")
    nodes: list[Node] = []
    edges: list[Edge] = []
    for number, item in enumerate(data, 1):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise StoreError(f"{path}: элемент {number}: ожидается узел с полем id")
        node_id = item["id"]
        try:
            found = kind_of(node_id)
        except ValueError:
            found = None
        if found is not kind:
            raise StoreError(f"{path}: узел {node_id} — в этом файле только узлы вида {kind}")
        for rel in EDGE_KEYS:
            targets = item.get(rel.value)
            if targets is None:
                continue
            if not isinstance(targets, list) or not all(isinstance(t, str) for t in targets):
                raise StoreError(
                    f"{path}: {node_id}: поле {rel.value} — список id, например [UR-001]"
                )
            edges += [Edge.of(node_id, rel, t) for t in targets]
        fields = {k: v for k, v in item.items() if k not in _EDGE_NAMES}
        nodes.append(_node({**fields, "kind": kind.value}, f"{path}: {node_id}"))
    return nodes, edges


def _scalar(key: str, value: Any, *, quote_all: bool = False) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int | float):
        return str(value)
    if not isinstance(value, str):
        raise TypeError(f"{key}: значение {value!r} не записывается в YAML")
    bare = (
        not quote_all
        and key in _SYMBOL_FIELDS
        and _BARE.match(value)
        and value.lower() not in _YAML_WORDS
    )
    return value if bare else json.dumps(value, ensure_ascii=False)


def _field_lines(key: str, value: Any) -> list[str]:
    if isinstance(value, dict):
        inner = ", ".join(f"{k}: {_scalar(k, v, quote_all=True)}" for k, v in value.items())
        return [f"  {key}: {{{inner}}}"]
    if isinstance(value, list):
        if all(isinstance(v, str) for v in value) and key in _EDGE_NAMES:
            return [f"  {key}: [{', '.join(value)}]"]
        lines = [f"  {key}:"]
        for v in value:
            if isinstance(v, dict):
                inner = ", ".join(f"{k}: {_scalar(k, x, quote_all=True)}" for k, x in v.items())
                lines.append(f"    - {{{inner}}}")
            else:
                lines.append(f"    - {_scalar(key, v, quote_all=True)}")
        return lines
    return [f"  {key}: {_scalar(key, value)}"]


def render_requirements(kind: NodeKind, graph: ArtifactGraph) -> str:
    """Canonical text of one requirements file: header, nodes by id, blank line between nodes."""
    edges = stored_edges(graph)
    blocks = []
    for node in graph.nodes_of(kind):
        data = node.model_dump(mode="json", exclude_defaults=True, exclude={"kind"})
        data["id"] = node.id
        order = FIELD_ORDER[kind] + tuple(k for k in type(node).model_fields if k != "kind")
        lines: list[str] = []
        for key in dict.fromkeys(order):
            if key in data:
                lines += _field_lines(key, data[key])
        for rel in EDGE_KEYS:
            targets = sorted(e.dst for e in edges if e.src == node.id and e.rel is rel)
            if targets:
                lines += _field_lines(rel.value, targets)
        lines[0] = "- " + lines[0][2:]
        blocks.append("\n".join(lines) + "\n")
    return HEADERS[kind] + ("\n".join(blocks) if blocks else "[]\n")


# --- interview/transcript.jsonl --------------------------------------------------------------


def parse_transcript(text: str, path: str = TRANSCRIPT_FILE) -> list[Node]:
    turns = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StoreError(f"{path}, строка {number}: не JSON ({exc.msg})") from None
        if not isinstance(data, dict):
            raise StoreError(f"{path}, строка {number}: ожидается объект реплики")
        turns.append(_node({**data, "kind": "TURN"}, f"{path}, строка {number}"))
    return turns


def render_transcript(graph: ArtifactGraph) -> str:
    lines = []
    for turn in graph.nodes_of(NodeKind.TURN):
        assert isinstance(turn, InterviewTurn)
        extra = turn.model_dump(mode="json", exclude_defaults=True, exclude={"kind"})
        data = {"id": turn.id, "role": turn.role, "text": turn.text, "area_tags": turn.area_tags}
        lines.append(json.dumps(data | extra, ensure_ascii=False))
    return "".join(f"{line}\n" for line in lines)


# --- models/processes/*.process.json ---------------------------------------------------------


def parse_process(text: str, path: str) -> ProcessNode:
    """A process node keeps the whole DSL; its id and name are taken from the DSL."""
    try:
        dsl = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StoreError(f"{path}: не JSON, строка {exc.lineno}: {exc.msg}") from None
    if not isinstance(dsl, dict) or not isinstance(dsl.get("id"), str):
        raise StoreError(f"{path}: в процессе нет поля id (например «PRC-01»)")
    data = {"kind": "PRC", "id": dsl["id"], "name": dsl.get("name"), "dsl": dsl}
    node = _node(data, f"{path}: {dsl['id']}")
    assert isinstance(node, ProcessNode)
    return node


def render_process(node: ProcessNode) -> str:
    dsl = dict(node.dsl or {})
    head = {"dsl_version": dsl.pop("dsl_version", 1), "id": node.id, "name": node.name}
    dsl.pop("id", None)
    dsl.pop("name", None)
    return json.dumps(head | dsl, ensure_ascii=False, indent=2) + "\n"


def process_path(node_id: str) -> str:
    return f"{PROCESS_DIR}/{node_id}{PROCESS_SUFFIX}"


# --- trace/edges.yaml and trace/ids.yaml -----------------------------------------------------


def parse_edges(text: str, path: str = EDGES_FILE) -> set[Edge]:
    data = load_yaml(text, path) or []
    try:
        return {Edge.model_validate(row) for row in data}
    except (ValidationError, TypeError):
        raise StoreError(f"{path}: ожидается список {{from, rel, to}}") from None


def render_edges(graph: ArtifactGraph) -> str:
    def key(e: Edge) -> tuple[int, str, int, str]:
        return (_TRACE_KINDS.index(kind_of(e.src)), e.src, _TRACE_RELS.index(e.rel), e.dst)

    rows = [
        f"- {{from: {e.src}, rel: {e.rel.value}, to: {e.dst}}}"
        for e in sorted(stored_edges(graph), key=key)
    ]
    return EDGES_HEADER + "".join(f"{row}\n" for row in rows)


def parse_ids(text: str, path: str = IDS_FILE) -> dict[str, int]:
    data = load_yaml(text, path) or {}
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, int) for k, v in data.items()
    ):
        raise StoreError(f"{path}: ожидается «префикс: номер», например «FR: 14»")
    return data


def render_ids(high_water: dict[str, int]) -> str:
    return IDS_HEADER + "".join(f"{k}: {v}\n" for k, v in sorted(high_water.items()))
