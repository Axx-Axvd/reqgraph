"""SRS export (T-401, T-408, ADR-016): the project's graph -> Markdown (Jinja2) -> DOCX (pandoc).

The sections follow standards/iso29148_srs.yaml (the structure after Wiegers, T-408). Sections the
code builds (features, lists, NFR by characteristic, interfaces, issues, traceability) come from
the graph as it is now (standards/content.py); the connected text the Standards agent wrote comes
from the stored sections (documents/iso29148_srs.yaml). Appendix B carries every scheme of the
project — BPMN of the processes, the ER diagram, UML and C4 files — drawn by Kroki (cache, then
network); in Word each takes a whole landscape A4 page of its own: raw OpenXML section breaks.
"""

import re
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import Literal

import jinja2

from reqgraph.dsl.bpmn_compile import compile_bpmn
from reqgraph.dsl.kroki import KIND_BY_SUFFIX, render_svg
from reqgraph.dsl.process import parse_process
from reqgraph.graph.nodes import NodeKind, ProcessNode
from reqgraph.graph.store.project import Project
from reqgraph.standards import DocumentStructure, load_structure
from reqgraph.standards.content import llm_texts, section_text

TEMPLATE = "iso29148_srs"
Format = Literal["md", "docx"]
Document = Literal["srs", "tz", "tz19"]
# a document: its structure in standards/ and the name of its files in exports/ (T-402, T-407)
DOCUMENTS: dict[str, tuple[str, str]] = {
    "srs": ("iso29148_srs", "srs"),
    "tz": ("gost34_602", "tz_gost34"),
    "tz19": ("gost19_201", "tz_gost19"),
}
# a standard of reqgraph.yaml (project.standards) -> the document it asks for
BY_STANDARD: dict[str, Document] = {"iso29148": "srs", "gost34_602": "tz", "gost19_201": "tz19"}
TWIPS_PER_MM = 56.7
LANDSCAPE_CM = (25.7, 15.5)  # A4 landscape minus 20 mm margins and room for the caption
PORTRAIT_CM = (17.0, 24.0)  # A4 portrait minus 20 mm margins: a scheme taller than wide
PORTRAIT_BREAK = (  # ends the portrait section before a scheme (margins as in reference.docx)
    '<w:p><w:pPr><w:sectPr><w:pgSz w:w="11906" w:h="16838" />'
    '<w:pgMar w:top="1134" w:right="850" w:bottom="1134" w:left="1701" w:header="709" '
    'w:footer="709" w:gutter="0" /></w:sectPr></w:pPr></w:p>'
)
LANDSCAPE_BREAK = (  # ends the section of the scheme: that page is landscape
    '<w:p><w:pPr><w:sectPr><w:pgSz w:w="16838" w:h="11906" w:orient="landscape" />'
    '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="709" '
    'w:footer="709" w:gutter="0" /></w:sectPr></w:pPr></w:p>'
)
SCHEME_PORTRAIT_BREAK = (  # ends the section of a tall scheme: a portrait page, narrow margins
    '<w:p><w:pPr><w:sectPr><w:pgSz w:w="11906" w:h="16838" w:code="9" />'
    '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="709" '
    'w:footer="709" w:gutter="0" /></w:sectPr></w:pPr></w:p>'
)


@dataclass
class Diagram:
    id: str
    name: str
    number: int = 0
    path: str | None = None  # relative to the export folder, e.g. img/PRC-01.svg
    note: str = ""  # why it is not drawn
    width_cm: float = LANDSCAPE_CM[0]
    height_cm: float = LANDSCAPE_CM[1]
    landscape: bool = True  # BPMN always (CLAUDE.md); other schemes when wider than tall

    @property
    def page_break(self) -> str:
        return LANDSCAPE_BREAK if self.landscape else SCHEME_PORTRAIT_BREAK


@dataclass
class SectionView:
    id: str
    number: str
    title: str
    level: int
    text: str
    required: bool
    heading: bool = False  # a heading over subsections: no text of its own
    diagrams: list[Diagram] = field(default_factory=list)

    @property
    def figure(self) -> str:
        """Figures are numbered within their appendix (`Рисунок А.1`) or section (`Рисунок 4.1`)."""
        appendix = re.match(r"Приложение (\w+)\.", self.title)
        return f"{appendix.group(1) if appendix else self.number}."


FILE_LABELS = {  # a scheme kept as a model file, by the Kroki kind
    "dbml": "Модель данных (ER-диаграмма)",
    "plantuml": "Диаграмма UML",
    "structurizr": "Архитектура (C4)",
}
MODEL_ORDER = ("dbml", "plantuml", "structurizr")


@cache
def _environment() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FunctionLoader(
            lambda name: files("reqgraph.exporters").joinpath("templates", name).read_text("utf-8")
        ),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        autoescape=False,  # Markdown, not HTML
    )


def reference_docx() -> Path:
    return Path(str(files("reqgraph.exporters").joinpath("templates", "reference.docx")))


def _bold_ids(text: str) -> str:
    """`- FR-001 Title: …` -> `- **FR-001** Title: …` (a list item starts with its id)."""
    return re.sub(r"^- ([A-Z0-9]+-[A-Za-z0-9.-]+?)(:?) ", r"- **\1**\2 ", text, flags=re.M)


def sections(
    project: Project, structure: DocumentStructure, diagrams: Sequence[Diagram] = ()
) -> list[SectionView]:
    graph, info = project.graph, project.config.project
    llm = llm_texts(graph)
    views = []
    for section in structure.sections:
        text, _ = section_text(
            section, graph, llm, project_name=info.name, project_id=info.id, langs=info.langs
        )
        views.append(
            SectionView(
                id=section.id,
                number=section.number,
                title=section.title,
                level=section.level,
                text=_bold_ids(text),
                required=section.required,
                heading=section.fill == "none",
                diagrams=list(diagrams) if section.fill == "models" else [],
            )
        )
    return views


def _ratio(svg: str) -> float | None:
    """Width / height of an SVG from its viewBox or width and height."""
    box = re.search(r'viewBox="[-\d.]+[ ,]+[-\d.]+[ ,]+([\d.]+)[ ,]+([\d.]+)"', svg)
    sized = re.search(r'<svg[^>]*\swidth="([\d.]+)[a-z]*"[^>]*\sheight="([\d.]+)[a-z]*"', svg)
    match = box or sized
    if match is None or float(match.group(2)) == 0:
        return None
    return float(match.group(1)) / float(match.group(2))


def _size(svg: str, *, landscape: bool = True) -> tuple[float, float]:
    """Width and height in cm on the page, keeping the scheme's proportions."""
    page = LANDSCAPE_CM if landscape else PORTRAIT_CM
    ratio = _ratio(svg)
    if ratio is None:
        return page
    width = min(page[0], page[1] * ratio)
    return round(width, 2), round(width / ratio, 2)


async def _draw(diagram: Diagram, kind: str, source: str, out: Path, *, offline: bool) -> None:
    result = await render_svg(kind, source, offline=offline)
    if result.svg is None:
        diagram.note = result.error or "Kroki не ответил"
        return
    rel = f"img/{diagram.id}.svg"
    (out / "img").mkdir(parents=True, exist_ok=True)
    (out / rel).write_text(result.svg, encoding="utf-8")
    diagram.path = rel
    ratio = _ratio(result.svg)
    diagram.landscape = kind == "bpmn" or ratio is None or ratio >= 1
    diagram.width_cm, diagram.height_cm = _size(result.svg, landscape=diagram.landscape)


async def draw_schemes(project: Project, out: Path, *, offline: bool) -> list[Diagram]:
    """Every scheme of the project as SVG in <out>/img/: BPMN of each process with a DSL, then
    the model files — the ER diagram, UML, C4 — in that order."""
    diagrams: list[Diagram] = []
    for node in project.graph.nodes_of(NodeKind.PRC):
        assert isinstance(node, ProcessNode)
        diagram = Diagram(node.id, node.name, len(diagrams) + 1)
        diagrams.append(diagram)
        if node.dsl is None:
            diagram.note = "у процесса нет DSL"
            continue
        bpmn = compile_bpmn(parse_process(node.dsl))
        await _draw(diagram, "bpmn", bpmn, out, offline=offline)
    files = [
        (KIND_BY_SUFFIX[Path(rel).suffix], rel)
        for rel in sorted(project.files)
        if rel.startswith("models/") and Path(rel).suffix in (".dbml", ".puml", ".dsl")
    ]
    for kind, rel in sorted(files, key=lambda f: (MODEL_ORDER.index(f[0]), f[1])):
        stem = Path(rel).stem
        diagram = Diagram(f"{kind}-{stem}", f"{FILE_LABELS[kind]}, {rel}", len(diagrams) + 1)
        diagrams.append(diagram)
        await _draw(diagram, kind, project.files[rel], out, offline=offline)
    return diagrams


def render_markdown(
    project: Project,
    diagrams: Sequence[Diagram] = (),
    *,
    docx: bool = False,
    document: Document = "srs",
) -> str:
    structure = load_structure(DOCUMENTS[document][0])
    text = (
        _environment()
        .get_template("document.md.j2")
        .render(
            title=structure.title,
            project=project.config.project,
            sections=sections(project, structure, diagrams),
            docx=docx,
            portrait_break=PORTRAIT_BREAK,
        )
    )
    return re.sub(r"\n{3,}", "\n\n", text).rstrip("\n") + "\n"


EMU_PER_CM = 360_000


def widen_schemes(docx: Path, diagrams: Sequence[Diagram]) -> None:
    """pandoc fits every picture to the text width of the portrait page; a scheme gets back its
    landscape size. The pictures of the SRS are the schemes, in the same order."""
    sizes = [d for d in diagrams if d.path]
    with zipfile.ZipFile(docx) as source:
        items = [(i, source.read(i.filename)) for i in source.infolist()]
    drawings = iter(sizes)

    def resize(match: re.Match[str]) -> str:
        diagram = next(drawings, None)
        if diagram is None:
            return match.group(0)
        cx, cy = round(diagram.width_cm * EMU_PER_CM), round(diagram.height_cm * EMU_PER_CM)
        block = re.sub(
            r'<wp:extent cx="\d+" cy="\d+"', f'<wp:extent cx="{cx}" cy="{cy}"', match.group(0)
        )
        return re.sub(r'<a:ext cx="\d+" cy="\d+"', f'<a:ext cx="{cx}" cy="{cy}"', block)

    with zipfile.ZipFile(docx, "w", zipfile.ZIP_DEFLATED) as target:
        for info, data in items:
            if info.filename == "word/document.xml":
                data = re.sub(
                    r"<w:drawing>.*?</w:drawing>", resize, data.decode("utf-8"), flags=re.S
                ).encode("utf-8")
            target.writestr(info, data)


def to_docx(markdown: str, out: Path, resources: Path) -> Path:
    import pypandoc  # lazy: ~35 MB of pandoc, only for the export (CLAUDE.md, Render Free)

    pypandoc.convert_text(
        markdown,
        "docx",
        format="markdown",
        outputfile=str(out),
        extra_args=[
            "--reference-doc",
            str(reference_docx()),
            "--resource-path",
            str(resources),
            "--quiet",  # no warning about rsvg-convert: Word 2016+ shows SVG as it is
        ],
    )
    return out


def write_document(
    project: Project,
    out: Path,
    document: Document,
    diagrams: Sequence[Diagram],
    formats: Sequence[Format] = ("md", "docx"),
) -> list[Path]:
    """Write <name>.md and/or <name>.docx of one document; the schemes are drawn already."""
    name = DOCUMENTS[document][1]
    written = []
    if "md" in formats:
        path = out / f"{name}.md"
        markdown = render_markdown(project, diagrams, document=document)
        path.write_text(markdown, encoding="utf-8", newline="\n")
        written.append(path)
    if "docx" in formats:
        markdown = render_markdown(project, diagrams, docx=True, document=document)
        docx = to_docx(markdown, out / f"{name}.docx", out)
        widen_schemes(docx, diagrams)
        written.append(docx)
    return written


def exports_of(project: Project) -> list[str]:
    """What `reqgraph export` writes by default: the documents of the project and ReqIF (T-403)."""
    return [*documents_of(project), "reqif"]


def documents_of(project: Project) -> list[Document]:
    """The documents a project asks for in reqgraph.yaml (project.standards); SRS by default."""
    found = [BY_STANDARD[s] for s in project.config.project.standards]
    return found or ["srs"]


async def export_documents(
    project: Project,
    out: Path,
    documents: Sequence[Document] | None = None,
    formats: Sequence[Format] = ("md", "docx"),
    *,
    offline: bool = False,
) -> list[Path]:
    """Write the documents (SRS, TZ by GOST 34 and 19) and their schemes (img/*.svg, drawn
    once) into `out`."""
    out.mkdir(parents=True, exist_ok=True)
    diagrams = await draw_schemes(project, out, offline=offline)
    written = [out / d.path for d in diagrams if d.path]
    for document in documents or documents_of(project):
        written += write_document(project, out, document, diagrams, formats)
    return written


async def export_srs(
    project: Project,
    out: Path,
    formats: Sequence[Format] = ("md", "docx"),
    *,
    offline: bool = False,
) -> list[Path]:
    """Write srs.md and/or srs.docx (and img/*.svg) into `out`; returns the written files."""
    return await export_documents(project, out, ["srs"], formats, offline=offline)
