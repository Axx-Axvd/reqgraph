"""Good and bad fixtures of the real checks: garage61 is clean, each mutation fires its checks.

Mutations: fixtures/bad/mutations.yaml (the table «Ожидаемые мутации» of garage61/REVIEW.md
and more). Kroki is not called: SCH-004/005 are skipped offline (their own tests fake Kroki).
"""

import asyncio
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from reqgraph.checks import all_checks, run_checks
from reqgraph.checks.report import CIReport
from reqgraph.dsl.readers import model_readers
from reqgraph.graph.store import FileStore, StoreError

from .conftest import GARAGE61

BAD = Path(__file__).resolve().parent / "fixtures" / "bad"
MUTATIONS: list[dict[str, Any]] = yaml.safe_load(
    (BAD / "mutations.yaml").read_text(encoding="utf-8")
)


def check(folder: Path) -> CIReport:
    project = FileStore(folder, readers=model_readers()).load()
    return asyncio.run(run_checks(project, offline=True))


def mutate(folder: Path, mutation: dict[str, Any]) -> None:
    if "replace" in mutation:
        rel, old, new = mutation["replace"]
        path = folder / rel
        text = path.read_text(encoding="utf-8")
        assert old in text, f"{mutation['name']}: в {rel} нет «{old}» — эталон изменился?"
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    if "add" in mutation:
        rel, source = mutation["add"]
        shutil.copyfile(BAD / source, folder / rel)
    for rel, node_id, field, value in mutation.get("edit", []):
        _edit_node(folder / rel, node_id, lambda node, f=field, v=value: _set(node, f, v))
    if "delete_node" in mutation:
        rel, node_id = mutation["delete_node"]
        _edit_node(folder / rel, node_id, None)


def _set(node: dict[str, Any], field: str, value: Any) -> None:
    if value is None:
        node.pop(field, None)
    else:
        node[field] = value


def _edit_node(path: Path, node_id: str, change: Any) -> None:
    """Change (or delete, change=None) one node of a requirements file; formatting is not kept."""
    nodes = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert any(n["id"] == node_id for n in nodes), f"в {path.name} нет {node_id}"
    if change is None:
        nodes = [n for n in nodes if n["id"] != node_id]
    else:
        for node in nodes:
            if node["id"] == node_id:
                change(node)
    path.write_text(yaml.safe_dump(nodes, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_every_review_mutation_is_covered() -> None:
    """The table «Ожидаемые мутации» of garage61/REVIEW.md has 10 rows."""
    assert sum(bool(m.get("review")) for m in MUTATIONS) == 10


def test_reference_project_is_clean() -> None:
    report = check(GARAGE61)
    assert [f for f in report.findings if f.severity != "info"] == []
    assert {c.id for c in report.checks} == {c.id for c in all_checks()}


@pytest.mark.parametrize("mutation", MUTATIONS, ids=[m["name"] for m in MUTATIONS])
def test_mutation_fires_its_checks(tmp_path: Path, mutation: dict[str, Any]) -> None:
    folder = Path(shutil.copytree(GARAGE61, tmp_path / "garage61"))
    mutate(folder, mutation)
    if "load_error" in mutation:
        with pytest.raises(StoreError, match=mutation["load_error"]):
            check(folder)
        return
    report = check(folder)
    for check_id, nodes in mutation["expect"].items():
        fired = [f for f in report.findings if f.check_id == check_id and f.severity != "info"]
        assert fired, f"{check_id} не сработала: {report.headline()}"
        seen = {n for f in fired for n in f.node_ids}
        assert set(nodes) <= seen, (check_id, nodes, seen)
