"""Analyst (03_agents, T-202): brief or interview -> BR, UR, FR, NFR, CON and actors.

The model fills a flat questionnaire (AnalystDraft), not a raw GraphPatch: free models keep it
better, and ids and links are still issued by code. to_patch() turns the draft into a GraphPatch,
checking every new node against its schema first: an invalid item is dropped with the reason,
the rest stays. The node then guards, applies and, if anything was dropped, asks once more.
"""

from dataclasses import dataclass, field
from functools import cache
from typing import Any, Literal, get_args

from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict, Field

from reqgraph.agents.common import ALLOWED, Attempt, apply_with_retry, diff_summary, guarded, start
from reqgraph.agents.prompts import load_prompt
from reqgraph.agents.runtime import RunContext
from reqgraph.agents.state import BudgetState, RepairTask, RunState
from reqgraph.checks.text import vague_dictionary
from reqgraph.graph.edges import Rel
from reqgraph.graph.errors import GraphError
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import ISO25010, InterviewTurn, Node, NodeKind, Priority, node_from_dict
from reqgraph.graph.patch import AddOp, GraphPatch, LinkOp, Op, RemoveOp, UpdateOp
from reqgraph.graph.store.config import Area
from reqgraph.llm.router import BudgetExceeded

RequirementKind = Literal["BR", "UR", "FR", "NFR", "CON"]


class _Draft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")  # tolerate extra keys from a model


class DraftGoal(_Draft):
    name: str
    unit: str
    target: str
    baseline: float | None = None
    horizon: str | None = None


class DraftMetric(_Draft):
    name: str
    unit: str
    threshold: str
    method: str


class DraftRequirement(_Draft):
    ref: str = Field(description="new: a short latin key (fr_cancel); existing: its id (FR-003)")
    kind: RequirementKind
    title: str
    statement: str
    priority: Priority | None = None
    area: Area | None = None
    acceptance: list[str] = Field(default_factory=list, description="FR only")
    scenario: list[str] = Field(default_factory=list, description="UR only: steps")
    actor: str | None = Field(default=None, description="UR only: ref or id of an actor")
    goal_metric: DraftGoal | None = Field(default=None, description="BR only")
    iso25010: ISO25010 | None = Field(default=None, description="NFR only")
    metric: DraftMetric | None = Field(default=None, description="NFR only")
    constraint_type: Literal["legal", "budget", "time", "tech"] | None = Field(
        default=None, description="CON only"
    )
    refines: list[str] = Field(default_factory=list, description="refs or ids: UR->BR, FR/NFR->UR")
    sources: list[str] = Field(default_factory=list, description="TURN ids of client turns")
    assumption: bool = False


class DraftActor(_Draft):
    ref: str
    name: str
    description: str | None = None
    sources: list[str] = Field(default_factory=list)


class Removal(_Draft):
    id: str
    reason: str


class AnalystDraft(_Draft):
    actors: list[DraftActor] = Field(default_factory=list)
    requirements: list[DraftRequirement] = Field(default_factory=list)
    remove: list[Removal] = Field(default_factory=list, description="repair tasks only")


# fields of each kind that the draft may set (the rest of the node is kept as it is)
_FIELDS: dict[str, tuple[str, ...]] = {
    "BR": ("title", "statement", "priority", "area", "assumption", "goal_metric"),
    "UR": ("title", "statement", "priority", "area", "assumption", "actor", "scenario"),
    "FR": ("title", "statement", "priority", "area", "assumption", "acceptance"),
    "NFR": ("title", "statement", "priority", "area", "assumption", "iso25010", "metric"),
    "CON": ("title", "statement", "area", "assumption", "type"),
    "ACT": ("name", "description"),
}
_DUMMY = {"BR": "BR-000", "UR": "UR-000", "FR": "FR-000", "NFR": "NFR-000", "CON": "CON-000"}


@dataclass
class Conversion:
    patch: GraphPatch
    refs: dict[str, str] = field(default_factory=dict)  # draft ref -> tmp_id or existing id
    dropped: list[str] = field(default_factory=list)


def _requirement_fields(item: DraftRequirement, *, edit: bool = False) -> dict[str, Any]:
    """Fields of a node. An edit of an existing node takes only the fields the model sent: an
    omitted acceptance list must not wipe the criteria (T-205)."""
    data = item.model_dump(
        exclude_none=True, exclude_unset=edit, exclude={"ref", "kind", "refines", "sources"}
    )
    if "constraint_type" in data:
        data["type"] = data.pop("constraint_type")
    return {k: v for k, v in data.items() if k in _FIELDS[item.kind]}


def to_patch(draft: AnalystDraft, graph: ArtifactGraph) -> Conversion:
    """Draft -> GraphPatch. New items get tmp_ids; existing ids are updated where they differ."""
    conversion = Conversion(GraphPatch(ops=[]))
    ops: list[Op] = []
    refs = conversion.refs

    def new_tmp() -> str:
        return f"n{len(refs) + 1}"

    actors: list[tuple[DraftActor, str]] = []  # new actors and their tmp_ids
    for actor in draft.actors:
        if graph.get(actor.ref) is not None:
            refs[actor.ref] = actor.ref
            continue
        fields = actor.model_dump(exclude_none=True, include={"name", "description"})
        try:
            node_from_dict({"kind": "ACT", "id": "ACT-00", **fields}, actor.ref)
        except GraphError as exc:
            conversion.dropped.append(str(exc))
            continue
        refs[actor.ref] = tmp = new_tmp()
        ops.append(AddOp(op="add", kind=NodeKind.ACT, tmp_id=tmp, fields=fields))
        actors.append((actor, tmp))

    kept: list[tuple[DraftRequirement, str]] = []
    for item in draft.requirements:
        fields = _requirement_fields(item, edit=graph.get(item.ref) is not None)
        if fields.get("actor") is not None:
            actor_ref = refs.get(fields["actor"], fields["actor"])
            known = {tmp for _, tmp in actors} | {n.id for n in graph.nodes_of("ACT")}
            if actor_ref not in known:
                conversion.dropped.append(f"{item.ref}: роли «{fields['actor']}» нет")
                del fields["actor"]
            else:
                fields["actor"] = actor_ref
        existing = graph.get(item.ref)
        if existing is not None:
            if existing.kind != item.kind:
                conversion.dropped.append(
                    f"{item.ref}: вид узла {existing.kind} нельзя сменить на {item.kind}"
                )
                continue
            try:
                changed = _changed(existing, fields)
            except GraphError as exc:
                conversion.dropped.append(str(exc))
                continue
            if changed:
                ops.append(UpdateOp(op="update", id=item.ref, fields=changed))
            refs[item.ref] = item.ref
            kept.append((item, item.ref))
            continue
        try:
            check = {**fields, "actor": None} if "actor" in fields else fields
            node_from_dict({"kind": item.kind, "id": _DUMMY[item.kind], **check}, item.ref)
        except GraphError as exc:
            conversion.dropped.append(str(exc))
            continue
        refs[item.ref] = tmp = new_tmp()
        ops.append(AddOp(op="add", kind=NodeKind(item.kind), tmp_id=tmp, fields=fields))
        kept.append((item, tmp))

    edges = {(e.src, e.rel, e.dst) for e in graph.edges}

    def link(src: str, rel: Rel, dst: str, label: str) -> None:
        target = refs.get(dst, dst)
        if target == dst and graph.get(dst) is None and not dst.startswith("TURN-"):
            conversion.dropped.append(f"{label}: {rel.value} {dst} — такого требования нет")
            return
        if (src, rel, target) not in edges:
            ops.append(LinkOp.model_validate({"op": "link", "from": src, "rel": rel, "to": target}))

    for item, ref in kept:
        for parent in item.refines:
            link(ref, Rel.REFINES, parent, item.ref)
        for turn in item.sources:
            link(ref, Rel.DERIVED_FROM, turn, item.ref)
    for actor, ref in actors:
        for turn in actor.sources:
            link(ref, Rel.DERIVED_FROM, turn, actor.ref)
    ops += [RemoveOp(op="remove", id=r.id, reason=r.reason) for r in draft.remove]
    conversion.patch = GraphPatch(ops=ops)
    return conversion


def _changed(node: Node, fields: dict[str, Any]) -> dict[str, Any]:
    current = node.model_dump(mode="json")
    probe = node_from_dict({**current, **fields}, node.id).model_dump(mode="json")
    return {k: fields[k] for k in fields if probe.get(k) != current.get(k)}


# --- the prompt ------------------------------------------------------------------------------


@cache
def _vague_terms() -> list[str]:
    vocabulary = vague_dictionary()
    return sorted(vocabulary["ru_lemmas"] | vocabulary["phrases"])


def _view(graph: ArtifactGraph) -> list[str]:
    """Requirements and actors as short lines: what the Analyst may see and change."""
    lines = []
    for node in graph.view(ALLOWED["analyst"]).nodes.values():
        links = [f"{e.rel.value} {e.dst}" for e in graph.edges if e.src == node.id]
        text = getattr(node, "statement", None) or getattr(node, "name", "")
        title = getattr(node, "title", "")
        head = f"{node.id} [{node.status}] {title}".rstrip()
        lines.append(f"{head}: {text}" + (f" ({'; '.join(links)})" if links else ""))
    return lines


def _turns(graph: ArtifactGraph) -> list[InterviewTurn]:
    return [n for n in graph.nodes_of("TURN") if isinstance(n, InterviewTurn)]


def render(state: RunState, tasks: list[RepairTask]) -> str:
    return load_prompt("analyst/extract").render(
        vague_terms=_vague_terms(),
        iso25010=get_args(ISO25010),
        areas=get_args(Area),
        graph=_view(state["graph"]),
        turns=_turns(state["graph"]),
        tasks=tasks,
    )


async def analyst(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = start(runtime, "analyst")
    if state["stop"] is not None:
        return {}
    mine = [t for t in state["tasks"] if t.owner == "analyst"]
    rest = [t for t in state["tasks"] if t.owner != "analyst"]
    if state["iteration"] > 0 and not mine:
        ctx.events.emit("skip", agent="analyst", reason="нет задач ремонта")
        return {}
    graph = state["graph"]
    prompt = render(state, mine)
    budget: list[BudgetState] = [state["budget"]]

    async def ask(text: str) -> Attempt:
        draft, budget[0] = await ctx.ask(
            "analyst", text, AnalystDraft, budget[0], template=load_prompt("analyst/extract")
        )
        conversion = to_patch(draft, graph)
        return guarded(conversion.patch, graph, "analyst", mine, conversion.dropped)

    async def retry(reasons: str) -> Attempt:
        return await ask(prompt + "\n\n" + load_prompt("analyst/retry").render(error=reasons))

    try:
        result = await apply_with_retry(ctx, "analyst", graph, await ask(prompt), retry)
    except BudgetExceeded:
        ctx.events.emit("stop", reason="budget", node="analyst")
        return {"stop": "budget", "tasks": rest, "budget": budget[0]}
    update: dict[str, Any] = {"budget": budget[0], "tasks": rest}
    if result is None:
        return update
    ctx.events.emit("agent_end", agent="analyst", diff=diff_summary(result.diff))
    return update | {"graph": result.graph}
