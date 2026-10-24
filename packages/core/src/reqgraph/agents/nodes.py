"""Nodes of the run graph (03_agents): intake, interview, the pipeline, CI, repair, export.

The Analyst is real (agents/analyst.py, T-202). Modeler and Standards are still stubs around one
structured() call (T-203, T-204): their prompt is data only — the graph view and the tasks in
tags, no instructions in code. Every agent patch goes through guard() and apply(actor="agent").
"""

import json
from typing import Any

from langgraph.runtime import Runtime
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, Field

from reqgraph.agents.common import ALLOWED, diff_summary, guarded, start, tag
from reqgraph.agents.runtime import RunContext
from reqgraph.agents.state import RepairTask, RunState
from reqgraph.checks.base import Owner
from reqgraph.checks.runner import run_checks
from reqgraph.graph.errors import GraphError
from reqgraph.graph.nodes import NodeKind
from reqgraph.graph.patch import AddOp, GraphPatch
from reqgraph.llm.router import BudgetExceeded

MAX_TASKS = 10  # repair tasks per round (03_agents, Reviewer)


class ReferenceProject(RuntimeError):
    """Agents are not run on a reference project: it is written and approved by a person."""


class Question(BaseModel):
    """The interviewer's output in T-201; T-301 adds the coverage delta."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)


def brief_turns(brief: str) -> list[str]:
    """Paragraphs of a brief, without Markdown headings: each becomes a client turn."""
    paragraphs = (" ".join(p.split()) for p in brief.replace("\r\n", "\n").split("\n\n"))
    return [p for p in paragraphs if p and not p.startswith("#")]


async def intake(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = start(runtime, "intake")
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
    if state["mode"] != "brief" or not state["brief"]:
        return {}
    texts = brief_turns(state["brief"])
    patch = GraphPatch(
        ops=[
            AddOp(
                op="add", kind=NodeKind.TURN, tmp_id=f"b{i}", fields={"role": "client", "text": t}
            )
            for i, t in enumerate(texts)
        ]
    )
    result = state["graph"].apply(patch, actor="agent")
    ctx.events.emit("brief", turns=list(result.id_map.values()))
    return {"graph": result.graph}


async def interviewer(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = start(runtime, "interviewer")
    if state["stop"] is not None:
        return {}
    prompt = tag("graph", state["graph"].to_json())
    try:
        question, budget = await ctx.ask("interviewer", prompt, Question, state["budget"])
    except BudgetExceeded:
        ctx.events.emit("stop", reason="budget", node="interviewer")
        return {"stop": "budget"}
    return {"question": question.text, "budget": budget}


async def await_answer(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    """Pause until a person or the simulator answers; both turns go into the graph as data."""
    ctx = start(runtime, "await_answer")
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


async def _stub(owner: Owner, state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    """Modeler and Standards until T-203/T-204: one GraphPatch call, guarded and applied."""
    ctx = start(runtime, owner)
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
            tag("graph", state["graph"].view(allowed).to_json()),
            tag("tasks", json.dumps([t.model_dump() for t in mine], ensure_ascii=False)),
        ]
    )
    try:
        patch, budget = await ctx.ask(owner, prompt, GraphPatch, state["budget"])
    except BudgetExceeded:
        ctx.events.emit("stop", reason="budget", node=owner)
        return {"stop": "budget", "tasks": rest}
    update: dict[str, Any] = {"budget": budget, "tasks": rest}
    attempt = guarded(patch, state["graph"], owner, mine)
    if attempt.dropped:
        ctx.events.emit("dropped", agent=owner, reasons=attempt.dropped)
    try:
        result = state["graph"].apply(attempt.patch, actor="agent")
    except GraphError as exc:
        ctx.events.emit("patch_rejected", agent=owner, error=str(exc))
        return update
    ctx.events.emit("agent_end", agent=owner, diff=diff_summary(result.diff))
    return update | {"graph": result.graph}


async def modeler(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    return await _stub("modeler", state, runtime)


async def standards(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    return await _stub("standards", state, runtime)


async def ci_check(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    """The same checks as `reqgraph check`: deterministic, no LLM (ADR-006)."""
    ctx = start(runtime, "ci_check")
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
    ctx = start(runtime, "reviewer")
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
    start(runtime, "export").events.emit("export", formats=[])  # SRS and TZ come in T-401
    return {}


async def persist(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = start(runtime, "persist")
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
