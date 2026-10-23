"""checks/ is a service: graph and dsl below it are fine, agents and llm above it are not."""

import ast
from pathlib import Path

import reqgraph.checks

FORBIDDEN = ("reqgraph.agents", "reqgraph.llm", "reqgraph.exporters", "reqgraph.sim")


def imports_of(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_checks_import_nothing_from_upper_layers() -> None:
    root = Path(reqgraph.checks.__file__).parent
    offenders = {
        f"{path.name}: {name}"
        for path in root.rglob("*.py")
        for name in imports_of(path)
        if name.startswith(FORBIDDEN)
    }
    assert not offenders


def test_pm4py_is_imported_only_by_the_soundness_check() -> None:
    """pm4py costs +160 MB and seconds (ADR-014): importing the checks must not load it."""
    import subprocess
    import sys

    code = "import sys, reqgraph.checks, reqgraph.cli; print('pm4py' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
