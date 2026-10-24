"""Nodes of the run graph (03_agents). In T-201 the agents are stubs around one LLM call each.

An agent node: its own repair tasks -> one structured() call through llm/ -> GraphPatch -> only its
own node kinds (ALLOWED) -> ArtifactGraph.apply(actor="agent"): ids come from code, approved
nodes are locked. Real prompts and guard() come with the agents (T-202…T-205); the prompt here is
data only — the graph view and the tasks in tags, no instructions in code.
"""

import json
from typing import Any

from langgraph.runtime import Runtime
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, Field

from reqgraph.agents.runtime import RunContext
from reqgraph.agents.state import RepairTask, RunState
from reqgraph.checks.base import Owner
from reqgraph.checks.runner import run_checks
from reqgraph.graph.errors import GraphError
from reqgraph.graph.graph import ApplyResult, GraphDiff
from reqgraph.graph.nodes import NodeKind
from reqgraph.graph.patch import AddOp, GraphPatch, RemoveOp, UpdateOp
from reqgraph.llm.router import BudgetExceeded

ALLOWED: dict[Owner, frozenset[NodeKind]] = {
    "analyst": frozenset(
        {NodeKind.BR, NodeKind.UR, NodeKind.FR, NodeKind.NFR, NodeKind.CON, NodeKind.ACT}
    ),
    "modeler": frozenset({NodeKind.PRC, NodeKind.ENT, NodeKind.UC, NodeKind.C4}),
    "standards": frozenset({NodeKind.SEC}),
}
MAX_TASKS = 10  # repair tasks per round (03_agents, Reviewer)


class ReferenceProject(RuntimeError):
    """Agents are not run on a reference project: it is written and approved by a person."""


class Question(BaseModel):
    """The interviewer's output in T-201; T-301 adds the coverage delta."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)


def _context(runtime: Runtime[RunContext], node: str) -> RunContext:
    runtime.context.events.emit("node_start", node=node)
    return runtime.context


def _data(name: str, value: str) -> str:
    return f"<{name}>\n{value}\n</{name}>"


def _diff(diff: GraphDiff) -> dict[str, Any]:
    return {
        "added": diff.added,
        "removed": diff.removed,
        "changed": sorted(diff.changed),
        "linked": len(diff.linked),
        "unlinked": len(diff.unlinked),
    }


def _foreign(patch: GraphPatch, state: RunState, allowed: frozenset[NodeKind]) -> list[str]:
    """Ops on node kinds that are not the agent's own."""
    graph = state["graph"]
    found = []
    for op in patch.ops:
        if isinstance(op, AddOp):
            kind: str | None = op.kind
        elif isinstance(op, UpdateOp | RemoveOp):
            node = graph.get(op.id)
            kind = node.kind if node is not None else None
        else:
            continue  # links are checked by apply(): both ends must exist
        if kind is not None and NodeKind(kind) not in allowed:
            found.append(f"{op.op} {kind}")
    return found


async def intake(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = _context(runtime, "intake")
    info = ctx.project.config.project
    if info.reference and state["mode"] != "check":
        raise ReferenceProject(
            f"{info.id}: эталонный проект — агенты не запускаются, только проверки и экспорт "
            "(reqgraph.yaml: project.reference)"
        )
    ctx.events.emit(
        "run_start",
        mode=state["mode"],
        project=info.id,
        nodes=len(state["graph"].nodes),
    )
    return {}


async def interviewer(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = _context(runtime, "interviewer")
    if state["stop"] is not None:
        return {}
    prompt = _data("graph", state["graph"].to_json())
    try:
        question, budget = await ctx.ask("interviewer", prompt, Question, state["budget"])
    except BudgetExceeded:
        ctx.events.emit("stop", reason="budget", node="interviewer")
        return {"stop": "budget"}
    return {"question": question.text, "budget": budget}


async def await_answer(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    """Pause until a person or the simulator answers; both turns go into the graph as data."""
    ctx = _context(runtime, "await_answer")
    if state["stop"] is not None or state["question"] is None:
        return {}
    answer = interrupt({"question": state["question"]})
    turns = [("q", "agent", state["question"]), ("a", "client", str(answer))]
    patch = GraphPatch(
        ops=[
            AddOp(op="add", kind=NodeKind.TURN, tmp_id=tmp, fields={"role": role, "text": text})
            for tmp, role, text in turns
        ]
    )
    result = state["graph"].apply(patch, actor="agent")
    ctx.events.emit("answer", turns=[result.id_map["q"], result.id_map["a"]])
    return {"graph": result.graph, "question": None, "turns": state["turns"] + 1}


def mode_gate(state: RunState) -> str:
    """interview — questions first; brief — straight to the Analyst; check — only the checks."""
    return {"interview": "interviewer", "brief": "analyst", "check": "ci_check"}[state["mode"]]


def coverage_gate(state: RunState, runtime: Runtime[RunContext]) -> str:
    """Enough asked: coverage reached, the turn limit, or the agents stopped (03_agents)."""
    if (
        state["stop"] is not None
        or state["coverage"].complete
        or state["turns"] >= runtime.context.max_turns
    ):
        return "done"
    return "ask"


async def _agent(owner: Owner, state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = _context(runtime, owner)
    if state["stop"] is not None:
        return {}
    mine = [t for t in state["tasks"] if t.owner == owner]
    rest = [t for t in state["tasks"] if t.owner != owner]
    if state["iteration"] > 0 and not mine:
        ctx.events.emit("skip", agent=owner, reason="нет задач ремонта")
        return {}
    allowed = ALLOWED[owner]
    prompt = "\n".join(
        [
            _data("graph", state["graph"].view(allowed).to_json()),
            _data("tasks", json.dumps([t.model_dump() for t in mine], ensure_ascii=False)),
        ]
    )
    try:
        patch, budget = await ctx.ask(owner, prompt, GraphPatch, state["budget"])
    except BudgetExceeded:
        ctx.events.emit("stop", reason="budget", node=owner)
        return {"stop": "budget", "tasks": rest}
    update: dict[str, Any] = {"budget": budget, "tasks": rest}
    if foreign := _foreign(patch, state, allowed):
        error = f"чужие типы узлов: {', '.join(foreign)}"
        ctx.events.emit("patch_rejected", agent=owner, error=error)
        return update
    try:
        result: ApplyResult = state["graph"].apply(patch, actor="agent")
    except GraphError as exc:
        ctx.events.emit("patch_rejected", agent=owner, error=str(exc))
        return update
    ctx.events.emit("agent_end", agent=owner, ops=len(patch.ops), diff=_diff(result.diff))
    return update | {"graph": result.graph}


async def analyst(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    return await _agent("analyst", state, runtime)


async def modeler(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    return await _agent("modeler", state, runtime)


async def standards(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    return await _agent("standards", state, runtime)


async def ci_check(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    """The same checks as `reqgraph check`: deterministic, no LLM (ADR-006)."""
    ctx = _context(runtime, "ci_check")
    report = await run_checks(ctx.project.with_graph(state["graph"]), offline=ctx.offline)
    ctx.events.emit("ci_report", iteration=state["iteration"], **report.summary.model_dump())
    return {"ci": report}


def template_tasks(state: RunState) -> list[RepairTask]:
    """Tasks straight from the errors of the report: owner, nodes, message and hint.

    The stand-in for the LLM Reviewer (T-205) and the «without Reviewer» ablation (09_eval).
    """
    report = state["ci"]
    errors = [] if report is None else [f for f in report.findings if f.severity == "error"]
    return [
        RepairTask(
            owner=f.owner,
            node_ids=f.node_ids,
            instruction=f.message + (f" — {f.hint}" if f.hint else ""),
            check_ids=[f.check_id],
        )
        for f in errors[:MAX_TASKS]
    ]


def ci_gate(state: RunState, runtime: Runtime[RunContext]) -> str:
    """Repair while there are errors and rounds left; a report is exported in any case (05_ci)."""
    report = state["ci"]
    if (
        state["mode"] == "check"
        or state["stop"] is not None
        or report is None
        or report.ok
        or state["iteration"] >= runtime.context.max_iter
    ):
        return "done"
    return "repair"


async def reviewer(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = _context(runtime, "reviewer")
    tasks = template_tasks(state)
    iteration = state["iteration"] + 1
    ctx.events.emit("repair", iteration=iteration, tasks=[t.model_dump() for t in tasks])
    return {"tasks": tasks, "iteration": iteration}


PIPELINE: tuple[Owner, ...] = ("analyst", "modeler", "standards")


def route_tasks(state: RunState) -> Owner:
    """Repair goes down the pipeline from the first owner with tasks; the others skip theirs."""
    owners = {t.owner for t in state["tasks"]}
    return next((o for o in PIPELINE if o in owners), "analyst")


async def export(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    _context(runtime, "export").events.emit("export", formats=[])  # SRS and TZ come in T-401
    return {}


async def persist(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = _context(runtime, "persist")
    if ctx.store is not None:
        ctx.store.save(ctx.project.with_graph(state["graph"]))
    report = state["ci"]
    ctx.events.emit(
        "run_end",
        stop=state["stop"],
        iteration=state["iteration"],
        errors=None if report is None else report.summary.errors,
        budget=state["budget"].model_dump(),
    )
    return {}
