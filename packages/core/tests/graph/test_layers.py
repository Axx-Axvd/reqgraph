"""Architecture (CLAUDE.md): the domain layer does not import agents or llm (T-101)."""

import ast
from pathlib import Path

import reqgraph.graph

FORBIDDEN = (
    "reqgraph.agents",
    "reqgraph.llm",
    "reqgraph.exporters",
    "reqgraph.sim",
    "reqgraph.checks",
    "reqgraph.dsl",
)


def imports_of(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_graph_package_imports_nothing_from_upper_layers() -> None:
    root = Path(reqgraph.graph.__file__).parent
    offenders = {
        f"{path.name}: {name}"
        for path in root.glob("*.py")
        for name in imports_of(path)
        if name.startswith(FORBIDDEN)
    }
    assert not offenders
