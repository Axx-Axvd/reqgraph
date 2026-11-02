"""Standards (03_agents, T-204): sections of the SRS by standards/iso29148_srs.yaml, glossary.

Most sections are built by code from the graph: lists of requirements, actors, entities and the
acceptance criteria, each item with its id, and `rendered_in` links node -> section. The LLM writes
only connected text (StandardsDraft): purpose, scope, product perspective, glossary and the other
descriptive sections of the structure after Wiegers (T-408). An empty required field is asked for
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
    InterviewTurn,
    NodeKind,
    SectionNode,
)
from reqgraph.graph.patch import AddOp, GraphPatch, LinkOp, Op, UpdateOp
from reqgraph.llm.router import BudgetExceeded
from reqgraph.standards import DocumentStructure, Section, load_structure
from reqgraph.standards.content import code_content, line

TEMPLATE = "iso29148_srs"


class _Draft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class GlossaryTerm(_Draft):
    term: str
    definition: str


class StandardsDraft(_Draft):
    """Connected text of the SRS (T-408: the structure after Wiegers). Required: purpose, scope,
    perspective, glossary; the rest may stay empty when the data say nothing about it."""

    purpose: str = Field(default="", description="2–4 предложения: что за система и для кого")
    conventions: str = Field(default="", description="как читать документ: id, приоритеты")
    audience: str = Field(default="", description="кому адресован документ и что кому читать")
    scope: str = Field(default="", description="что система делает и чего не делает")
    references: str = Field(default="", description="документы и законы, названные заказчиком")
    perspective: str = Field(default="", description="новая система или замена, с чем связана")
    environment: str = Field(default="", description="где работает: устройства, браузеры, ОС")
    user_docs: str = Field(default="", description="какая документация нужна пользователям")
    ui: str = Field(default="", description="требования к экранам и удобству")
    hardware: str = Field(default="", description="оборудование: сканеры, принтеры, кассы")
    communication: str = Field(default="", description="SMS, почта, протоколы обмена")
    other: str = Field(default="", description="требования, не попавшие в другие разделы")
    glossary: list[GlossaryTerm] = Field(default_factory=list, description="5–15 терминов")


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
    built = code_content(section, graph)
    assert built is not None
    return built


def build_sections(
    graph: ArtifactGraph, draft: StandardsDraft | None, structure: DocumentStructure | None = None
) -> GraphPatch:
    """Add or update every section of the structure; link the nodes it lists (rendered_in).
    Without a draft the LLM sections keep their text: a rebuild after other agents' repairs."""
    structure = structure or load_structure(TEMPLATE)
    ops: list[Op] = []
    edges = {(e.src, e.dst) for e in graph.edges if e.rel is Rel.RENDERED_IN}
    for index, section in enumerate(structure.sections):
        if draft is None and section.llm_field is not None and graph.get(section.id) is not None:
            continue
        text, refs = _content(section, graph, draft or StandardsDraft())
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


REQUIRED_TEXT = {  # T-408: the LLM sections TPL-001 requires, with what to ask for
    "purpose": "нужно 2–4 предложения о назначении системы",
    "scope": "нужны границы проекта: что система делает и чего не делает",
    "perspective": "нужно положение продукта: новая система или замена, с чем связана",
}


def _missing(draft: StandardsDraft) -> list[str]:
    found = [
        f"{name}: пусто — {need}"
        for name, need in REQUIRED_TEXT.items()
        if not str(getattr(draft, name)).strip()
    ]
    if not [t for t in draft.glossary if t.term.strip() and t.definition.strip()]:
        found.append("glossary: нет терминов с определениями")
    return found


def render(state: RunState, tasks: list[RepairTask]) -> str:
    graph = state["graph"]
    turns = [
        n for n in graph.nodes_of("TURN") if isinstance(n, InterviewTurn) and n.role == "client"
    ]
    requirements = [
        line(n) for kind in ("BR", "UR", "FR", "NFR", "CON") for n in graph.nodes_of(kind)
    ]
    return load_prompt("standards/srs").render(
        turns=turns,
        requirements=requirements,
        actors=[line(n) for n in graph.nodes_of("ACT")],
        entities=[line(n) for n in graph.nodes_of("ENT")],
        tasks=tasks,
    )


async def standards(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = start(runtime, "standards")
    if state["stop"] is not None:
        return {}
    mine = [t for t in state["tasks"] if t.owner == "standards"]
    rest = [t for t in state["tasks"] if t.owner != "standards"]
    graph = state["graph"]
    if state["iteration"] > 0 and not mine:
        # other agents repaired the graph: rebuild the listed sections by code, no LLM call
        rebuilt = guarded(build_sections(graph, None), graph, "standards", [])
        if not rebuilt.patch.ops:
            ctx.events.emit("skip", agent="standards", reason="нет задач ремонта")
            return {}
        try:
            result = graph.apply(rebuilt.patch, actor="agent")
        except GraphError as exc:
            ctx.events.emit("patch_rejected", agent="standards", error=str(exc))
            return {}
        ctx.events.emit("rebuild", agent="standards", diff=diff_summary(result.diff))
        return {"graph": result.graph}
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
