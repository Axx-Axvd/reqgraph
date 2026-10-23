"""dsl/ is a service: it may use the graph, but not agents, llm, checks or exporters (T-103)."""

import ast
from pathlib import Path

import reqgraph.dsl

FORBIDDEN = (
    "reqgraph.agents",
    "reqgraph.llm",
    "reqgraph.checks",
    "reqgraph.exporters",
    "reqgraph.sim",
)


def imports_of(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_dsl_imports_nothing_from_upper_layers() -> None:
    root = Path(reqgraph.dsl.__file__).parent
    offenders = {
        f"{path.name}: {name}"
        for path in root.rglob("*.py")
        for name in imports_of(path)
        if name.startswith(FORBIDDEN)
    }
    assert not offenders
