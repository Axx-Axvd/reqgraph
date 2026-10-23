"""SND-001…004: processes are correct — reachable, sound, sensible gateways, one page each."""

import networkx as nx

from reqgraph.checks.base import BaseCheck, CheckContext, Finding
from reqgraph.checks.registry import register
from reqgraph.dsl.layout import MIN_FONT_PT, extent, layout, page_font_pt
from reqgraph.dsl.process import DslError, ProcessDSL
from reqgraph.graph.graph import ArtifactGraph


def _parsed(ctx: CheckContext) -> dict[str, ProcessDSL]:
    """Processes that parse; broken ones are reported by SCH-002."""
    return {k: v for k, v in ctx.processes().items() if not isinstance(v, DslError)}


def _graph(dsl: ProcessDSL) -> "nx.DiGraph[str]":
    flow = nx.DiGraph()
    flow.add_nodes_from(e.id for e in dsl.nodes)
    flow.add_edges_from((f.src, f.dst) for f in dsl.flow_list())
    return flow


@register
class Reachable(BaseCheck):
    id = "SND-001"
    title = "все шаги достижимы от старта и ведут к концу"
    group = "snd"
    owner = "modeler"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        found = []
        for pid, dsl in _parsed(ctx).items():
            flow = _graph(dsl)
            starts = [e.id for e in dsl.nodes if e.type == "start"]
            ends = [e.id for e in dsl.nodes if e.type == "end"]
            if not starts or not ends:
                missing = "стартового события" if not starts else "конечного события"
                found.append(self.finding("error", [pid], f"{pid}: нет {missing}"))
                continue
            reached = set(starts).union(*(nx.descendants(flow, s) for s in starts))
            finishing = set(ends).union(*(nx.ancestors(flow, e) for e in ends))
            for element in dsl.nodes:
                ref = f"{pid}.{element.id}"
                if element.id not in reached:
                    found.append(
                        self.finding(
                            "error",
                            [ref],
                            f"{ref}: шаг недостижим от старта",
                            hint="добавьте стрелку, ведущую к шагу, или удалите шаг",
                        )
                    )
                elif element.id not in finishing:
                    found.append(
                        self.finding(
                            "error",
                            [ref],
                            f"{ref}: от шага нельзя дойти до конца процесса",
                            hint="добавьте стрелку к следующему шагу или к конечному событию",
                        )
                    )
        return found


@register
class Sound(BaseCheck):
    id = "SND-002"
    title = "процесс sound (сеть Петри: всегда завершается, ничего не зависает)"
    group = "snd"
    owner = "modeler"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        from reqgraph.dsl.soundness import is_sound  # pm4py: heavy, imported only here

        found = []
        reachable_ok = {f.node_ids[0].split(".")[0] for f in Reachable().run(graph, ctx)}
        for pid, dsl in _parsed(ctx).items():
            if pid in reachable_ok:
                continue  # SND-001 already names the broken steps
            if not is_sound(dsl):
                found.append(
                    self.finding(
                        "error",
                        [pid],
                        f"{pid}: процесс не sound — возможен тупик или зависание "
                        "(например, параллельные ветки сведены через «или»)",
                        hint="парные шлюзы: and-разветвление закрывайте and-слиянием, xor — xor",
                    )
                )
        return found


@register
class Gateways(BaseCheck):
    id = "SND-003"
    title = "шлюзы корректны"
    group = "snd"
    owner = "modeler"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        found = []
        for pid, dsl in _parsed(ctx).items():
            flows = dsl.flow_list()
            types = {e.id: e.type for e in dsl.nodes}
            joins_and = False
            splits_and = []
            for element in dsl.nodes:
                if element.type not in ("xor", "and", "event_based"):
                    continue
                ref = f"{pid}.{element.id}"
                out = [f for f in flows if f.src == element.id]
                into = [f for f in flows if f.dst == element.id]
                if len(out) < 2 and len(into) < 2:
                    found.append(
                        self.finding(
                            "warning", [ref], f"{ref}: шлюз ничего не разветвляет и не сводит"
                        )
                    )
                if element.type == "xor" and len(out) >= 2:
                    unlabeled = [f.dst for f in out if not f.label]
                    if unlabeled:
                        found.append(
                            self.finding(
                                "warning",
                                [ref],
                                f"{ref}: у веток к {', '.join(unlabeled)} нет подписи условия",
                                hint='подпишите ветки: ["G01", "T04", "да"]',
                            )
                        )
                if element.type == "event_based":
                    wrong = [f.dst for f in out if types[f.dst] not in ("timer", "message")]
                    if len(out) < 2 or wrong:
                        found.append(
                            self.finding(
                                "warning",
                                [ref],
                                f"{ref}: после событийного шлюза должны идти минимум два события "
                                "«таймер» или «сообщение»",
                            )
                        )
                if element.type == "and":
                    joins_and = joins_and or len(into) >= 2
                    if len(out) >= 2:
                        splits_and.append(ref)
            if splits_and and not joins_and:
                found.append(
                    self.finding(
                        "warning",
                        splits_and,
                        f"{pid}: параллельные ветки ({', '.join(splits_and)}) нигде не сводятся "
                        "and-шлюзом",
                    )
                )
        return found


@register
class OnePage(BaseCheck):
    id = "SND-004"
    title = "процесс помещается на одну страницу"
    group = "snd"
    owner = "modeler"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        found = []
        for pid, dsl in _parsed(ctx).items():
            drawing = layout(dsl)
            font = page_font_pt(drawing)
            if font < MIN_FONT_PT:
                width, _ = extent(drawing)
                found.append(
                    self.finding(
                        "warning",
                        [pid],
                        f"{pid}: на альбомном листе А4 текст схемы будет {font} pt "
                        f"(минимум {MIN_FONT_PT:g} pt, ширина схемы {width} px)",
                        hint="разбейте процесс на несколько процессов поменьше",
                    )
                )
        return found
