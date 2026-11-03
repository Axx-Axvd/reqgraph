"""Modeler, second step (T-207): use cases (PlantUML) and the C4 model (Structurizr) from a form.

The model fills ViewsDraft: use cases with their actor and FRs, the system with its containers
and external systems, and the relationships between them. Code does the rest, as for the ERD
(T-203): UC and C4 ids (the same counters apply() uses), the texts of models/uml/use_cases.puml and
models/c4/workspace.dsl (dsl/plantuml.py, dsl/c4.py), the nodes read back from those texts and the
realized_by links. A separate question from processes and the ERD: a free model keeps a shorter
answer right, and this part is retried and measured on its own.
"""

from dataclasses import dataclass, field, replace

from pydantic import BaseModel, ConfigDict, Field

from reqgraph.agents.common import Attempt, guarded
from reqgraph.agents.prompts import load_prompt
from reqgraph.agents.runtime import RunContext
from reqgraph.agents.state import BudgetState, RepairTask
from reqgraph.checks.registry import all_checks
from reqgraph.checks.runner import run_checks
from reqgraph.dsl.c4 import (
    SYSTEM_ID,
    C4Model,
    Element,
    Relationship,
    parse_workspace,
    read_elements,
    render_workspace,
)
from reqgraph.dsl.plantuml import (
    UseCase,
    UseCaseModel,
    parse_use_cases,
    read_use_cases,
    render_use_cases,
)
from reqgraph.graph.edges import Rel
from reqgraph.graph.errors import GraphError
from reqgraph.graph.graph import ApplyResult, ArtifactGraph, GraphDiff
from reqgraph.graph.ids import IdAllocator
from reqgraph.graph.nodes import ActorNode, FunctionalReq, Node, NodeKind
from reqgraph.graph.patch import AddOp, GraphPatch, LinkOp, Op, RemoveOp, UpdateOp
from reqgraph.llm.router import BudgetExceeded

UML_FILE = "models/uml/use_cases.puml"
C4_FILE = "models/c4/workspace.dsl"
ROLE = "modeler_views"  # llm/roles.yaml: the Modeler's ladder
MAX_ATTEMPTS = 3  # T-207: SCH-004 and SCH-005 are clean after at most 3 answers
VIEW_CHECKS = ("SCH-004", "SCH-005", "TRC-003")
VIEW_PREFIXES = ("UC-", "C4-")


class _Draft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class DraftUseCase(_Draft):
    ref: str = Field(description="new: a short latin key (uc_book); existing: its id UC-01")
    name: str = Field(description="a goal of the actor, a verb first: Записаться на приём")
    actor: str = Field(description="ACT id of the role that starts it")
    realizes: list[str] = Field(default_factory=list, description="FR ids")
    extends: str | None = Field(default=None, description="ref or UC id of the base use case")
    includes: list[str] = Field(default_factory=list, description="refs or UC ids it always uses")


class DraftContainer(_Draft):
    ref: str = Field(description="new: a short latin key (cnt_api); existing: its id C4-CNT-01")
    name: str
    description: str = ""
    technology: str = ""
    database: bool = False
    realizes: list[str] = Field(default_factory=list, description="FR ids")


class DraftExternal(_Draft):
    ref: str = Field(description="new: a short latin key (ext_sms); existing: its id C4-EXT-01")
    name: str
    description: str = ""
    realizes: list[str] = Field(default_factory=list, description="FR ids")


class DraftLink(_Draft):
    src: str = Field(description="ACT id, system, or ref / id of a container or external system")
    dst: str
    label: str = Field(description="what happens: Записывается, Отправляет SMS")
    technology: str = ""


class DraftC4(_Draft):
    system_name: str
    system_description: str = ""
    containers: list[DraftContainer] = Field(default_factory=list)
    externals: list[DraftExternal] = Field(default_factory=list)
    links: list[DraftLink] = Field(
        default_factory=list, description="all relationships of the model; empty keeps the old"
    )


class Removal(_Draft):
    id: str
    reason: str


class ViewsDraft(_Draft):
    use_cases: list[DraftUseCase] = Field(default_factory=list)
    c4: DraftC4 | None = None
    remove: list[Removal] = Field(default_factory=list, description="repair tasks only")


@dataclass
class ViewsUpdate:
    patch: GraphPatch
    files: dict[str, str] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)
    ids: dict[str, str] = field(default_factory=dict)  # draft ref -> id


def uml_file(files: dict[str, str]) -> str:
    """The use case diagram: the first PlantUML file under models/uml with use cases."""
    found = sorted(
        r
        for r, t in files.items()
        if r.startswith("models/uml/") and r.endswith(".puml")
        if "usecase" in t
    )
    return found[0] if found else UML_FILE


def c4_file(files: dict[str, str]) -> str:
    found = sorted(r for r in files if r.startswith("models/c4/") and r.endswith(".dsl"))
    return found[0] if found else C4_FILE


def _actors(graph: ArtifactGraph) -> dict[str, ActorNode]:
    return {n.id: n for n in graph.nodes_of("ACT") if isinstance(n, ActorNode)}


def _key(node_id: str) -> tuple[str, int]:
    head, _, number = node_id.rpartition("-")
    return head, int(number) if number.isdigit() else 0


def to_views(
    draft: ViewsDraft, graph: ArtifactGraph, files: dict[str, str], *, project_name: str
) -> ViewsUpdate:
    """Draft -> GraphPatch and the new texts of the use case diagram and the C4 model."""
    update = ViewsUpdate(GraphPatch(ops=[]))
    allocator = IdAllocator.from_graph(graph)
    actors = _actors(graph)
    links: set[tuple[str, str]] = set()  # (FR, element)
    removed = {r.id for r in draft.remove}

    def realizes(frs: list[str], target: str, label: str) -> None:
        for fr in frs:
            if isinstance(graph.get(fr), FunctionalReq):
                links.add((fr, target))
            else:
                update.dropped.append(f"{label}: {fr} — такого ФТ нет")

    # --- use cases ---------------------------------------------------------------------------
    uml_rel = uml_file(files)
    uml = parse_use_cases(files[uml_rel]) if uml_rel in files else UseCaseModel("", (), (), ())
    use_cases = {u.id: u for u in uml.use_cases}
    uc_links = list(uml.links)
    uc_relations = list(uml.relations)
    refs: dict[str, str] = {}
    accepted: list[DraftUseCase] = []
    for item in draft.use_cases:
        if item.actor not in actors:
            update.dropped.append(f"{item.ref}: роль {item.actor} — такой роли нет")
            continue
        if item.ref.startswith("UC-"):
            if item.ref not in use_cases:
                update.dropped.append(f"{item.ref}: такого сценария нет")
                continue
            refs[item.ref] = item.ref
        else:
            refs[item.ref] = allocator.allocate(NodeKind.UC)
        accepted.append(item)
    for item in accepted:
        uc_id = refs[item.ref]
        use_cases[uc_id] = UseCase(uc_id, item.name)
        uc_links = [link for link in uc_links if link[1] != uc_id] + [(item.actor, uc_id)]
        uc_relations = [r for r in uc_relations if r[0] != uc_id]
        bases = [(item.extends, "extend")] if item.extends else []
        for base, kind in [*bases, *((i, "include") for i in item.includes)]:
            target = refs.get(base) or (base if base in use_cases else None)
            if target is None or target == uc_id:
                update.dropped.append(f"{item.ref}: {kind} {base} — такого сценария нет")
                continue
            uc_relations.append((uc_id, target, kind))
        realizes(item.realizes, uc_id, item.ref)
    update.ids |= refs
    for gone in removed & set(use_cases):
        del use_cases[gone]
    uc_links = [(a, u) for a, u in uc_links if a in actors and u in use_cases]
    uc_relations = [r for r in uc_relations if r[0] in use_cases and r[1] in use_cases]

    # --- C4 ---------------------------------------------------------------------------------
    c4_rel = c4_file(files)
    c4 = parse_workspace(files[c4_rel]) if c4_rel in files else None
    containers = {c.id: c for c in c4.containers} if c4 else {}
    externals = {e.id: e for e in c4.externals} if c4 else {}
    relations = list(c4.relations) if c4 else []
    system = c4.system if c4 else None
    if draft.c4 is not None:
        system = Element(SYSTEM_ID, draft.c4.system_name, draft.c4.system_description)
        names = {SYSTEM_ID: SYSTEM_ID, "system": SYSTEM_ID} | {a: a for a in actors}
        names |= {i: i for i in [*containers, *externals]}
        for c in draft.c4.containers:
            if c.ref.startswith("C4-") and c.ref not in containers:
                update.dropped.append(f"{c.ref}: такого контейнера нет")
                continue
            cid = (
                c.ref
                if c.ref in containers
                else allocator.allocate(NodeKind.C4, c4_kind="container")
            )
            names[c.ref] = update.ids[c.ref] = cid
            containers[cid] = Element(cid, c.name, c.description, c.technology, c.database)
            realizes(c.realizes, cid, c.ref)
        for e in draft.c4.externals:
            if e.ref.startswith("C4-") and e.ref not in externals:
                update.dropped.append(f"{e.ref}: такой внешней системы нет")
                continue
            eid = (
                e.ref if e.ref in externals else allocator.allocate(NodeKind.C4, c4_kind="external")
            )
            names[e.ref] = update.ids[e.ref] = eid
            externals[eid] = Element(eid, e.name, e.description)
            realizes(e.realizes, eid, e.ref)
        if draft.c4.links:
            relations = []
            for link in draft.c4.links:
                src, dst = names.get(link.src), names.get(link.dst)
                if src is None or dst is None:
                    missing = link.src if src is None else link.dst
                    update.dropped.append(
                        f"связь {link.src} → {link.dst}: элемента {missing} нет на схеме"
                    )
                    continue
                relations.append(Relationship(src, dst, link.label, link.technology))
    for gone in removed:
        containers.pop(gone, None)
        externals.pop(gone, None)
    present = {SYSTEM_ID, *actors, *containers, *externals}
    relations = [r for r in relations if r.src in present and r.dst in present]

    # --- texts and the nodes read back from them ----------------------------------------------
    scanned: dict[str, Node] = {}
    if accepted or removed & {u.id for u in uml.use_cases}:
        model = UseCaseModel(
            system.name if system is not None else uml.system or project_name,
            tuple((a.id, a.name) for a in actors.values()),
            tuple(use_cases.values()),
            tuple(uc_links),
            tuple(uc_relations),
        )
        text = render_use_cases(model)
        update.files[uml_rel] = text
        scanned |= {n.id: n for n in read_use_cases(text, uml_rel)}
    elif uml_rel in files:
        scanned |= {n.id: n for n in read_use_cases(files[uml_rel], uml_rel)}
    if draft.c4 is not None or (c4 is not None and removed & {*c4_ids(c4)}):
        people = tuple(Element(a.id, a.name, a.description or "") for a in actors.values())
        model4 = C4Model(
            c4.title if c4 else project_name,
            system,
            people,
            tuple(containers.values()),
            tuple(externals.values()),
            tuple(relations),
        )
        text = render_workspace(model4)
        update.files[c4_rel] = text
        scanned |= {n.id: n for n in read_elements(text, c4_rel)}
    elif c4_rel in files:
        scanned |= {n.id: n for n in read_elements(files[c4_rel], c4_rel)}

    ops: list[Op] = []
    adds: list[tuple[str, AddOp]] = []
    for node_id, node in scanned.items():
        old = graph.get(node_id)
        fields = node.model_dump(mode="json", exclude={"id", "kind"}, exclude_defaults=True)
        if old is None:
            adds.append(
                (
                    node_id,
                    AddOp(
                        op="add", kind=NodeKind(node.kind), tmp_id=f"v{len(adds)}", fields=fields
                    ),
                )
            )
        elif old != node:
            dump = node.model_dump(mode="json", exclude={"id", "kind"})
            ops.append(UpdateOp(op="update", id=node_id, fields=dump))
    adds.sort(key=lambda pair: _key(pair[0]))
    for gone in sorted(removed):
        ops.append(
            RemoveOp(
                op="remove", id=gone, reason=next(r.reason for r in draft.remove if r.id == gone)
            )
        )
    existing = {(e.src, e.dst) for e in graph.edges if e.rel is Rel.REALIZED_BY}
    for fr, target in sorted(links - existing):
        if target in scanned:
            ops.append(
                LinkOp.model_validate(
                    {"op": "link", "from": fr, "rel": "realized_by", "to": target}
                )
            )
    update.patch = GraphPatch(ops=[op for _, op in adds] + ops)
    update.ids = {r: i for r, i in update.ids.items() if i in scanned}
    return update


def c4_ids(model: C4Model) -> list[str]:
    return [e.id for e in (*model.containers, *model.externals)]


def view_problems(graph: ArtifactGraph, files: dict[str, str]) -> list[str]:
    """What the Modeler's views must have besides compiling (T-207): a use case for every role and
    a C4 model."""
    problems = []
    uml_rel = uml_file(files)
    linked = {a for a, _ in parse_use_cases(files[uml_rel]).links} if uml_rel in files else set()
    for actor in _actors(graph).values():
        if actor.id not in linked:
            problems.append(f"{actor.id} {actor.name}: у роли нет ни одного сценария использования")
    if c4_file(files) not in files:
        problems.append("нет схемы C4: опишите систему, контейнеры и внешние системы (поле c4)")
    return problems


def is_view_task(task: RepairTask) -> bool:
    return any(n.startswith(VIEW_PREFIXES) for n in task.node_ids)


# --- the step -----------------------------------------------------------------------------------


def _requirements(graph: ArtifactGraph) -> list[str]:
    lines = []
    for kind in ("UR", "FR", "NFR"):
        for node in graph.nodes_of(kind):
            area = f" [{node.area}]" if node.area else ""
            lines.append(
                f"{node.id}{area}: {getattr(node, 'title', '')} — {getattr(node, 'statement', '')}"
            )
    return lines


def render(graph: ArtifactGraph, files: dict[str, str], tasks: list[RepairTask]) -> str:
    return load_prompt("modeler/views").render(
        requirements=_requirements(graph),
        actors=[
            f"{a.id}: {a.name}" + (f" — {a.description}" if a.description else "")
            for a in _actors(graph).values()
        ],
        use_cases=files.get(uml_file(files), ""),
        c4=files.get(c4_file(files), ""),
        tasks=tasks,
    )


@dataclass
class _Try:
    number: int
    draft: ViewsDraft
    attempt: Attempt
    files: dict[str, str]
    result: ApplyResult | None = None
    problems: list[str] = field(default_factory=list)
    errors: int = 0


@dataclass
class ViewsResult:
    graph: ArtifactGraph
    files: dict[str, str]
    budget: BudgetState
    attempts: int
    diff: GraphDiff | None = None  # None: nothing applied
    stopped: bool = False  # the budget ran out


async def views_step(
    ctx: RunContext,
    graph: ArtifactGraph,
    files: dict[str, str],
    tasks: list[RepairTask],
    budget: BudgetState,
) -> ViewsResult:
    """Ask, build, self-check, ask again with the problems: at most MAX_ATTEMPTS answers; the best
    applied attempt wins, also when the budget runs out on the way."""
    prompt = render(graph, files, tasks)
    template = load_prompt("modeler/views")
    checks = [c for c in all_checks() if c.id in VIEW_CHECKS]
    name = ctx.project.config.project.name
    tries: list[_Try] = []
    text = prompt
    stopped = False
    for number in range(1, MAX_ATTEMPTS + 1):
        try:
            draft, budget = await ctx.ask(ROLE, text, ViewsDraft, budget, template=template)
        except BudgetExceeded:
            stopped = True
            break
        update = to_views(draft, graph, files, project_name=name)
        current = _Try(
            number,
            draft,
            guarded(update.patch, graph, "modeler", tasks, update.dropped),
            files | update.files,
        )
        try:
            current.result = graph.apply(current.attempt.patch, actor="agent")
        except GraphError as exc:
            current.problems, current.errors = [str(exc)], 1
        if current.result is not None and set(update.ids.values()) - set(
            current.result.graph.nodes
        ):
            current.problems = [*current.attempt.dropped, "id моделей разошлись после отсева"]
            current.errors = len(current.problems)
            current.result = None
        if current.result is not None and not ctx.self_checks:  # B2 (T-405): first that applies
            current.problems = current.attempt.dropped
            tries.append(current)
            break
        if current.result is not None:
            project = replace(
                ctx.project, graph=current.result.graph, files=current.files, warnings=[]
            )
            report = await run_checks(project, checks, offline=ctx.offline)
            found = [
                f
                for f in report.findings
                if f.severity != "info"
                and (f.check_id != "TRC-003" or f.node_ids[0].startswith(VIEW_PREFIXES))
            ]
            own = view_problems(current.result.graph, current.files)
            current.problems = [
                *current.attempt.dropped,
                *(f"{f.check_id}: {f.message}" for f in found),
                *own,
            ]
            current.errors = (
                len(current.attempt.dropped) + len(own) + sum(f.severity == "error" for f in found)
            )
        tries.append(current)
        ctx.events.emit("views_check", agent="modeler", attempt=number, problems=current.problems)
        if not current.problems:
            break
        if number < MAX_ATTEMPTS:
            text = (
                prompt
                + "\n\n"
                + load_prompt("modeler/retry").render(
                    answer=draft.model_dump_json(exclude_defaults=True), problems=current.problems
                )
            )
    applied = [t for t in tries if t.result is not None]
    if not applied:
        if tries:
            ctx.events.emit("patch_rejected", agent="modeler", error="; ".join(tries[-1].problems))
        return ViewsResult(graph, files, budget, len(tries), stopped=stopped)
    best = min(applied, key=lambda t: (t.errors, len(t.problems), -t.number))
    assert best.result is not None
    if best.problems:
        ctx.events.emit("dropped", agent="modeler", reasons=best.problems)
    return ViewsResult(best.result.graph, best.files, budget, len(tries), best.result.diff, stopped)
