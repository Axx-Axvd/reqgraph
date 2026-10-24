"""Modeler (03_agents, T-203): functional requirements -> processes (JSON DSL) and the ERD.

The model fills ModelerDraft: processes almost in our DSL (flows as objects, no process id) and
entities as tables with columns. Code does the rest: process and entity ids (the same counters
apply() uses), the DBML text with `Note: 'ENT-xx · Название'` (render_dbml), realized_by links from
`realizes`. Before handing in, the Modeler runs our fast checks on its own models and, if they
find errors, tries again with their messages: at most MAX_ATTEMPTS answers (T-203).
"""

import json
import re
from dataclasses import dataclass, field, replace
from typing import Any

from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict, Field

from reqgraph.agents.common import Attempt, diff_summary, guarded, start
from reqgraph.agents.prompts import load_prompt
from reqgraph.agents.runtime import RunContext
from reqgraph.agents.state import BudgetState, RepairTask, RunState
from reqgraph.checks.base import Finding
from reqgraph.checks.registry import all_checks
from reqgraph.checks.runner import run_checks
from reqgraph.dsl.dbml import Column, DataModel, Relation, Table, entities, parse_dbml, render_dbml
from reqgraph.dsl.process import DslError, parse_process
from reqgraph.graph.edges import Rel
from reqgraph.graph.errors import GraphError
from reqgraph.graph.graph import ApplyResult, ArtifactGraph
from reqgraph.graph.ids import IdAllocator
from reqgraph.graph.nodes import EntityNode, FunctionalReq, NodeKind, ProcessNode, UserReq
from reqgraph.graph.patch import AddOp, GraphPatch, LinkOp, Op, RemoveOp, UnlinkOp, UpdateOp
from reqgraph.graph.store.project import Project
from reqgraph.llm.router import BudgetExceeded

ERD_FILE = "models/data/erd.dbml"
ERD_HEADER = (
    "Модель данных проекта. СОБРАНО reqgraph из ответа Modeler (T-203).\n"
    "Id и русское название сущности графа — в Note таблицы (ENT-xx · Название)."
)
MAX_ATTEMPTS = 3  # T-203: SCH-002 is clean after at most 3 answers
SELF_CHECKS = ("SCH-001", "SCH-002", "SCH-003", "SND-001", "SND-003", "SND-004", "TRC-002")
_TABLE = re.compile(r"^[a-z][a-z0-9_]*$")


class _Draft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class DraftElement(_Draft):
    id: str = Field(description="local id: S, E1, T01, G01, W01, M01")
    type: str = Field(
        description="start, end, task, user_task, service_task, timer, message, xor, and, "
        "event_based"
    )
    name: str = ""
    lane: str | None = None
    realizes: list[str] = Field(default_factory=list, description="FR ids, tasks only")
    event: str | None = Field(default=None, description="start only: timer or message")
    timer: str | None = Field(default=None, description="timer and timer start: when it fires")


class DraftFlow(_Draft):
    src: str
    dst: str
    label: str = Field(default="", description="xor branches: да / нет / условие")


class DraftProcess(_Draft):
    ref: str = Field(description="new: a short latin key (prc_booking); existing: its id PRC-01")
    name: str
    refines: list[str] = Field(default_factory=list, description="UR ids")
    lanes: list[str] = Field(default_factory=list)
    nodes: list[DraftElement]
    flows: list[DraftFlow] = Field(default_factory=list)


class DraftColumn(_Draft):
    name: str
    type: str = "varchar"
    pk: bool = False
    not_null: bool = False
    unique: bool = False
    note: str | None = None
    ref: str | None = Field(default=None, description="foreign key: table.column")


class DraftEntity(_Draft):
    ref: str = Field(description="new: a short latin key (ent_visit); existing: its id ENT-02")
    name: str = Field(description="Russian name of the entity, as the FRs say it: Запись")
    table: str = Field(description="table name, latin snake_case: booking")
    columns: list[DraftColumn]
    realizes: list[str] = Field(default_factory=list, description="FR ids")


class Removal(_Draft):
    id: str
    reason: str


class ModelerDraft(_Draft):
    processes: list[DraftProcess] = Field(default_factory=list)
    entities: list[DraftEntity] = Field(default_factory=list)
    remove: list[Removal] = Field(default_factory=list, description="repair tasks only")


@dataclass
class ModelUpdate:
    patch: GraphPatch
    files: dict[str, str] = field(default_factory=dict)  # model texts changed by the draft
    dropped: list[str] = field(default_factory=list)
    ids: dict[str, str] = field(default_factory=dict)  # draft ref -> id


def erd_file(files: dict[str, str]) -> str:
    """The ERD of the project: the first DBML file under models/data, else the default path."""
    found = sorted(r for r in files if r.startswith("models/data/") and r.endswith(".dbml"))
    return found[0] if found else ERD_FILE


def _process_dsl(item: DraftProcess, process_id: str) -> dict[str, Any]:
    return {
        "dsl_version": 1,
        "id": process_id,
        "name": item.name,
        "refines": item.refines,
        "lanes": item.lanes,
        "nodes": [
            e.model_dump(exclude_none=True, exclude_defaults=True) | {"id": e.id, "type": e.type}
            for e in item.nodes
        ],
        "flows": [[f.src, f.dst, f.label] if f.label else [f.src, f.dst] for f in item.flows],
    }


def to_models(draft: ModelerDraft, graph: ArtifactGraph, files: dict[str, str]) -> ModelUpdate:
    """Draft -> GraphPatch and the new ERD text. Ids are predicted with the allocator apply()
    uses, in the order of the add operations, so the DSL, the DBML notes and the realized_by
    links can carry the real ids."""
    update = ModelUpdate(GraphPatch(ops=[]))
    ops: list[Op] = []
    allocator = IdAllocator.from_graph(graph)
    links: set[tuple[str, str]] = set()  # (FR, element)

    def known_fr(fr: str, label: str) -> bool:
        if isinstance(graph.get(fr), FunctionalReq):
            return True
        update.dropped.append(f"{label}: {fr} — такого ФТ нет")
        return False

    for item in draft.processes:
        existing = graph.get(item.ref)
        if existing is not None and not isinstance(existing, ProcessNode):
            update.dropped.append(f"{item.ref}: это не процесс")
            continue
        process_id = item.ref if existing is not None else allocator.fork().allocate(NodeKind.PRC)
        refines = [u for u in item.refines if isinstance(graph.get(u), UserReq)]
        dropped_refines = sorted(set(item.refines) - set(refines))
        if dropped_refines:
            update.dropped.append(
                f"{item.ref}: refines {', '.join(dropped_refines)} — таких ПТ нет"
            )
        dsl = _process_dsl(item.model_copy(update={"refines": refines}), process_id)
        try:
            process = parse_process(dsl)
        except DslError as exc:
            update.dropped.append(
                str(exc).replace(f"процесс {process_id}", f"процесс {item.ref}", 1)
            )
            continue
        if existing is None:
            allocator.allocate(NodeKind.PRC)
            ops.append(
                AddOp(
                    op="add",
                    kind=NodeKind.PRC,
                    tmp_id=f"p{len(ops)}",
                    fields={"name": item.name, "dsl": dsl},
                )
            )
        else:
            ops.append(UpdateOp(op="update", id=process_id, fields={"name": item.name, "dsl": dsl}))
            old = existing.dsl or {}
            gone = {f"{process_id}.{e['id']}" for e in old.get("nodes", [])} - {
                f"{process_id}.{e.id}" for e in process.nodes
            }
            for edge in graph.edges:
                if edge.rel is Rel.REALIZED_BY and edge.dst in gone:
                    ops.append(
                        UnlinkOp.model_validate(
                            {"op": "unlink", "from": edge.src, "rel": "realized_by", "to": edge.dst}
                        )
                    )
        update.ids[item.ref] = process_id
        for element in process.nodes:
            for fr in element.realizes:
                if known_fr(fr, f"{item.ref}.{element.id}"):
                    links.add((fr, f"{process_id}.{element.id}"))

    erd_rel = erd_file(files)
    current = parse_dbml(files[erd_rel], erd_rel) if erd_rel in files else DataModel((), (), {})
    tables = {t.name: t for t in current.tables}
    by_id = {t.entity_id: t.name for t in current.tables if t.entity_id}
    relations = [r for r in current.relations]
    changed_erd = False
    for ent in draft.entities:
        existing = graph.get(ent.ref)
        if existing is not None and not isinstance(existing, EntityNode):
            update.dropped.append(f"{ent.ref}: это не сущность")
            continue
        if not _TABLE.fullmatch(ent.table):
            update.dropped.append(f"{ent.ref}: имя таблицы «{ent.table}» — латиница в snake_case")
            continue
        if existing is None:
            if ent.table in tables:
                update.dropped.append(f"{ent.ref}: таблица {ent.table} уже есть, укажите её ENT-id")
                continue
            entity_id = allocator.allocate(NodeKind.ENT)
        else:
            entity_id = ent.ref
            old_name = by_id.get(entity_id)
            if old_name is not None:
                tables.pop(old_name, None)
                relations = [r for r in relations if r.src_table != old_name]
        columns = tuple(
            Column(c.name, c.type, pk=c.pk, not_null=c.not_null, unique=c.unique, note=c.note)
            for c in ent.columns
        )
        tables[ent.table] = Table(ent.table, columns, note=f"{entity_id} · {ent.name}")
        for column in ent.columns:
            if column.ref:
                dst_table, _, dst_column = column.ref.partition(".")
                relations.append(
                    Relation(ent.table, (column.name,), ">", dst_table, (dst_column or "id",))
                )
        update.ids[ent.ref] = entity_id
        changed_erd = True
        for fr in ent.realizes:
            if known_fr(fr, ent.ref):
                links.add((fr, entity_id))

    removed = {r.id for r in draft.remove}
    for removal in draft.remove:
        ops.append(RemoveOp(op="remove", id=removal.id, reason=removal.reason))
        if removal.id in by_id:
            name = by_id[removal.id]
            tables.pop(name, None)
            relations = [r for r in relations if name not in (r.src_table, r.dst_table)]
            changed_erd = True

    if changed_erd:
        model = DataModel(tuple(tables.values()), tuple(relations), dict(current.enums))
        text = render_dbml(model, header=ERD_HEADER)
        try:
            new_entities = {e.id: e for e in entities(parse_dbml(text, erd_rel), erd_rel)}
        except DslError as exc:
            update.dropped.append(str(exc))
            new_entities = None
        if new_entities is not None:
            update.files[erd_rel] = text
            old_entities = {e.id for e in graph.nodes_of(NodeKind.ENT)}
            adds = sorted((i for i in new_entities if i not in old_entities), key=_number)
            for new_id in adds:  # same order as the allocator issued them
                node = new_entities[new_id]
                fields = node.model_dump(mode="json", exclude={"id", "kind"}, exclude_defaults=True)
                ops.append(AddOp(op="add", kind=NodeKind.ENT, tmp_id=f"e{len(ops)}", fields=fields))
            for old_id, node in new_entities.items():
                if old_id in old_entities and graph.get(old_id) != node:
                    fields = node.model_dump(mode="json", include={"name", "attributes"})
                    ops.append(UpdateOp(op="update", id=old_id, fields=fields))
            for lost in old_entities - set(new_entities) - removed:
                update.dropped.append(f"{lost}: таблицы нет в новой ERD — удаляют только по задаче")
        else:  # no ERD this time: the entities and their links wait for the next answer
            links = {(fr, target) for fr, target in links if not target.startswith("ENT-")}
            update.ids = {r: i for r, i in update.ids.items() if not i.startswith("ENT-")}

    existing_links = {(e.src, e.dst) for e in graph.edges if e.rel is Rel.REALIZED_BY}
    for fr, target in sorted(links - existing_links):
        ops.append(
            LinkOp.model_validate({"op": "link", "from": fr, "rel": "realized_by", "to": target})
        )
    update.patch = GraphPatch(ops=_ordered(ops))
    return update


def _number(entity_id: str) -> int:
    return int(entity_id.rsplit("-", 1)[1])


def _ordered(ops: list[Op]) -> list[Op]:
    """apply() issues ids in the order of the add operations: processes first, then entities —
    the same order to_models() predicted them in."""
    adds = [o for o in ops if isinstance(o, AddOp)]
    adds.sort(key=lambda o: (o.kind is not NodeKind.PRC, _seq(o)))
    return adds + [o for o in ops if not isinstance(o, AddOp)]


def _seq(op: AddOp) -> int:
    return int(op.tmp_id[1:])


# --- the node ---------------------------------------------------------------------------------


def _requirements(graph: ArtifactGraph) -> list[str]:
    lines = []
    for kind in ("UR", "FR"):
        for node in graph.nodes_of(kind):
            text = f"{node.id}: {getattr(node, 'title', '')} — {getattr(node, 'statement', '')}"
            if isinstance(node, FunctionalReq) and node.acceptance:
                text += " | приёмка: " + "; ".join(node.acceptance)
            if isinstance(node, UserReq) and node.scenario:
                text += " | сценарий: " + "; ".join(node.scenario)
            lines.append(text)
    return lines


def _processes(graph: ArtifactGraph) -> list[str]:
    return [
        json.dumps(n.dsl, ensure_ascii=False)
        for n in graph.nodes_of("PRC")
        if isinstance(n, ProcessNode) and n.dsl is not None
    ]


def render(state: RunState, files: dict[str, str], tasks: list[RepairTask]) -> str:
    erd = files.get(erd_file(files), "")
    return load_prompt("modeler/model").render(
        requirements=_requirements(state["graph"]),
        processes=_processes(state["graph"]),
        erd=erd,
        tasks=tasks,
    )


def candidate(ctx: RunContext, graph: ArtifactGraph, files: dict[str, str]) -> Project:
    """The project with the Modeler's attempt: what its own checks run on."""
    return replace(ctx.project, graph=graph, files=files, warnings=[])


@dataclass
class _Try:
    number: int
    draft: ModelerDraft
    attempt: Attempt
    files: dict[str, str]
    result: ApplyResult | None = None
    problems: list[str] = field(default_factory=list)
    errors: int = 0


def _problems(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.check_id in SELF_CHECKS and f.severity != "info"]


async def modeler(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = start(runtime, "modeler")
    if state["stop"] is not None:
        return {}
    mine = [t for t in state["tasks"] if t.owner == "modeler"]
    rest = [t for t in state["tasks"] if t.owner != "modeler"]
    if state["iteration"] > 0 and not mine:
        ctx.events.emit("skip", agent="modeler", reason="нет задач ремонта")
        return {}
    graph = state["graph"]
    files = ctx.project.files | state["files"]
    prompt = render(state, files, mine)
    template = load_prompt("modeler/model")
    checks = [c for c in all_checks() if c.id in SELF_CHECKS]
    budget: BudgetState = state["budget"]
    tries: list[_Try] = []
    text = prompt
    try:
        for number in range(1, MAX_ATTEMPTS + 1):
            draft, budget = await ctx.ask("modeler", text, ModelerDraft, budget, template=template)
            update = to_models(draft, graph, files)
            current = _Try(
                number,
                draft,
                guarded(update.patch, graph, "modeler", mine, update.dropped),
                files | update.files,
            )
            try:
                current.result = graph.apply(current.attempt.patch, actor="agent")
            except GraphError as exc:
                current.problems = [str(exc)]
                current.errors = 1
            if current.result is not None and set(update.ids.values()) - set(
                current.result.graph.nodes
            ):
                # an add was dropped by the guard: the ids to_models() predicted no longer hold
                current.problems = [*current.attempt.dropped, "id моделей разошлись после отсева"]
                current.errors = len(current.problems)
                current.result = None
            if current.result is not None:
                report = await run_checks(
                    candidate(ctx, current.result.graph, current.files), checks, offline=True
                )
                found = _problems(report.findings)
                current.problems = current.attempt.dropped + [
                    f"{f.check_id}: {f.message}" for f in found
                ]
                current.errors = len(current.attempt.dropped) + sum(
                    f.severity == "error" for f in found
                )
            tries.append(current)
            ctx.events.emit(
                "self_check", agent="modeler", attempt=number, problems=current.problems
            )
            if not current.problems:
                break
            if number < MAX_ATTEMPTS:
                text = (
                    prompt
                    + "\n\n"
                    + load_prompt("modeler/retry").render(
                        answer=draft.model_dump_json(exclude_defaults=True),
                        problems=current.problems,
                    )
                )
    except BudgetExceeded:
        ctx.events.emit("stop", reason="budget", node="modeler")
        if not any(t.result is not None for t in tries):
            return {"stop": "budget", "tasks": rest, "budget": budget}
        stop: dict[str, Any] = {"stop": "budget"}
    else:
        stop = {}
    update_state: dict[str, Any] = {"budget": budget, "tasks": rest} | stop
    applied = [t for t in tries if t.result is not None]
    if not applied:
        ctx.events.emit("patch_rejected", agent="modeler", error="; ".join(tries[-1].problems))
        return update_state
    best = min(applied, key=lambda t: (t.errors, len(t.problems), -t.number))
    assert best.result is not None
    if best.problems:
        ctx.events.emit("dropped", agent="modeler", reasons=best.problems)
    ctx.events.emit(
        "agent_end", agent="modeler", attempts=len(tries), diff=diff_summary(best.result.diff)
    )
    changed = {r: t for r, t in best.files.items() if ctx.project.files.get(r) != t}
    return update_state | {"graph": best.result.graph, "files": state["files"] | changed}
