"""Standards (03_agents, T-204): sections of the SRS by standards/iso29148_srs.yaml, glossary.

Most sections are built by code from the graph: lists of requirements, actors, entities and the
acceptance criteria, each item with its id, and `rendered_in` links node -> section. The LLM writes
only connected text: purpose, scope and the glossary (StandardsDraft). An empty field is asked for
once more; what is still empty stays empty, and TPL-001 reports it.
"""

from typing import Any

from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict, Field

from reqgraph.agents.common import diff_summary, guarded, start
from reqgraph.agents.prompts import load_prompt
from reqgraph.agents.runtime import RunContext
from reqgraph.agents.state import RepairTask, RunState
from reqgraph.graph.edges import Rel
from reqgraph.graph.errors import GraphError
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import (
    FunctionalReq,
    InterviewTurn,
    Node,
    NodeKind,
    SectionNode,
)
from reqgraph.graph.patch import AddOp, GraphPatch, LinkOp, Op, UpdateOp
from reqgraph.llm.router import BudgetExceeded
from reqgraph.standards import DocumentStructure, Section, load_structure

TEMPLATE = "iso29148_srs"


class _Draft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class GlossaryTerm(_Draft):
    term: str
    definition: str


class StandardsDraft(_Draft):
    purpose: str = Field(default="", description="2–4 предложения: что за система и для кого")
    scope: str = Field(default="", description="что система делает и чего не делает")
    glossary: list[GlossaryTerm] = Field(default_factory=list, description="5–15 терминов")


def _line(node: Node) -> str:
    title = getattr(node, "title", None) or getattr(node, "name", "")
    text = getattr(node, "statement", None) or getattr(node, "description", None) or ""
    return f"- {node.id} {title}" + (f": {text}" if text else "")


def _content(
    section: Section, graph: ArtifactGraph, draft: StandardsDraft
) -> tuple[str, list[str]]:
    """Text and node refs of one section."""
    if section.fill == "none":
        return "", []
    if section.llm_field == "glossary":
        return "\n".join(f"- {t.term} — {t.definition}" for t in draft.glossary if t.term), []
    if section.llm_field is not None:
        return str(getattr(draft, section.llm_field)).strip(), []
    if section.fill == "acceptance":
        checked = [n for n in graph.nodes_of("FR") if isinstance(n, FunctionalReq) and n.acceptance]
        lines = [f"- {n.id}: " + "; ".join(n.acceptance) for n in checked]
        return "\n".join(lines), [n.id for n in checked]
    if section.fill == "assumptions":
        nodes: list[Node] = [n for n in graph.nodes.values() if n.assumption]
    else:
        nodes = [n for kind in section.node_kinds for n in graph.nodes_of(kind)]
    return "\n".join(_line(n) for n in nodes), [n.id for n in nodes]


def build_sections(
    graph: ArtifactGraph, draft: StandardsDraft, structure: DocumentStructure | None = None
) -> GraphPatch:
    """Add or update every section of the structure; link the nodes it lists (rendered_in)."""
    structure = structure or load_structure(TEMPLATE)
    ops: list[Op] = []
    edges = {(e.src, e.dst) for e in graph.edges if e.rel is Rel.RENDERED_IN}
    for index, section in enumerate(structure.sections):
        text, refs = _content(section, graph, draft)
        fields: dict[str, Any] = {"template": structure.document, "text": text, "refs": refs}
        existing = graph.get(section.id)
        if existing is None:
            ops.append(
                AddOp(
                    op="add",
                    kind=NodeKind.SEC,
                    tmp_id=f"s{index}",
                    fields={"id": section.id, **fields},
                )
            )
        elif (
            isinstance(existing, SectionNode) and existing.model_dump(include=set(fields)) != fields
        ):
            ops.append(UpdateOp(op="update", id=section.id, fields=fields))
        for ref in refs:
            if (ref, section.id) not in edges:
                ops.append(
                    LinkOp.model_validate(
                        {"op": "link", "from": ref, "rel": "rendered_in", "to": section.id}
                    )
                )
    return GraphPatch(ops=ops)


def _missing(draft: StandardsDraft) -> list[str]:
    found = []
    if not draft.purpose.strip():
        found.append("purpose: пусто — нужно 2–4 предложения о назначении системы")
    if not draft.scope.strip():
        found.append("scope: пусто — нужна область применения")
    if not [t for t in draft.glossary if t.term.strip() and t.definition.strip()]:
        found.append("glossary: нет терминов с определениями")
    return found


def render(state: RunState, tasks: list[RepairTask]) -> str:
    graph = state["graph"]
    turns = [
        n for n in graph.nodes_of("TURN") if isinstance(n, InterviewTurn) and n.role == "client"
    ]
    requirements = [
        _line(n) for kind in ("BR", "UR", "FR", "NFR", "CON") for n in graph.nodes_of(kind)
    ]
    return load_prompt("standards/srs").render(
        turns=turns,
        requirements=requirements,
        actors=[_line(n) for n in graph.nodes_of("ACT")],
        entities=[_line(n) for n in graph.nodes_of("ENT")],
        tasks=tasks,
    )


async def standards(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = start(runtime, "standards")
    if state["stop"] is not None:
        return {}
    mine = [t for t in state["tasks"] if t.owner == "standards"]
    rest = [t for t in state["tasks"] if t.owner != "standards"]
    if state["iteration"] > 0 and not mine:
        ctx.events.emit("skip", agent="standards", reason="нет задач ремонта")
        return {}
    graph = state["graph"]
    prompt = render(state, mine)
    template = load_prompt("standards/srs")
    budget = state["budget"]
    try:
        draft, budget = await ctx.ask(
            "standards", prompt, StandardsDraft, budget, template=template
        )
        if missing := _missing(draft):
            ctx.events.emit("patch_retry", agent="standards", reasons=missing)
            retry = load_prompt("standards/retry").render(problems=missing)
            draft, budget = await ctx.ask(
                "standards", prompt + "\n\n" + retry, StandardsDraft, budget, template=template
            )
    except BudgetExceeded:
        ctx.events.emit("stop", reason="budget", node="standards")
        return {"stop": "budget", "tasks": rest, "budget": budget}
    update: dict[str, Any] = {"budget": budget, "tasks": rest}
    attempt = guarded(build_sections(graph, draft), graph, "standards", mine)
    if attempt.dropped:
        ctx.events.emit("dropped", agent="standards", reasons=attempt.dropped)
    try:
        result = graph.apply(attempt.patch, actor="agent")
    except GraphError as exc:
        ctx.events.emit("patch_rejected", agent="standards", error=str(exc))
        return update
    ctx.events.emit("agent_end", agent="standards", diff=diff_summary(result.diff))
    return update | {"graph": result.graph}
