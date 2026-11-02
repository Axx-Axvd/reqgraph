"""ReqIF export (T-403): every requirement with its fields, refines as Parent relations, valid by
the ReqIF 1.2 schema and read back by the reqif library (StrictDoc's own). Regenerate the golden
file after an intended change: REQGRAPH_UPDATE_GOLDEN=1 uv run pytest packages/core/tests/exporters
"""

import os
import re
from pathlib import Path

import pytest
from reqgraph.exporters import reqif
from reqgraph.graph.edges import Rel
from reqgraph.graph.store import FileStore
from reqgraph.graph.store.project import Project

GARAGE61 = Path(__file__).resolve().parents[4] / "examples" / "garage61"
GOLDEN = Path(__file__).resolve().parent / "golden" / "garage61.reqif"
CREATED = "2026-11-02T12:00:00+00:00"


def garage61() -> Project:
    return FileStore(GARAGE61).load()


@pytest.fixture
def written(tmp_path: Path) -> Path:
    return reqif.write_reqif(garage61(), tmp_path, created=CREATED)


def test_reqif_of_garage61_matches_the_golden_file(written: Path) -> None:
    text = written.read_text(encoding="utf-8")
    assert written.name == "req.reqif"
    if os.environ.get("REQGRAPH_UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(text, encoding="utf-8", newline="\n")
    assert GOLDEN.read_text(encoding="utf-8") == text, "REQGRAPH_UPDATE_GOLDEN=1"
    assert "Каталог услуг" in text  # plain UTF-8, not \\u escapes


def test_the_file_is_valid_by_the_reqif_schema(written: Path) -> None:
    assert reqif.schema_errors(written) == []


def test_requirements_relations_and_fields_are_read_back(written: Path) -> None:
    from reqif.parser import ReqIFParser

    bundle = ReqIFParser.parse(str(written))
    content = bundle.core_content.req_if_content
    graph = garage61().graph
    names = {
        d.identifier: d.long_name
        for t in content.spec_types
        for d in getattr(t, "attribute_definitions", None) or []
    }

    def fields(obj: object) -> dict[str, str]:
        """Values as text: XHTML without its tags, one line per paragraph."""
        found = {}
        for a in obj.attributes:  # type: ignore[attr-defined]
            text = re.sub(r"</xhtml:p>", "\n", a.value)
            found[names[a.definition_ref]] = re.sub(r"<[^>]+>", "", text).strip()
        return found

    objects = {
        fields(o).get("ReqIF.ForeignID") or o.identifier: fields(o) for o in content.spec_objects
    }
    kinds = ("BR", "UR", "FR", "NFR", "CON")
    expected = {n.id for k in kinds for n in graph.nodes_of(k)}
    assert expected <= set(objects)
    chapters = [f["ReqIF.ChapterName"] for f in objects.values() if "ReqIF.ChapterName" in f]
    assert len(chapters) == 5 and chapters[0] == "Бизнес-требования"
    fr = objects["FR-006"]
    assert fr["ReqIF.Name"] == "Расписание мастеров" and fr["ACCEPTANCE"]
    assert fr["REALIZED_BY"] == "UC-04"
    ids = {o.identifier: fields(o).get("ReqIF.ForeignID") for o in content.spec_objects}
    parents = {(ids[r.source], ids[r.target]) for r in content.spec_relations}
    refines = {(e.src, e.dst) for e in graph.edges if e.rel is Rel.REFINES}
    assert refines <= parents
    (spec,) = content.specifications
    assert spec.long_name == "Гараж 61: онлайн-запись в автосервис"
    assert [len(h.children or []) for h in spec.children] == [len(graph.nodes_of(k)) for k in kinds]


def test_cli_writes_reqif_by_default_and_on_its_own(tmp_path: Path) -> None:
    from reqgraph.cli import app
    from typer.testing import CliRunner

    args = ["export", str(GARAGE61), "--out", str(tmp_path / "r"), "--doc", "reqif"]
    only = CliRunner().invoke(app, args)
    assert only.exit_code == 0, only.output
    assert [p.name for p in (tmp_path / "r").iterdir()] == ["req.reqif"]  # no schemes, no pandoc
    assert [p.name for p in (GARAGE61 / "exports").iterdir()] == [".gitkeep"]
