"""Process DSL fixtures: the two processes of garage61 and small hand-made ones."""

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
GARAGE61 = HERE.parents[3] / "examples" / "garage61" / "models" / "processes"
FIXTURES = HERE / "fixtures"
GOLDEN = HERE / "golden"


def load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def all_processes() -> dict[str, Path]:
    """Name of the golden file -> DSL file."""
    found = {
        p.name.removesuffix(".process.json"): p for p in sorted(GARAGE61.glob("*.process.json"))
    }
    found |= {
        p.name.removesuffix(".process.json"): p for p in sorted(FIXTURES.glob("*.process.json"))
    }
    return found
