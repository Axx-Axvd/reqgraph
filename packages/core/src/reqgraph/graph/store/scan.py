"""Interim scanner of diagram files: ids and names of ENT, UC and C4 nodes (garage61 conventions).

Replaced by real parsers in T-104 (pydbml, PlantUML and Structurizr through Kroki). Conventions
(examples/garage61/REVIEW.md, No. 3): DBML — `Note: 'ENT-xx'` inside a table; PlantUML — an alias
without the dash (`UC01` = UC-01, `ACT01` = ACT-01); Structurizr — the property `reqgraph.id`.
"""

import re
from typing import Any

from reqgraph.graph.errors import GraphError
from reqgraph.graph.nodes import C4Node, EntityNode, UseCaseNode, node_from_dict
from reqgraph.graph.store.errors import StoreError

_TABLE = re.compile(r"^Table\s+\"?([\w.]+)\"?[^{\n]*\{(.*?)^\}", re.M | re.S)
_ENT_NOTE = re.compile(r"^\s*Note:\s*['\"](ENT-\d+)['\"]", re.M)
_COLUMN = re.compile(r"^\"?(\w+)\"?\s+(\w+(?:\([^)]*\))?)")
_USECASE = re.compile(r"^\s*usecase\s+\"([^\"]+)\"\s+as\s+UC(\d+)", re.M)
_ACTOR_LINK = re.compile(r"^\s*ACT(\d+)\s+-+>\s*UC(\d+)", re.M)
_C4_DECL = re.compile(
    r"^\s*(?:[\w.]+\s*=\s*)?(person|softwareSystem|container|component)\s+\"([^\"]*)\""
    r"(?:\s+\"([^\"]*)\")?(?:\s+\"([^\"]*)\")?"
)
_C4_ID = re.compile(r"\"reqgraph\.id\"\s+\"([^\"]+)\"")
_C4_KIND = {"C4-SYS": "system", "C4-CNT": "container", "C4-EXT": "external"}


def _node(data: dict[str, Any], label: str) -> Any:
    try:
        return node_from_dict(data, label)
    except GraphError as exc:
        raise StoreError(str(exc)) from None


def _unique(found: dict[str, Any], node_id: str, path: str) -> None:
    if node_id in found:
        raise StoreError(f"{path}: {node_id} встречается дважды")


def scan_dbml(text: str, path: str) -> list[EntityNode]:
    """Tables with an `ENT-xx` note become entities; their columns become attributes."""
    found: dict[str, EntityNode] = {}
    for table in _TABLE.finditer(text):
        note = _ENT_NOTE.search(table.group(2))
        if note is None:
            continue
        node_id = note.group(1)
        _unique(found, node_id, path)
        attributes = []
        for line in table.group(2).splitlines():
            line = line.strip()
            if not line or line.startswith(("Note", "//", "indexes", "}")):
                continue
            column = _COLUMN.match(line)
            if column:
                attributes.append({"name": column.group(1), "type": column.group(2)})
        data = {"kind": "ENT", "id": node_id, "name": table.group(1), "attributes": attributes}
        found[node_id] = _node(data, f"{path}: {node_id}")
    return list(found.values())


def scan_puml(text: str, path: str) -> list[UseCaseNode]:
    """`usecase "name" as UCnn`; the actor is the first `ACTnn --> UCnn` arrow to it."""
    actors: dict[str, str] = {}
    for link in _ACTOR_LINK.finditer(text):
        actors.setdefault(f"UC-{link.group(2)}", f"ACT-{link.group(1)}")
    found: dict[str, UseCaseNode] = {}
    for usecase in _USECASE.finditer(text):
        node_id = f"UC-{usecase.group(2)}"
        _unique(found, node_id, path)
        data = {"kind": "UC", "id": node_id, "name": usecase.group(1), "actor": actors.get(node_id)}
        found[node_id] = _node(data, f"{path}: {node_id}")
    return list(found.values())


def scan_c4(text: str, path: str) -> list[C4Node]:
    """An element whose `properties` (written before its children) hold `reqgraph.id` C4-…."""
    found: dict[str, C4Node] = {}
    last: re.Match[str] | None = None
    for lineno, line in enumerate(text.splitlines(), 1):
        declaration = _C4_DECL.match(line)
        if declaration:
            last = declaration
        for prop in _C4_ID.finditer(line):
            node_id = prop.group(1)
            if not node_id.startswith("C4-"):
                continue  # people are actors (ACT-xx) and live in requirements/actors.yaml
            if last is None:
                raise StoreError(
                    f"{path}, строка {lineno}: {node_id} не относится ни к одному элементу"
                )
            _unique(found, node_id, path)
            element, name, _description, technology = last.groups()
            data = {
                "kind": "C4",
                "id": node_id,
                "name": name,
                "c4_kind": _C4_KIND.get(node_id[:6], "unknown"),
                "technology": technology if element == "container" else None,
            }
            found[node_id] = _node(data, f"{path}: {node_id}")
    return list(found.values())
