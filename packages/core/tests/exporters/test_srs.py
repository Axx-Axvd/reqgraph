"""SRS export (T-401): Markdown by the structure, traceability, BPMN pages, DOCX through pandoc.

Kroki is replaced by a stub (no network in unit tests). Regenerate the golden Markdown after an
intended change: REQGRAPH_UPDATE_GOLDEN=1 uv run pytest packages/core/tests/exporters
"""

import asyncio
import os
import zipfile
from pathlib import Path

import pytest
from reqgraph.dsl.kroki import RenderResult
from reqgraph.exporters import srs
from reqgraph.graph import GraphPatch
from reqgraph.graph.store import FileStore
from reqgraph.graph.store.project import Project
from reqgraph.standards import load_structure

GARAGE61 = Path(__file__).resolve().parents[4] / "examples" / "garage61"
GOLDEN = Path(__file__).resolve().parent / "golden"
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="400" viewBox="0 0 1400 400"/>'


@pytest.fixture
def kroki(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    asked: list[str] = []

    async def fake(kind: str, source: str, *, offline: bool = False) -> RenderResult:
        asked.append(kind)
        return RenderResult(svg=SVG)

    monkeypatch.setattr(srs, "render_svg", fake)
    return asked


def garage61() -> Project:
    return FileStore(GARAGE61).load()


def export(project: Project, out: Path, *formats: srs.Format) -> list[Path]:
    return asyncio.run(srs.export_srs(project, out, formats or ("md", "docx")))


def test_markdown_of_garage61_matches_the_golden_file(tmp_path: Path, kroki: list[str]) -> None:
    export(garage61(), tmp_path, "md")
    text = (tmp_path / "srs.md").read_text(encoding="utf-8")
    golden = GOLDEN / "garage61_srs.md"
    if os.environ.get("REQGRAPH_UPDATE_GOLDEN") == "1":
        golden.write_text(text, encoding="utf-8", newline="\n")
    assert golden.read_text(encoding="utf-8") == text, "REQGRAPH_UPDATE_GOLDEN=1"
    # appendix B: a scheme per process, then the ER diagram, two UML files and C4 (T-408)
    assert kroki == ["bpmn", "bpmn", "dbml", "plantuml", "plantuml", "structurizr"]


def test_every_section_in_order_with_ids(tmp_path: Path, kroki: list[str]) -> None:
    export(garage61(), tmp_path, "md")
    text = (tmp_path / "srs.md").read_text(encoding="utf-8")
    titles = [s.title for s in load_structure(srs.TEMPLATE).sections]
    positions = [text.index(t) for t in titles]
    assert positions == sorted(positions)
    assert "- **FR-001** Каталог услуг:" in text and "- **ACT-01** Частный клиент" in text
    assert "*Раздел не заполнен.*" in text  # garage61 has no Standards text: purpose is empty
    assert "![Рисунок Б.1 — PRC-01 · " in text and "](img/PRC-01.svg)" in text
    assert "![Рисунок Б.3 — Модель данных (ER-диаграмма), models/data/erd.dbml]" in text
    assert "## Приложение Д. Трассировка требований" in text  # appendices: no number of their own
    assert "### 3.1 Онлайн-запись частного клиента (UR-001)" in text  # system features
    assert "openxml" not in text  # page breaks are only for Word


def test_traceability_goes_from_fr_to_goals_and_models() -> None:
    from reqgraph.standards.content import trace_rows

    rows = {r[0]: r for r in trace_rows(garage61().graph)}
    assert len(rows) == 14
    assert rows["FR-006"][2] == ["UR-004"] and rows["FR-006"][3] == ["BR-001", "BR-002"]
    assert "PRC-01.T02" in rows["FR-001"][4] and "ENT-02" in rows["FR-001"][4]


def test_the_standards_text_comes_from_the_stored_sections(
    tmp_path: Path, kroki: list[str]
) -> None:
    project = garage61()
    op = {
        "op": "add",
        "kind": "SEC",
        "tmp_id": "s",
        "fields": {"id": "SEC-SRS-1.1", "template": "iso29148_srs", "text": "Запись в сервис."},
    }
    graph = project.graph.apply(GraphPatch.model_validate({"ops": [op]}), actor="user").graph
    export(project.with_graph(graph), tmp_path, "md")
    text = (tmp_path / "srs.md").read_text(encoding="utf-8")
    assert "### 1.1 Назначение\n\nЗапись в сервис." in text


def test_docx_has_headings_the_table_and_a_landscape_page_per_scheme(
    tmp_path: Path, kroki: list[str]
) -> None:
    written = export(garage61(), tmp_path, "docx")
    assert tmp_path / "srs.docx" in written and not (tmp_path / "srs.md").exists()
    with zipfile.ZipFile(tmp_path / "srs.docx") as docx:
        xml = docx.read("word/document.xml").decode("utf-8")
        media = [n for n in docx.namelist() if n.startswith("word/media/")]
    assert "Функциональные требования" in xml and "Трассировка требований" in xml
    assert "<w:tbl>" in xml
    assert xml.count('w:orient="landscape"') == 6 and len(media) == 6  # every scheme of garage61
    assert xml.count('w:h="16838" />') == 1  # one portrait break: no empty page between schemes
    full = round(srs.LANDSCAPE_CM[0] * srs.EMU_PER_CM)
    assert xml.count(f'<wp:extent cx="{full}"') == 6  # the whole landscape width, not the portrait
    assert "Times New Roman" in zipfile.ZipFile(tmp_path / "srs.docx").read(
        "word/styles.xml"
    ).decode("utf-8")


def test_without_kroki_the_scheme_is_named_not_drawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def offline(kind: str, source: str, *, offline: bool = False) -> RenderResult:
        return RenderResult(offline=True, error="нет сети")

    monkeypatch.setattr(srs, "render_svg", offline)
    export(garage61(), tmp_path, "md")
    text = (tmp_path / "srs.md").read_text(encoding="utf-8")
    assert "схема не отрисована (нет сети)" in text and not (tmp_path / "img").exists()


def test_scheme_size_keeps_proportions_on_its_page() -> None:
    wide = srs._size('<svg viewBox="35 35 1410 430" width="1410" height="430">')
    tall = srs._size('<svg width="400" height="800">')
    assert wide[0] == srs.LANDSCAPE_CM[0] and wide[1] < srs.LANDSCAPE_CM[1]
    assert tall[1] == srs.LANDSCAPE_CM[1] and tall[0] < srs.LANDSCAPE_CM[0]
    upright = srs._size('<svg width="400" height="800">', landscape=False)
    assert upright == (12.0, 24.0)  # a tall scheme fills a portrait page by its height


def test_a_tall_model_scheme_gets_a_portrait_page_a_bpmn_never(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tall = '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="900"/>'

    async def fake(kind: str, source: str, *, offline: bool = False) -> RenderResult:
        return RenderResult(svg=tall)

    monkeypatch.setattr(srs, "render_svg", fake)
    diagrams = asyncio.run(srs.draw_schemes(garage61(), tmp_path, offline=True))
    assert [d.landscape for d in diagrams] == [True, True, False, False, False, False]


def test_cli_exports_into_the_chosen_folder(tmp_path: Path, kroki: list[str]) -> None:
    from reqgraph.cli import app
    from typer.testing import CliRunner

    result = CliRunner().invoke(app, ["export", str(GARAGE61), "--out", str(tmp_path), "--offline"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "srs.md").is_file() and (tmp_path / "srs.docx").is_file()
    exported = [p.name for p in (GARAGE61 / "exports").iterdir()]
    assert exported == [".gitkeep"]  # the reference project is not touched
    bad = CliRunner().invoke(app, ["export", str(GARAGE61), "--format", "pdf"])
    assert bad.exit_code == 2 and "md, docx" in bad.output


def test_tz_of_garage61_matches_the_golden_file(tmp_path: Path, kroki: list[str]) -> None:
    """T-402: the TZ by GOST 34.602 from the same graph, schemes drawn once for both documents."""
    written = asyncio.run(srs.export_documents(garage61(), tmp_path, ["srs", "tz"], ["md"]))
    assert tmp_path / "tz_gost34.md" in written and tmp_path / "srs.md" in written
    assert len(kroki) == 6  # not 12: the schemes are shared
    text = (tmp_path / "tz_gost34.md").read_text(encoding="utf-8")
    golden = GOLDEN / "garage61_tz_gost34.md"
    if os.environ.get("REQGRAPH_UPDATE_GOLDEN") == "1":
        golden.write_text(text, encoding="utf-8", newline="\n")
    assert golden.read_text(encoding="utf-8") == text, "REQGRAPH_UPDATE_GOLDEN=1"
    assert text.startswith("# Техническое задание на создание автоматизированной системы")
    assert "### 1.1 Полное наименование системы и её условное обозначение" in text
    assert "Гараж 61: онлайн-запись в автосервис (условное обозначение — garage61)." in text
    assert "#### 4.1.9 Требования к защите информации" in text and "**CON-001**" in text
    assert "### 4.2 Требования к функциям (задачам), выполняемым системой" in text
    assert "Заполняется заказчиком при заключении договора." in text
    assert "Требования не предъявляются." in text
    assert "## Приложение А. Модели системы" in text and "](img/PRC-01.svg)" in text
    assert "![Рисунок А.1 — PRC-01 · " in text and "Рисунок Б." not in text


def test_tz_docx_puts_every_bpmn_on_a_landscape_page(tmp_path: Path, kroki: list[str]) -> None:
    asyncio.run(srs.export_documents(garage61(), tmp_path, ["tz"], ["docx"]))
    with zipfile.ZipFile(tmp_path / "tz_gost34.docx") as docx:
        xml = docx.read("word/document.xml").decode("utf-8")
    assert xml.count('w:orient="landscape"') == 6 and "Источники разработки" in xml


def test_cli_exports_the_documents_the_project_asks_for(tmp_path: Path, kroki: list[str]) -> None:
    from reqgraph.cli import app
    from typer.testing import CliRunner

    args = ["export", str(GARAGE61), "--out", str(tmp_path), "--format", "md"]
    result = CliRunner().invoke(app, args)  # garage61: standards [iso29148, gost34_602]
    assert result.exit_code == 0, result.output
    assert (tmp_path / "srs.md").is_file() and (tmp_path / "tz_gost34.md").is_file()
    assert (tmp_path / "req.reqif").is_file()  # T-403: ReqIF goes with the documents
    only = CliRunner().invoke(app, [*args, "--out", str(tmp_path / "tz"), "--doc", "tz"])
    assert only.exit_code == 0 and not (tmp_path / "tz" / "srs.md").exists()
    bad = CliRunner().invoke(app, [*args, "--doc", "gost19"])
    assert bad.exit_code == 2 and "srs, tz, tz19, reqif" in bad.output
    program = CliRunner().invoke(app, [*args, "--out", str(tmp_path / "p"), "--doc", "tz19"])
    assert program.exit_code == 0 and (tmp_path / "p" / "tz_gost19.md").is_file()


def test_program_tz_of_garage61_matches_the_golden_file(tmp_path: Path, kroki: list[str]) -> None:
    """T-407: the TZ for a program by GOST 19.201 from the same graph and the same schemes."""
    written = asyncio.run(srs.export_documents(garage61(), tmp_path, ["tz19"], ["md"]))
    assert tmp_path / "tz_gost19.md" in written
    text = (tmp_path / "tz_gost19.md").read_text(encoding="utf-8")
    golden = GOLDEN / "garage61_tz_gost19.md"
    if os.environ.get("REQGRAPH_UPDATE_GOLDEN") == "1":
        golden.write_text(text, encoding="utf-8", newline="\n")
    assert golden.read_text(encoding="utf-8") == text, "REQGRAPH_UPDATE_GOLDEN=1"
    assert text.startswith("# Техническое задание на разработку программы")
    assert "### 1.1 Наименование программы" in text
    assert "### 4.1 Требования к функциональным характеристикам" in text
    assert "#### 4.1.1 Онлайн-запись частного клиента (UR-001)" in text
    assert "### 4.6 Требования к маркировке и упаковке\n\nТребования не предъявляются." in text
    assert "## Приложение А. Модели программы" in text and "](img/PRC-01.svg)" in text
    assert "![Рисунок А.1 — PRC-01 · " in text and "Рисунок Б." not in text  # its own appendix


def test_program_tz_docx_puts_every_bpmn_on_a_landscape_page(
    tmp_path: Path, kroki: list[str]
) -> None:
    asyncio.run(srs.export_documents(garage61(), tmp_path, ["tz19"], ["docx"]))
    with zipfile.ZipFile(tmp_path / "tz_gost19.docx") as docx:
        xml = docx.read("word/document.xml").decode("utf-8")
    assert xml.count('w:orient="landscape"') == 6 and "Порядок контроля и приёмки" in xml


def test_documents_follow_the_standards_of_the_project() -> None:
    from dataclasses import replace

    project = garage61()
    info = project.config.project.model_copy(update={"standards": ["gost19_201", "iso29148"]})
    config = project.config.model_copy(update={"project": info})
    assert srs.documents_of(replace(project, config=config)) == ["tz19", "srs"]
