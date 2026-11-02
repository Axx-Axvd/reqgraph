"""C4 models in Structurizr DSL. Elements are read by the property `reqgraph.id` (REVIEW.md of
garage61, No. 3); whether the workspace compiles is decided by Kroki (dsl/kroki.py, SCH-005).

`parse_workspace` reads only what `render_workspace` writes and what garage61 has by hand: people,
the software system with its containers, external systems and relationships of the model block
(T-207). There is no Structurizr parser for Python and Java is not shipped.
"""

import re
from dataclasses import dataclass, field

from reqgraph.graph.nodes import C4Node
from reqgraph.graph.store.scan import scan_c4

DESCRIPTION = "СОБРАНО reqgraph из ответа Modeler (T-207)"
SYSTEM_ID = "C4-SYS"
_DECL = re.compile(
    r'^\s*(?:([\w.]+)\s*=\s*)?(person|softwareSystem|container)\s+"([^"]*)"'
    r'(?:\s+"([^"]*)")?(?:\s+"([^"]*)")?'
)
_WORKSPACE = re.compile(r'^\s*workspace\s+"([^"]*)"')
_ID = re.compile(r'"reqgraph\.id"\s+"([^"]+)"')
_TAGS = re.compile(r"^\s*tags\s+(.*)$")
_RELATION = re.compile(r'^\s*([\w.]+)\s*->\s*([\w.]+)\s+"([^"]*)"(?:\s+"([^"]*)")?')
_QUOTED = re.compile(r'"[^"]*"')


@dataclass(frozen=True)
class Element:
    id: str  # C4-SYS, C4-CNT-01, C4-EXT-01; a person — ACT-01 (or its variable when it has none)
    name: str
    description: str = ""
    technology: str = ""  # containers only
    database: bool = False  # containers only: drawn as a cylinder


@dataclass(frozen=True)
class Relationship:
    src: str
    dst: str
    label: str
    technology: str = ""


@dataclass(frozen=True)
class C4Model:
    title: str
    system: Element | None
    people: tuple[Element, ...] = ()
    containers: tuple[Element, ...] = ()
    externals: tuple[Element, ...] = ()
    relations: tuple[Relationship, ...] = ()


def read_elements(text: str, path: str) -> list[C4Node]:
    """Reader for FileStore: software systems and containers with a C4-… id."""
    return scan_c4(text, path)


@dataclass
class _Declared:
    var: str
    kind: str
    name: str
    description: str
    technology: str
    id: str | None = None
    tags: set[str] = field(default_factory=set)


def parse_workspace(text: str) -> C4Model:
    title = ""
    declared: list[_Declared] = []
    stack: list[_Declared | None] = []  # open blocks: an element's or another one (properties…)
    raw: list[tuple[str, str, str, str]] = []
    for line in text.splitlines():
        bare = _QUOTED.sub('""', line)
        if title == "" and (match := _WORKSPACE.match(line)):
            title = match.group(1)
        opened: _Declared | None = None
        if match := _DECL.match(line):
            parent = next((d for d in reversed(stack) if d is not None), None)
            var = match.group(1) or f"element{len(declared) + 1}"
            if parent is not None and "." not in var:
                var = f"{parent.var}.{var}"
            opened = _Declared(
                var, match.group(2), match.group(3), match.group(4) or "", match.group(5) or ""
            )
            declared.append(opened)
        elif match := _RELATION.match(line):
            raw.append((match.group(1), match.group(2), match.group(3), match.group(4) or ""))
        current = next((d for d in reversed(stack) if d is not None), None)
        if current is not None:
            if match := _ID.search(line):
                current.id = current.id or match.group(1)
            if match := _TAGS.match(line):
                current.tags |= set(re.findall(r'"([^"]+)"', match.group(1)))
        for char in bare:
            if char == "{":
                stack.append(opened)
                opened = None
            elif char == "}" and stack:
                stack.pop()
    ids = {d.var: d.id or d.var for d in declared}

    def element(d: _Declared) -> Element:
        return Element(
            ids[d.var],
            d.name,
            d.description,
            d.technology if d.kind == "container" else "",
            database="Database" in d.tags,
        )

    systems = [d for d in declared if d.kind == "softwareSystem"]
    own = next(
        (d for d in systems if d.id == SYSTEM_ID),
        next((d for d in systems if "External" not in d.tags), None),
    )
    return C4Model(
        title=title,
        system=element(own) if own is not None else None,
        people=tuple(element(d) for d in declared if d.kind == "person"),
        containers=tuple(element(d) for d in declared if d.kind == "container"),
        externals=tuple(element(d) for d in systems if d is not own),
        relations=tuple(
            Relationship(ids.get(s, s), ids.get(t, t), lab, tech) for s, t, lab, tech in raw
        ),
    )


def _text(value: str) -> str:
    return " ".join(value.replace('"', "'").split())


def _var(element_id: str) -> str:
    """C4-SYS -> system, C4-CNT-01 -> cnt01, C4-EXT-01 -> ext01, ACT-01 -> act01."""
    if element_id == SYSTEM_ID:
        return "system"
    if element_id.startswith("C4-"):
        element_id = element_id[3:]
    return re.sub(r"[^a-z0-9_]", "", element_id.lower()) or "element"


def _block(lines: list[str], indent: str, element: Element, tags: list[str]) -> None:
    has_id = element.id.startswith(("C4-", "ACT-"))
    if not tags and not has_id:
        return
    lines[-1] += " {"
    if tags:
        lines.append(f"{indent}    tags " + " ".join(f'"{t}"' for t in tags))
    if has_id:
        lines += [
            f"{indent}    properties {{",
            f'{indent}        "reqgraph.id" "{element.id}"',
            f"{indent}    }}",
        ]
    lines.append(f"{indent}}}")


def _declare(keyword: str, element: Element, *, technology: bool = False) -> str:
    args = [element.name, element.description]
    if technology and element.technology:
        args.append(element.technology)
    return f"{keyword} " + " ".join(f'"{_text(a)}"' for a in args)


def render_workspace(model: C4Model) -> str:
    system = model.system or Element(SYSTEM_ID, model.title)
    path = {system.id: "system"} | {c.id: f"system.{_var(c.id)}" for c in model.containers}
    path |= {e.id: _var(e.id) for e in (*model.people, *model.externals)}
    pad = " " * 8
    lines = [
        f'workspace "{_text(model.title)}" "{DESCRIPTION}" {{',
        "",
        "    !identifiers hierarchical",
        "",
        "    model {",
    ]
    for person in model.people:
        lines.append(f"{pad}{_var(person.id)} = {_declare('person', person)}")
        _block(lines, pad, person, [])
    lines.append("")
    lines.append(f"{pad}system = {_declare('softwareSystem', system)} {{")
    lines += [
        f"{pad}    properties {{",
        f'{pad}        "reqgraph.id" "{system.id}"',
        f"{pad}    }}",
    ]
    for container in model.containers:
        lines.append(
            f"{pad}    {_var(container.id)} = " + _declare("container", container, technology=True)
        )
        _block(lines, pad + "    ", container, ["Database"] if container.database else [])
    lines.append(f"{pad}}}")
    for external in model.externals:
        lines.append("")
        lines.append(f"{pad}{_var(external.id)} = {_declare('softwareSystem', external)}")
        _block(lines, pad, external, ["External"])
    lines.append("")
    for rel in model.relations:
        src, dst = path.get(rel.src, _var(rel.src)), path.get(rel.dst, _var(rel.dst))
        tech = f' "{_text(rel.technology)}"' if rel.technology else ""
        lines.append(f'{pad}{src} -> {dst} "{_text(rel.label)}"{tech}')
    lines += ["    }", "", "    views {"]
    lines += [
        f'{pad}systemContext system "context" {{',
        f"{pad}    include *",
        f"{pad}    autolayout lr",
        f"{pad}}}",
    ]
    if model.containers:
        lines += [
            f'{pad}container system "containers" {{',
            f"{pad}    include *",
            f"{pad}    autolayout lr",
            f"{pad}}}",
        ]
    lines += [
        f"{pad}styles {{",
        f'{pad}    element "Database" {{',
        f"{pad}        shape cylinder",
        f"{pad}    }}",
        f'{pad}    element "External" {{',
        f"{pad}        background #999999",
        f"{pad}    }}",
        f"{pad}}}",
        "    }",
        "}",
    ]
    return "\n".join(lines) + "\n"
