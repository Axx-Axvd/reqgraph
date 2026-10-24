"""agents/ is the orchestration layer: nothing below imports it; LangGraph loads only with it."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest
import reqgraph

ROOT = Path(reqgraph.__file__).parent


def imports_of(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


@pytest.mark.parametrize("layer", ["graph", "dsl", "checks", "llm"])
def test_lower_layers_do_not_import_agents(layer: str) -> None:
    offenders = {
        f"{path.relative_to(ROOT)}: {name}"
        for path in (ROOT / layer).rglob("*.py")
        for name in imports_of(path)
        if name.startswith(("reqgraph.agents", "langgraph"))
    }
    assert not offenders


def test_check_command_does_not_load_langgraph() -> None:
    """langgraph + langchain-core cost about +68 MB (docs/research/2026-10-versions.md)."""
    code = "import sys, reqgraph.cli, reqgraph.checks; print('langgraph' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
