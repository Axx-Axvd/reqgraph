"""TPL-001: required SRS sections are filled (own structure standards/iso29148_srs.yaml, ADR-012).

TPL-002 (TZ by GOST 34.602) comes with the TZ exporter (T-402, T-404).
"""

from reqgraph.checks.base import BaseCheck, CheckContext, CheckSkipped, Finding
from reqgraph.checks.registry import register
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import SectionNode
from reqgraph.standards import load_structure


@register
class SrsSections(BaseCheck):
    id = "TPL-001"
    title = "разделы SRS заполнены"
    group = "tpl"
    owner = "standards"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        standards = ctx.project.config.project.standards
        if standards and "iso29148" not in standards:
            raise CheckSkipped(
                "проекту не нужна SRS по iso29148 (reqgraph.yaml: project.standards)"
            )
        sections = {n.id: n for n in graph.nodes_of("SEC") if isinstance(n, SectionNode)}
        if not sections:
            raise CheckSkipped(
                "разделы SRS ещё не собраны: их пишет Standards в прогоне, файлы — экспорт (S4)"
            )
        structure = load_structure("iso29148_srs")
        return [
            self.finding(
                "error",
                [section.id],
                f"{section.id} «{section.title}»: раздел не заполнен",
                hint="заполните раздел: Standards — из графа и брифа; пусто, если в графе "
                f"нет узлов для него ({section.fill})",
            )
            for section in structure.required
            if section.id not in sections or not sections[section.id].text.strip()
        ]
