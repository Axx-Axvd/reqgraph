"""schemas/*.schema.json are generated from Pydantic and must be up to date (T-101)."""

import json
from pathlib import Path

from reqgraph.cli import app
from reqgraph.schemas import SCHEMAS, render
from typer.testing import CliRunner

REPO = Path(__file__).resolve().parents[4]


def test_committed_schemas_are_current() -> None:
    for name in SCHEMAS:
        committed = (REPO / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8")
        assert committed == render(name), (
            f"schemas/{name}.schema.json устарел: uv run reqgraph schemas"
        )


def test_command_writes_files(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["schemas", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert {p.name for p in tmp_path.iterdir()} == {f"{n}.schema.json" for n in SCHEMAS}


def test_patch_schema_describes_all_operations() -> None:
    schema = json.loads(render("graph-patch"))
    text = json.dumps(schema)
    for op in ("add", "link", "unlink", "update", "remove"):
        assert f'"{op}"' in text
    assert schema["properties"]["schema_version"]["const"] == 1


def test_rendering_is_deterministic() -> None:
    assert render("graph-patch") == render("graph-patch")
    assert render("graph-patch").endswith("\n")
