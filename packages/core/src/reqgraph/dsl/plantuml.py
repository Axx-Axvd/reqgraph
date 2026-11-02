"""PlantUML use case diagrams. Use cases are read by the conventions of garage61 (REVIEW.md,
No. 3: alias without the dash, `UC01` = UC-01); whether the file compiles is decided by Kroki
(dsl/kroki.py, check SCH-004). No PlantUML parser exists for Python and Java is not shipped:
`parse_use_cases` reads only what `render_use_cases` writes and what garage61 has by hand (T-207).
"""

import re
from dataclasses import dataclass

from reqgraph.graph.nodes import UseCaseNode
from reqgraph.graph.store.scan import scan_puml

HEADER = (
    "' СОБРАНО reqgraph из ответа Modeler (T-207).\n"
    "' Псевдоним = id узла графа без дефиса (UC01 -> UC-01, ACT01 -> ACT-01)."
)
_ACTOR = re.compile(r'^\s*actor\s+"([^"]*)"\s+as\s+ACT(\d+)\s*$')
_USECASE = re.compile(r'^\s*usecase\s+"([^"]*)"\s+as\s+UC(\d+)\s*$')
_SYSTEM = re.compile(r'^\s*rectangle\s+"([^"]*)"')
_LINK = re.compile(r"^\s*ACT(\d+)\s+-+>\s*UC(\d+)\s*$")
_RELATION = re.compile(r"^\s*UC(\d+)\s+\.+>\s*UC(\d+)\s*:\s*<<(extend|include)>>\s*$")


@dataclass(frozen=True)
class UseCase:
    id: str  # UC-01
    name: str


@dataclass(frozen=True)
class UseCaseModel:
    system: str
    actors: tuple[tuple[str, str], ...]  # (ACT-01, name)
    use_cases: tuple[UseCase, ...]
    links: tuple[tuple[str, str], ...]  # (ACT-01, UC-01): the actor takes part in the use case
    relations: tuple[tuple[str, str, str], ...] = ()  # (UC-05, UC-04, extend | include)


def read_use_cases(text: str, path: str) -> list[UseCaseNode]:
    """Reader for FileStore: `usecase "name" as UCnn`, actor from the first `ACTnn --> UCnn`."""
    return scan_puml(text, path)


def parse_use_cases(text: str) -> UseCaseModel:
    system = ""
    actors: list[tuple[str, str]] = []
    use_cases: list[UseCase] = []
    links: list[tuple[str, str]] = []
    relations: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        if match := _ACTOR.match(line):
            actors.append((f"ACT-{match.group(2)}", match.group(1)))
        elif match := _USECASE.match(line):
            use_cases.append(UseCase(f"UC-{match.group(2)}", match.group(1)))
        elif match := _SYSTEM.match(line):
            system = system or match.group(1)
        elif match := _LINK.match(line):
            links.append((f"ACT-{match.group(1)}", f"UC-{match.group(2)}"))
        elif match := _RELATION.match(line):
            relations.append((f"UC-{match.group(1)}", f"UC-{match.group(2)}", match.group(3)))
    return UseCaseModel(system, tuple(actors), tuple(use_cases), tuple(links), tuple(relations))


def _text(value: str) -> str:
    """A name inside double quotes: no quotes and no line breaks of its own."""
    return " ".join(value.replace('"', "'").split())


def _alias(node_id: str) -> str:
    return node_id.replace("-", "")


def render_use_cases(model: UseCaseModel) -> str:
    lines = [
        "@startuml use_cases",
        HEADER,
        "left to right direction",
        "skinparam shadowing false",
        "",
    ]
    lines += [f'actor "{_text(name)}" as {_alias(i)}' for i, name in model.actors]
    lines += ["", f'rectangle "{_text(model.system)}" {{']
    lines += [f'  usecase "{_text(u.name)}" as {_alias(u.id)}' for u in model.use_cases]
    lines += ["}", ""]
    lines += [f"{_alias(a)} --> {_alias(u)}" for a, u in model.links]
    lines += [f"{_alias(a)} .> {_alias(b)} : <<{kind}>>" for a, b, kind in model.relations]
    lines.append("@enduml")
    return "\n".join(lines) + "\n"
