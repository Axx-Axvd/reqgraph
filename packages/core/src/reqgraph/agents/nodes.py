"""Nodes of the run graph (03_agents): intake, interview, the pipeline, CI, repair, export.

The agents themselves live in agents/analyst.py, modeler.py and standards.py (T-202…T-204);
every agent patch goes through guard() and apply(actor="agent").
"""

from dataclasses import replace
from typing import Any

from langgraph.runtime import Runtime
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, Field

from reqgraph.agents.common import start
from reqgraph.agents.coverage import coverage_of, empty_answers, facts_by_area, queue
from reqgraph.agents.prompts import load_prompt
from reqgraph.agents.reviewer import fingerprints
from reqgraph.agents.runtime import RunContext
from reqgraph.agents.state import RunState
from reqgraph.checks.base import Owner
from reqgraph.checks.runner import run_checks
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import InterviewTurn, NodeKind
from reqgraph.graph.patch import AddOp, GraphPatch
from reqgraph.graph.store.config import Area
from reqgraph.graph.store.project import Project
from reqgraph.llm.router import BudgetExceeded

DONE = {"done": True}  # the answer that ends the interview early («/готово» in the CLI)
RECENT_TURNS = 8  # turns the interviewer sees verbatim
SAME_AREA = 2  # questions in a row about one area; then the next gap goes first
FACTS_SHOWN = 8  # told facts of an area the interviewer sees, the latest


class ReferenceProject(RuntimeError):
    """Agents are not run on a reference project: it is written and approved by a person."""


class Question(BaseModel):
    """The interviewer's output. Coverage itself is counted by code (coverage.py), the area only
    says what the question aims at (events, the efficiency metric of 09_eval)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    text: str = Field(min_length=1, description="один вопрос заказчику")
    area: Area | None = Field(default=None, description="область покрытия, о которой вопрос")
    done: bool = Field(default=False, description="только без трекера: вопросов больше нет")


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
    if state["mode"] == "check" or not state["brief"]:
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


def _turns(graph: ArtifactGraph) -> list[InterviewTurn]:
    return [n for n in graph.nodes_of("TURN") if isinstance(n, InterviewTurn)]


def render_question(state: RunState, ctx: RunContext) -> tuple[str, str]:
    """The prompt and the template name: with the coverage tracker (M2) or without it (M1)."""
    turns = _turns(state["graph"])
    asked = [t.text for t in turns if t.role == "agent"]
    assumptions = [
        f"{n.id}: {getattr(n, 'statement', '')}"
        for kind in ("BR", "UR", "FR", "NFR", "CON")
        for n in state["graph"].nodes_of(kind)
        if n.assumption
    ]
    name = "interviewer/ask" if ctx.interviewer == "coverage" else "interviewer/ask_free"
    found = next_gaps(state)
    areas = [area for area, _, _ in found[:3]]
    facts = facts_by_area(state["graph"], areas)
    prompt = load_prompt(name).render(
        gaps=found,
        coverage=state["coverage"],
        facts={area: facts[area][-FACTS_SHOWN:] for area in areas},
        asked_before={area for area in state["asked_areas"] if area is not None},
        recent=turns[-RECENT_TURNS:],
        asked=asked,
        assumptions=assumptions[:10],
        turn=state["turns"] + 1,
        max_turns=ctx.max_turns,
    )
    return prompt, name


def next_gaps(state: RunState) -> list[tuple[str, int, int]]:
    """The areas to ask about, in the order of coverage.queue() (T-305); among those asked
    before, one whose last answer told nothing new, or that was asked SAME_AREA times in a row,
    goes last."""
    graph, asked = state["graph"], state["asked_areas"]
    found = queue(state["coverage"], graph, asked)
    empty = empty_answers(graph, asked)
    recent = asked[-SAME_AREA:]
    last: str | None = None
    if empty and empty[-1] is not None:
        last = empty[-1]
    elif len(recent) == SAME_AREA and len(set(recent)) == 1:
        last = recent[0]
    if last is not None and len(found) > 1:
        found.sort(key=lambda g: g[0] == last)  # stable: the rest keep their order
    return found


async def interviewer(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = start(runtime, "interviewer")
    if state["stop"] is not None:
        return {}
    prompt, name = render_question(state, ctx)
    template = load_prompt(name)
    try:
        question, budget = await ctx.ask(
            "interviewer", prompt, Question, state["budget"], template=template
        )
    except BudgetExceeded:
        ctx.events.emit("stop", reason="budget", node="interviewer")
        return {"stop": "budget"}
    if question.done and ctx.interviewer == "free":
        ctx.events.emit("interview_end", reason="interviewer", turns=state["turns"])
        return {"budget": budget, "question": None, "interview_done": True}
    ctx.events.emit("question", turn=state["turns"] + 1, area=question.area)
    asked = [*state["asked_areas"], question.area]
    return {"question": question.text, "budget": budget, "asked_areas": asked}


async def await_answer(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    """Pause until a person or the simulator answers; both turns go into the graph as data.
    The answer DONE ends the interview without a turn."""
    ctx = start(runtime, "await_answer")
    if state["stop"] is not None or state["question"] is None:
        return {}
    answer = interrupt({"question": state["question"], "turn": state["turns"] + 1})
    if answer == DONE:
        ctx.events.emit("interview_end", reason="client", turns=state["turns"])
        return {"question": None, "interview_done": True}
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
    """interview — the brief to the Analyst first, else straight to the coverage; brief — to the
    Analyst; check — only the checks."""
    if state["mode"] == "interview":
        return "analyst" if state["brief"] else "coverage"
    return {"brief": "analyst", "check": "ci_check"}[state["mode"]]


async def coverage(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    """Count the coverage from the graph and decide whether the interview goes on (03_agents):
    coverage reached (with the tracker), every area left closed (T-305), the turn limit,
    «/готово», or the agents stopped."""
    ctx = start(runtime, "coverage")
    counted = coverage_of(state["graph"], state["coverage"].need)
    tracker = ctx.interviewer == "coverage"
    reached = counted.complete and tracker
    left = queue(counted, state["graph"], state["asked_areas"])
    saturated = tracker and not reached and not left
    limit = state["turns"] >= ctx.max_turns
    done = state["interview_done"] or state["stop"] is not None or reached or saturated or limit
    ctx.events.emit(
        "coverage",
        turns=state["turns"],
        got=counted.got,
        need=counted.need,
        left=[area for area, _, _ in left],
        done=done,
    )
    if done and not state["interview_done"]:
        reason = (
            "coverage" if reached else "saturated" if saturated else "limit" if limit else "stop"
        )
        ctx.events.emit("interview_end", reason=reason, turns=state["turns"])
    return {"coverage": counted, "interview_done": done}


def coverage_gate(state: RunState) -> str:
    return "done" if state["interview_done"] else "ask"


def after_analyst(state: RunState) -> str:
    """In an interview the Analyst runs after every answer, then the coverage is counted again;
    once the interview is over (and in repair rounds) the pipeline goes on to the Modeler."""
    if state["mode"] == "interview" and not state["interview_done"] and state["stop"] is None:
        return "coverage"
    return "modeler"


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
