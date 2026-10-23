"""SCH-001…005: models are valid — BPMN by the XSD, the process DSL, DBML, PlantUML, Structurizr."""

from reqgraph.checks.base import BaseCheck, CheckContext, CheckSkipped, Finding
from reqgraph.checks.registry import register
from reqgraph.dsl.bpmn_compile import compile_bpmn
from reqgraph.dsl.bpmn_xsd import validate_bpmn
from reqgraph.dsl.process import DslError
from reqgraph.graph.graph import ArtifactGraph


@register
class BpmnXsd(BaseCheck):
    id = "SCH-001"
    title = "BPMN валиден по XSD BPMN 2.0"
    group = "sch"
    owner = "modeler"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        found = []
        for process_id, dsl in ctx.processes().items():
            if isinstance(dsl, DslError):
                continue  # SCH-002 reports it
            errors = validate_bpmn(compile_bpmn(dsl))
            if errors:
                text = "; ".join(errors[:3])
                found.append(
                    self.finding(
                        "error",
                        [process_id],
                        f"{process_id}: BPMN не проходит XSD: {text}",
                        hint="ошибка компилятора при корректном DSL — сообщите разработчику",
                    )
                )
        return found


@register
class ProcessDsl(BaseCheck):
    id = "SCH-002"
    title = "DSL процесса валиден, ссылки realizes и refines существуют"
    group = "sch"
    owner = "modeler"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        found = []
        for process_id, dsl in ctx.processes().items():
            if isinstance(dsl, DslError):
                found.append(
                    self.finding(
                        "error", [process_id], str(dsl), hint="исправьте JSON DSL процесса"
                    )
                )
                continue
            for element in dsl.nodes:
                for fr in element.realizes:
                    if graph.get(fr) is None:
                        found.append(
                            self.finding(
                                "error",
                                [f"{process_id}.{element.id}"],
                                f"{process_id}.{element.id}: realizes ссылается на {fr}, его нет",
                                hint="уберите ссылку или добавьте требование",
                            )
                        )
            for ur in dsl.refines:
                if graph.get(ur) is None:
                    found.append(
                        self.finding(
                            "error",
                            [process_id],
                            f"{process_id}: refines ссылается на {ur}, его нет",
                        )
                    )
        return found


@register
class DbmlParses(BaseCheck):
    id = "SCH-003"
    title = "DBML разбирается"
    group = "sch"
    owner = "modeler"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        model = ctx.data_model()
        if isinstance(model, DslError):
            return [self.finding("error", [], str(model), hint="исправьте синтаксис DBML")]
        return []


class _KrokiCompiles(BaseCheck):
    """A model file compiles when Kroki draws it; without network the check is skipped."""

    suffix: str
    notation: str

    async def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        files = ctx.model_files(self.suffix)
        found, offline = [], []
        for rel in files:
            result = await ctx.svg(rel)
            if result.offline:
                offline.append(rel)
            elif not result.ok:
                found.append(
                    self.finding(
                        "error",
                        [],
                        f"{rel}: {self.notation} не компилируется: {result.error}",
                        hint="исправьте строку, указанную в ошибке",
                    )
                )
        if offline and len(offline) == len(files):
            raise CheckSkipped(f"Kroki недоступен, {self.notation} не проверен")
        return found


@register
class PlantUmlCompiles(_KrokiCompiles):
    id = "SCH-004"
    title = "PlantUML компилируется"
    group = "sch"
    owner = "modeler"
    suffix = ".puml"
    notation = "PlantUML"


@register
class StructurizrCompiles(_KrokiCompiles):
    id = "SCH-005"
    title = "Structurizr DSL компилируется"
    group = "sch"
    owner = "modeler"
    suffix = ".dsl"
    notation = "Structurizr DSL"
