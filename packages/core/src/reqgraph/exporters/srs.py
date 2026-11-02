"""SRS export (T-401, ADR-016): the project's graph -> Markdown (Jinja2) -> DOCX (pandoc).

The sections follow standards/iso29148_srs.yaml. Lists of requirements, actors and entities are
built from the graph as it is now (standards/content.py); the connected text the Standards agent
wrote comes from the stored sections (documents/iso29148_srs.yaml). A traceability table closes
the document. Every BPMN scheme is drawn by Kroki (cache, then network) and in Word takes a whole
landscape A4 page of its own: raw OpenXML section breaks around the picture.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import Literal

import jinja2

from reqgraph.dsl.bpmn_compile import compile_bpmn
from reqgraph.dsl.kroki import render_svg
from reqgraph.dsl.process import parse_process
from reqgraph.graph.edges import Rel
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import FunctionalReq, NodeKind, ProcessNode, SectionNode
from reqgraph.graph.store.project import Project
from reqgraph.standards import DocumentStructure, Section, load_structure
from reqgraph.standards.content import code_content

TEMPLATE = "iso29148_srs"
Format = Literal["md", "docx"]
TWIPS_PER_MM = 56.7
LANDSCAPE_CM = (25.7, 15.5)  # A4 landscape minus 20 mm margins and room for the caption
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


@dataclass
class Diagram:
    id: str
    name: str
    number: int = 0
    path: str | None = None  # relative to the export folder, e.g. img/PRC-01.svg
    note: str = ""  # why it is not drawn
    width_cm: float = LANDSCAPE_CM[0]
    height_cm: float = LANDSCAPE_CM[1]


@dataclass
class SectionView:
    id: str
    number: str
    title: str
    level: int
    text: str
    required: bool
    diagrams: list[Diagram] = field(default_factory=list)


@dataclass(frozen=True)
class TraceRow:
    fr: str
    title: str
    urs: list[str]
    brs: list[str]
    models: list[str]


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


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _bold_ids(text: str) -> str:
    """`- FR-001 Title: …` -> `- **FR-001** Title: …` (a list item starts with its id)."""
    return re.sub(r"^- ([A-Z0-9]+-[A-Za-z0-9.-]+?)(:?) ", r"- **\1**\2 ", text, flags=re.M)


def sections(
    graph: ArtifactGraph, structure: DocumentStructure, diagrams: Sequence[Diagram] = ()
) -> list[SectionView]:
    stored = {n.id: n for n in graph.nodes_of(NodeKind.SEC) if isinstance(n, SectionNode)}
    views = []
    for section in structure.sections:
        number = section.id.removeprefix("SEC-").split("-", 1)[-1]
        views.append(
            SectionView(
                id=section.id,
                number=number,
                title=section.title,
                level=number.count(".") + 2,
                text=_text(section, graph, stored),
                required=section.required,
                diagrams=list(diagrams) if "PRC" in section.node_kinds else [],
            )
        )
    return views


def _text(section: Section, graph: ArtifactGraph, stored: dict[str, SectionNode]) -> str:
    built = code_content(section, graph)
    if built is not None:
        return _bold_ids(built[0])
    node = stored.get(section.id)
    return node.text.strip() if node is not None else ""


def traceability(graph: ArtifactGraph) -> list[TraceRow]:
    """Every FR with the UR it refines, the BR above those, the model elements realizing it."""

    def targets(src: str, rel: Rel) -> list[str]:
        return sorted(e.dst for e in graph.edges if e.src == src and e.rel is rel)

    rows = []
    for node in graph.nodes_of(NodeKind.FR):
        assert isinstance(node, FunctionalReq)
        urs = targets(node.id, Rel.REFINES)
        brs = sorted({br for ur in urs for br in targets(ur, Rel.REFINES)})
        rows.append(
            TraceRow(
                fr=node.id,
                title=_cell(node.title),
                urs=urs,
                brs=brs,
                models=targets(node.id, Rel.REALIZED_BY),
            )
        )
    return rows


def _size(svg: str) -> tuple[float, float]:
    """Width and height in cm on a landscape page, keeping the scheme's proportions."""
    box = re.search(r'viewBox="[-\d.]+[ ,]+[-\d.]+[ ,]+([\d.]+)[ ,]+([\d.]+)"', svg)
    sized = re.search(r'<svg[^>]*\swidth="([\d.]+)[a-z]*"[^>]*\sheight="([\d.]+)[a-z]*"', svg)
    match = box or sized
    if match is None or float(match.group(2)) == 0:
        return LANDSCAPE_CM
    ratio = float(match.group(1)) / float(match.group(2))
    width = min(LANDSCAPE_CM[0], LANDSCAPE_CM[1] * ratio)
    return round(width, 2), round(width / ratio, 2)


async def draw_processes(graph: ArtifactGraph, out: Path, *, offline: bool) -> list[Diagram]:
    """BPMN of every process with a DSL, as SVG files in <out>/img/."""
    diagrams = []
    for number, node in enumerate(graph.nodes_of(NodeKind.PRC), 1):
        assert isinstance(node, ProcessNode)
        diagram = Diagram(node.id, node.name, number)
        diagrams.append(diagram)
        if node.dsl is None:
            diagram.note = "у процесса нет DSL"
            continue
        result = await render_svg("bpmn", compile_bpmn(parse_process(node.dsl)), offline=offline)
        if result.svg is None:
            diagram.note = result.error or "Kroki не ответил"
            continue
        rel = f"img/{node.id}.svg"
        (out / "img").mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(result.svg, encoding="utf-8")
        diagram.path = rel
        diagram.width_cm, diagram.height_cm = _size(result.svg)
    return diagrams


def render_markdown(
    project: Project, diagrams: Sequence[Diagram] = (), *, docx: bool = False
) -> str:
    structure = load_structure(TEMPLATE)
    text = (
        _environment()
        .get_template("srs.md.j2")
        .render(
            title=structure.title,
            project=project.config.project,
            sections=sections(project.graph, structure, diagrams),
            trace=traceability(project.graph),
            docx=docx,
            portrait_break=PORTRAIT_BREAK,
            landscape_break=LANDSCAPE_BREAK,
        )
    )
    return re.sub(r"\n{3,}", "\n\n", text).rstrip("\n") + "\n"


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


async def export_srs(
    project: Project,
    out: Path,
    formats: Sequence[Format] = ("md", "docx"),
    *,
    offline: bool = False,
) -> list[Path]:
    """Write srs.md and/or srs.docx (and img/*.svg) into `out`; returns the written files."""
    out.mkdir(parents=True, exist_ok=True)
    diagrams = await draw_processes(project.graph, out, offline=offline)
    written = [out / d.path for d in diagrams if d.path]
    if "md" in formats:
        path = out / "srs.md"
        path.write_text(render_markdown(project, diagrams), encoding="utf-8", newline="\n")
        written.append(path)
    if "docx" in formats:
        written.append(
            to_docx(render_markdown(project, diagrams, docx=True), out / "srs.docx", out)
        )
    return written
