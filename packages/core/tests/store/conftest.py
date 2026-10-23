"""Helpers for store tests: copies of the reference project and tiny hand-made projects."""

import hashlib
import shutil
from pathlib import Path

import pytest

GARAGE61 = Path(__file__).resolve().parents[4] / "examples" / "garage61"

CONFIG = """project:
  id: mini
  name: "Мини-проект"
  standards: [iso29148]
  langs: [ru]
"""
BUSINESS = """- id: BR-001
  title: "Цель"
  statement: "Доля неявок должна снизиться с 15% до 7%."
  derived_from: [TURN-0001]
"""
TRANSCRIPT = '{"id": "TURN-0001", "role": "client", "text": "Хотим меньше неявок."}\n'


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def write_project(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return root


@pytest.fixture
def garage61(tmp_path: Path) -> Path:
    """A private copy: tests never write into examples/garage61 (only its author edits it)."""
    return Path(shutil.copytree(GARAGE61, tmp_path / "garage61"))


@pytest.fixture
def mini(tmp_path: Path) -> Path:
    return write_project(
        tmp_path / "mini",
        {
            "reqgraph.yaml": CONFIG,
            "requirements/business.yaml": BUSINESS,
            "interview/transcript.jsonl": TRANSCRIPT,
        },
    )
