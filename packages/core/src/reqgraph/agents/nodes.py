"""Nodes of the run graph (03_agents): intake, interview, the pipeline, CI, repair, export.

The agents themselves live in agents/analyst.py, modeler.py and standards.py (T-202…T-204);
every agent patch goes through guard() and apply(actor="agent").
"""

from dataclasses import replace
from typing import Any

from langgraph.runtime import Runtime
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, Field

from reqgraph.agents.common import start, tag
from reqgraph.agents.reviewer import fingerprints
from reqgraph.agents.runtime import RunContext
from reqgraph.agents.state import RunState
from reqgraph.checks.base import Owner
from reqgraph.checks.runner import run_checks
from reqgraph.graph.nodes import NodeKind
from reqgraph.graph.patch import AddOp, GraphPatch
from reqgraph.graph.store.project import Project
from reqgraph.llm.router import BudgetExceeded


class ReferenceProject(RuntimeError):
    """Agents are not run on a reference project: it is written and approved by a person."""


class Question(BaseModel):
    """The interviewer's output in T-201; T-301 adds the coverage delta."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)


def run_project(ctx: RunContext, state: RunState) -> Project:
    """The project as it is in this run: its graph and the model files agents have written."""
    files = ctx.project.files | state["files"]
    return replace(ctx.project, graph=state["graph"], files=files, warnings=[])


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


async def ci_check(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    """The same checks as `reqgraph check`: deterministic, no LLM (ADR-006)."""
    ctx = start(runtime, "ci_check")
    report = await run_checks(run_project(ctx, state), offline=ctx.offline)
    ctx.events.emit("ci_report", iteration=state["iteration"], **report.summary.model_dump())
    return {"ci": report, "history": [*state["history"], fingerprints(report)]}


def ci_gate(state: RunState) -> str:
    """Errors go to the Reviewer; it repairs or stops the run with needs_human (no progress, no
    rounds left). A report is exported in any case (05_ci)."""
    report = state["ci"]
    if state["mode"] == "check" or state["stop"] is not None or report is None or report.ok:
        return "done"
    return "repair"


PIPELINE: tuple[Owner, ...] = ("analyst", "modeler", "standards")


def route_tasks(state: RunState) -> str:
    """Repair goes down the pipeline from the first owner with tasks; the others skip theirs.
    A stopped run (needs_human, budget) goes straight to export with the last report."""
    if state["stop"] is not None:
        return "export"
    owners = {t.owner for t in state["tasks"]}
    return next((o for o in PIPELINE if o in owners), "analyst")


async def export(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    start(runtime, "export").events.emit("export", formats=[])  # SRS and TZ come in T-401
    return {}


async def persist(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = start(runtime, "persist")
    if ctx.store is not None:
        ctx.store.save(run_project(ctx, state))
    report = state["ci"]
    ctx.events.emit(
        "run_end",
        stop=state["stop"],
        iteration=state["iteration"],
        errors=None if report is None else report.summary.errors,
        budget=state["budget"].model_dump(),
    )
    return {}
