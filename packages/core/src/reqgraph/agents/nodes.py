"""Nodes of the run graph (03_agents): intake, interview, the pipeline, CI, repair, export.

The agents themselves live in agents/analyst.py, modeler.py and standards.py (T-202…T-204);
every agent patch goes through guard() and apply(actor="agent").
"""

from dataclasses import replace
from typing import Any, Literal

from langgraph.runtime import Runtime
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, Field

from reqgraph.agents.common import start
from reqgraph.agents.coverage import (
    NOT_UNDERSTOOD,
    again,
    clarify,
    coverage_of,
    facts_by_area,
    language_step,
    latest_told_nothing,
    queue,
)
from reqgraph.agents.prompts import load_prompt
from reqgraph.agents.reviewer import fingerprints
from reqgraph.agents.runtime import RunContext
from reqgraph.agents.state import Coverage, RunState
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
    """The interviewer's output. Coverage itself is counted by code (coverage.py); the coverage
    interviewer (M2) asks about the area the code picked, so its area here is ignored (T-317)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    text: str = Field(min_length=1, description="один вопрос заказчику")
    area: Area | None = Field(default=None, description="область покрытия, о которой вопрос")
    done: bool = Field(default=False, description="только без трекера: вопросов больше нет")


class Mark(BaseModel):
    """How the client answered the latest question (T-317): a call of its own before the question,
    so the code knows it when it picks the next area."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    previous: Literal["ok", "vague", "not_understood"] = Field(
        default="ok", description="как заказчик ответил: понял, расплывчато, не понял"
    )


Mode = Literal["new", "rephrase", "clarify"]


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


def _context(state: RunState) -> dict[str, Any]:
    turns = _turns(state["graph"])
    assumptions = [
        f"{n.id}: {getattr(n, 'statement', '')}"
        for kind in ("BR", "UR", "FR", "NFR", "CON")
        for n in state["graph"].nodes_of(kind)
        if n.assumption
    ]
    return {
        "recent": turns[-RECENT_TURNS:],
        "asked": [t.text for t in turns if t.role == "agent"],
        "assumptions": assumptions[:10],
        "turn": state["turns"] + 1,
    }


def render_question(
    state: RunState, ctx: RunContext, choice: tuple[str, int, Mode] | None = None
) -> tuple[str, str]:
    """The prompt and the template name: about the area the code picked (M2) or free (M1)."""
    values = _context(state) | {"max_turns": ctx.max_turns}
    if choice is None:
        return load_prompt("interviewer/ask_free").render(**values), "interviewer/ask_free"
    area, step, mode = choice
    facts = facts_by_area(state["graph"], [area])[area][-FACTS_SHOWN:]
    asked_before = area in {a for a in state["asked_areas"] if a is not None}
    prompt = load_prompt("interviewer/ask").render(
        **values,
        area=area,
        step=step,
        mode=mode,
        facts=facts,
        asked_before=asked_before,
        coverage=state["coverage"],
    )
    return prompt, "interviewer/ask"


def render_mark(state: RunState) -> str:
    """The latest question and the client's answer to it, for the mark (T-317)."""
    turns = _turns(state["graph"])
    question = next(t.text for t in reversed(turns) if t.role == "agent")
    return load_prompt("interviewer/mark").render(question=question, answer=turns[-1].text)


def choose_area(state: RunState, marks: list[str | None]) -> tuple[str, int, Mode] | None:
    """The area of the next question, picked by code (T-317, the second attempt): the latest area
    again a step simpler if the client did not understand, the latest area once more if the answer
    was vague, else the first of the queue; None — nothing is left to ask."""
    asked = state["asked_areas"]
    redo = again(state["graph"], asked, marks)
    if redo:
        return redo[0], redo[1], "rephrase"
    vague = clarify(asked, marks)
    if vague:
        return vague, language_step(asked, marks, vague), "clarify"
    found = next_gaps({**state, "answer_marks": marks})
    if not found:
        return None
    area = found[0][0]
    return area, language_step(asked, marks, area), "new"


def next_gaps(state: RunState) -> list[tuple[str, int, int]]:
    """The areas to ask about, in the order of coverage.queue() (T-305); an area asked
    SAME_AREA times in a row goes last."""
    marks = state.get("answer_marks", [])
    found = queue(state["coverage"], state["graph"], state["asked_areas"], marks)
    recent = state["asked_areas"][-SAME_AREA:]
    if len(recent) == SAME_AREA and len(set(recent)) == 1 and len(found) > 1:
        found.sort(key=lambda g: g[0] == recent[0])  # stable: the rest keep their order
    return found


def questionnaire() -> list[str]:
    """The fixed questions of the B3 baseline (T-405), one per line of the file."""
    text = load_prompt("interviewer/questionnaire").render()
    return [line.strip() for line in text.splitlines() if line.strip()]


async def interviewer(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = start(runtime, "interviewer")
    if state["stop"] is not None:
        return {}
    if ctx.interviewer == "questionnaire":  # B3: the next fixed question, no model
        questions = questionnaire()
        if state["turns"] >= len(questions):
            ctx.events.emit("interview_end", reason="questionnaire", turns=state["turns"])
            return {"question": None, "interview_done": True}
        ctx.events.emit("question", turn=state["turns"] + 1, area=None)
        return {
            "question": questions[state["turns"]],
            "asked_areas": [*state["asked_areas"], None],
        }
    if not tracked(ctx):
        return await _ask_free(state, ctx)
    budget = state["budget"]
    asked_before = state["asked_areas"]
    marks = list(state.get("answer_marks", []))
    previous = marked = None
    try:
        if len(marks) < len(asked_before):  # the mark of the latest answer, by its own call
            template = load_prompt("interviewer/mark")
            mark, budget = await ctx.ask(
                "interviewer", render_mark(state), Mark, budget, template=template
            )
            marked = previous = mark.previous
            if marked == NOT_UNDERSTOOD and not latest_told_nothing(state["graph"], asked_before):
                previous = "ok"  # an answer that told something new was understood
            marks = [*marks, *[None] * (len(asked_before) - len(marks) - 1), previous]
        choice = choose_area(state, marks)
        if choice is None:  # the answer was understood and nothing is left to ask
            reason = finished(state["coverage"], [])
            ctx.events.emit("interview_end", reason=reason, turns=state["turns"], previous=previous)
            return {
                "budget": budget,
                "question": None,
                "interview_done": True,
                "answer_marks": marks,
            }
        prompt, name = render_question(state, ctx, choice)
        question, budget = await ctx.ask(
            "interviewer", prompt, Question, budget, template=load_prompt(name)
        )
    except BudgetExceeded:
        ctx.events.emit("stop", reason="budget", node="interviewer")
        return {"stop": "budget"}
    area, step, mode = choice
    ctx.events.emit(
        "question",
        turn=state["turns"] + 1,
        area=area,
        previous=previous,
        step=step,
        mode=mode,
        **({"marked": marked} if marked != previous else {}),  # the model's own mark, kept
    )
    return {
        "question": question.text,
        "budget": budget,
        "asked_areas": [*asked_before, area],
        "answer_marks": marks,
    }


async def _ask_free(state: RunState, ctx: RunContext) -> dict[str, Any]:
    """M1: the model asks what it likes and decides when to stop; no marks, no areas."""
    prompt, name = render_question(state, ctx)
    try:
        question, budget = await ctx.ask(
            "interviewer", prompt, Question, state["budget"], template=load_prompt(name)
        )
    except BudgetExceeded:
        ctx.events.emit("stop", reason="budget", node="interviewer")
        return {"stop": "budget"}
    if question.done:
        ctx.events.emit("interview_end", reason="interviewer", turns=state["turns"])
        return {"budget": budget, "question": None, "interview_done": True}
    ctx.events.emit("question", turn=state["turns"] + 1, area=question.area)
    return {
        "question": question.text,
        "budget": budget,
        "asked_areas": [*state["asked_areas"], question.area],
    }


def tracked(ctx: RunContext) -> bool:
    """The coverage interviewer (M2) marks answers and steps its language (T-317); M1 does not."""
    return ctx.interviewer == "coverage"


def finished(counted: Coverage, left: list[tuple[str, int, int]]) -> str | None:
    """Why the coverage interviewer stops (T-301, T-305, T-318): every area asked and the coverage
    reached, or every open area told nothing; None while something is left to ask."""
    if left:
        return None
    return "coverage" if counted.complete else "saturated"


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
    coverage reached once every area has been asked (with the tracker; the brief alone does not
    end it, T-318), every area left closed (T-305), the turn limit, «/готово», or the agents
    stopped."""
    ctx = start(runtime, "coverage")
    counted = coverage_of(state["graph"], state["coverage"].need)
    tracker = ctx.interviewer == "coverage"
    marks = state.get("answer_marks", [])
    # T-317: an empty latest answer keeps its area open until the interviewer marks it
    left = queue(counted, state["graph"], state["asked_areas"], marks, pending=True)
    end = finished(counted, left) if tracker else None
    reached = end == "coverage"  # every area asked once (T-305, T-318)
    saturated = end == "saturated"
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
