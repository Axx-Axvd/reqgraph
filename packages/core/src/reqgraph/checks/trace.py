"""TRC-001…006: traceability — BR → UR → FR → model elements, sources in the interview, references
resolve and the DSL `realizes` mirrors `realized_by` of the requirements (REVIEW.md of garage61)."""

import networkx as nx
from rapidfuzz import fuzz

from reqgraph.checks.base import BaseCheck, CheckContext, CheckSkipped, Finding
from reqgraph.checks.registry import register
from reqgraph.checks.text import REQUIREMENT_KINDS, words
from reqgraph.dsl.process import TASKS, DslError, ProcessDSL
from reqgraph.graph.edges import Edge, Rel, split_ref
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import C4Node, EntityNode, FunctionalReq, InterviewTurn

_FUZZY_MIN = 85


def _edges(graph: ArtifactGraph, rel: Rel) -> list[Edge]:
    return [e for e in graph.edges if e.rel is rel]


def _processes(ctx: CheckContext) -> dict[str, ProcessDSL]:
    return {k: v for k, v in ctx.processes().items() if not isinstance(v, DslError)}


@register
class BrRefined(BaseCheck):
    id = "TRC-001"
    title = "каждое БТ уточнено ПТ"
    group = "trc"
    owner = "analyst"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        refined = {e.dst for e in _edges(graph, Rel.REFINES)}
        return [
            self.finding(
                "error",
                [br.id],
                f"{br.id}: ни одно пользовательское требование его не уточняет",
                hint="добавьте UR с refines: [" + br.id + "] или уберите БТ",
            )
            for br in graph.nodes_of("BR")
            if br.id not in refined
        ]


@register
class FrRealized(BaseCheck):
    id = "TRC-002"
    title = "каждое ФТ реализовано в модели"
    group = "trc"
    owner = "modeler"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        realized = {e.src for e in _edges(graph, Rel.REALIZED_BY)}
        return [
            self.finding(
                "error",
                [fr.id],
                f"{fr.id}: не реализовано ни одним элементом модели",
                hint="добавьте realized_by: задачу процесса, сущность, сценарий или контейнер C4",
            )
            for fr in graph.nodes_of("FR")
            if fr.id not in realized
        ]


@register
class NoOrphans(BaseCheck):
    id = "TRC-003"
    title = "нет сирот в моделях"
    group = "trc"
    owner = "modeler"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        """Process tasks, entities, use cases, C4 containers and external systems; not events,
        gateways, actors, C4-SYS or attributes (REVIEW.md of garage61, No. 4)."""
        targets = {e.dst for e in _edges(graph, Rel.REALIZED_BY)}
        parents = {split_ref(t)[0] for t in targets}
        elements = [n.id for n in graph.nodes_of("ENT")] + [n.id for n in graph.nodes_of("UC")]
        elements += [
            n.id
            for n in graph.nodes_of("C4")
            if isinstance(n, C4Node) and n.c4_kind in ("container", "external")
        ]
        orphans = [e for e in elements if e not in parents]
        for pid, dsl in _processes(ctx).items():
            orphans += [
                f"{pid}.{el.id}"
                for el in dsl.nodes
                if el.type in TASKS and f"{pid}.{el.id}" not in targets
            ]
        return [
            self.finding(
                "warning",
                [ref],
                f"{ref}: элемент модели не реализует ни одного требования",
                hint="свяжите его с ФТ (realized_by) или удалите из модели",
            )
            for ref in orphans
        ]


@register
class ReferencesResolve(BaseCheck):
    id = "TRC-004"
    title = "все ссылки разрешаются, нет циклов, realizes = realized_by"
    group = "trc"
    owner = "analyst"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        """Nodes themselves are checked when the graph is built (T-101): here — sub-elements
        (PRC-01.T05, ENT-05.status), cycles of refines / depends_on and the DSL mirror."""
        found: list[Finding] = []
        processes = _processes(ctx)
        for edge in graph.edges:
            parent, sub = split_ref(edge.dst)
            if sub is None:
                continue
            node = graph.get(parent)
            if parent in processes:
                known = {el.id for el in processes[parent].nodes}
            elif isinstance(node, EntityNode):
                known = {a.name for a in node.attributes}
            else:
                continue  # a process whose DSL does not parse: SCH-002
            if sub not in known:
                found.append(
                    self.finding(
                        "error",
                        [edge.src, edge.dst],
                        f"{edge.src}: ссылка {edge.dst} — в {parent} нет элемента {sub}",
                        hint="исправьте id элемента или добавьте его в модель",
                    )
                )
        for rel in (Rel.REFINES, Rel.DEPENDS_ON):
            chain = nx.DiGraph([(e.src, e.dst) for e in _edges(graph, rel)])
            for cycle in sorted(sorted(c) for c in nx.simple_cycles(chain)):
                found.append(
                    self.finding(
                        "error",
                        cycle,
                        f"цикл {rel.value}: {' → '.join(cycle)}",
                        hint="требование не может уточнять (или зависеть от) само себя",
                    )
                )
        found += self._mirror(graph, processes)
        return found

    def _mirror(self, graph: ArtifactGraph, processes: dict[str, ProcessDSL]) -> list[Finding]:
        """`realizes` of a process step and `realized_by` of the requirement must agree."""
        edges = {(e.src, e.dst) for e in _edges(graph, Rel.REALIZED_BY)}
        found = []
        for pid, dsl in processes.items():
            for el in dsl.nodes:
                ref = f"{pid}.{el.id}"
                for fr in el.realizes:
                    if graph.get(fr) is not None and (fr, ref) not in edges:
                        found.append(
                            self.finding(
                                "error",
                                [fr, ref],
                                f"{ref}: в DSL realizes {fr}, а у {fr} нет realized_by {ref}",
                                hint=f"добавьте {ref} в realized_by у {fr} (главная запись — "
                                "в требовании)",
                            )
                        )
            for fr, target in sorted(edges):
                parent, sub = split_ref(target)
                if parent != pid or sub is None:
                    continue
                element = next((e for e in dsl.nodes if e.id == sub), None)
                if element is not None and fr not in element.realizes:
                    found.append(
                        self.finding(
                            "error",
                            [fr, target],
                            f"{fr}: realized_by {target}, а в DSL у {target} нет realizes {fr}",
                            hint=f"добавьте «{fr}» в realizes шага {sub} процесса {pid}",
                        )
                    )
        return found


@register
class EntitiesInErd(BaseCheck):
    id = "TRC-005"
    title = "сущности из ФТ есть в ERD"
    group = "trc"
    owner = "modeler"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        """An FR realized by an entity should speak about it: the entity name (in Russian) is
        found among the words of the FR (lemmas, rapidfuzz ≥ 85)."""
        entities = {n.id: n for n in graph.nodes_of("ENT") if isinstance(n, EntityNode)}
        russian = {
            i: n for i, n in entities.items() if any("а" <= c <= "я" for c in n.name.lower())
        }
        if not russian:
            raise CheckSkipped(
                "у сущностей ERD нет русских названий — сравнивать формулировки ФТ не с чем"
            )
        found = []
        for fr in graph.nodes_of("FR"):
            assert isinstance(fr, FunctionalReq)
            mine = [
                e.dst
                for e in _edges(graph, Rel.REALIZED_BY)
                if e.src == fr.id and split_ref(e.dst)[0] in russian
            ]
            lemmas = [w.lemma for w in words(fr.statement)]
            for entity_id in mine:
                name = " ".join(w.lemma for w in words(russian[entity_id].name))
                if not any(fuzz.ratio(name, lemma) >= _FUZZY_MIN for lemma in lemmas):
                    found.append(
                        self.finding(
                            "warning",
                            [fr.id, entity_id],
                            f"{fr.id}: реализуется сущностью {entity_id} "
                            f"«{russian[entity_id].name}», но в формулировке она не названа",
                        )
                    )
        return found


@register
class HasSource(BaseCheck):
    id = "TRC-006"
    title = "у требования есть источник"
    group = "trc"
    owner = "analyst"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        sources: dict[str, list[str]] = {}
        for edge in _edges(graph, Rel.DERIVED_FROM):
            sources.setdefault(edge.src, []).append(edge.dst)
        found = []
        for kind in REQUIREMENT_KINDS:
            for node in graph.nodes_of(kind):
                turns = sources.get(node.id, [])
                if not turns and not node.assumption:
                    found.append(
                        self.finding(
                            "error",
                            [node.id],
                            f"{node.id}: нет источника — ни реплики интервью, ни пометки допущения",
                            hint="добавьте derived_from: [TURN-…] или assumption: true",
                        )
                    )
                elif turns and not any(
                    isinstance(t := graph.get(turn), InterviewTurn) and t.role == "client"
                    for turn in turns
                ):
                    found.append(
                        self.finding(
                            "error",
                            [node.id, *turns],
                            f"{node.id}: источник — только вопросы аналитика, а не слова заказчика",
                            hint="сошлитесь на ответ заказчика (role: client)",
                        )
                    )
        return found
