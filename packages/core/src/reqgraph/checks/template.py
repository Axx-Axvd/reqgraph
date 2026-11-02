"""TPL-001 and TPL-002: required sections of the SRS and of the TZ are filled (own structures in
standards/, names only — ADR-012).

TPL-001 checks standards/iso29148_srs.yaml (the structure after Wiegers, T-408), TPL-002 —
standards/gost34_602.yaml (the TZ by GOST 34.602-2020, T-402). Sections the code builds are taken
from the graph as it is now; the connected text — from the sections the Standards agent wrote for
the SRS, which the TZ shares. Until Standards has run there is nothing to check: skipped.
"""

from typing import ClassVar

from reqgraph.checks.base import BaseCheck, CheckContext, CheckSkipped, Finding
from reqgraph.checks.registry import register
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import SectionNode
from reqgraph.standards import load_structure
from reqgraph.standards.content import llm_texts, section_text


class DocumentSections(BaseCheck):
    group = "tpl"
    owner = "standards"
    template: ClassVar[str]
    standard: ClassVar[str]  # its name in reqgraph.yaml: project.standards
    document: ClassVar[str]  # how the messages call the document

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        info = ctx.project.config.project
        if info.standards and self.standard not in info.standards:
            raise CheckSkipped(
                f"проекту не нужен документ {self.document}: {self.standard} нет в "
                "reqgraph.yaml (project.standards)"
            )
        if not any(isinstance(n, SectionNode) for n in graph.nodes_of("SEC")):
            raise CheckSkipped(
                f"разделы {self.document} ещё не собраны: текст пишет Standards в прогоне, "
                "файлы — reqgraph export"
            )
        llm = llm_texts(graph)
        found = []
        for section in load_structure(self.template).required:
            text, _ = section_text(
                section, graph, llm, project_name=info.name, project_id=info.id, langs=info.langs
            )
            if text.strip():
                continue
            found.append(
                self.finding(
                    "error",
                    [section.id],
                    f"{section.id} «{section.title}»: раздел не заполнен",
                    hint="заполните раздел: Standards — из графа и брифа; пусто, если в графе "
                    f"нет узлов для него ({section.fill})",
                )
            )
        return found


@register
class SrsSections(DocumentSections):
    id = "TPL-001"
    title = "разделы SRS заполнены"
    template = "iso29148_srs"
    standard = "iso29148"
    document = "SRS"


@register
class TzSections(DocumentSections):
    id = "TPL-002"
    title = "разделы ТЗ по ГОСТ 34.602 заполнены"
    template = "gost34_602"
    standard = "gost34_602"
    document = "ТЗ"
