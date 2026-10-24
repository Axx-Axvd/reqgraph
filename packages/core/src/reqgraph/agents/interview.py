"""`reqgraph interview` (T-301): questions and answers in a project folder, with pause and resume.

The run graph pauses on every question (interrupt). Its state is checkpointed into the project
folder (.reqgraph/checkpoints.sqlite, LangGraph's SQLite saver), so an interview stopped with
Ctrl+C, «/пауза» or a closed terminal goes on from the same question after a restart. The answers
come from a callback: the terminal in the CLI, the stakeholder simulator in the evals (T-302).
Once the interview is over the pipeline runs as in `reqgraph run` and writes the same reports.
"""

import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from langgraph.types import Command
from pydantic_ai.models import Model

from reqgraph.agents.graph import build_graph
from reqgraph.agents.nodes import DONE
from reqgraph.agents.run import (
    ConsoleEvents,
    RunSummary,
    load_project,
    summarize,
    write_reports,
)
from reqgraph.agents.runtime import JsonlEvents, RunContext, checkpoint_serde
from reqgraph.agents.state import BudgetState, RunState
from reqgraph.checks.report import CIReport
from reqgraph.graph.store.formats import BRIEF_FILE

STATE_DIR = ".reqgraph"  # checkpoints of the project's runs; not for git
EVENTS = "interview-events.jsonl"

if TYPE_CHECKING:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

Reply = str | Mapping[str, Any] | None  # an answer, DONE to end the interview, None to pause
Answer = Callable[[str, int], Awaitable[Reply]]


@dataclass
class Outcome:
    """A paused interview has no summary yet; a finished one has the reports of the run."""

    paused: bool
    turns: int
    summary: RunSummary | None = None
    report: CIReport | None = None


@asynccontextmanager
async def sqlite_saver(path: Path) -> AsyncIterator["AsyncSqliteSaver"]:
    """LangGraph's SQLite checkpointer with our serializer (only our state types are restored)."""
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as conn:
        yield AsyncSqliteSaver(conn, serde=checkpoint_serde())


def _thread_file(root: Path) -> Path:
    return root / STATE_DIR / "interview.json"


def _open_thread(root: Path) -> dict[str, Any] | None:
    path = _thread_file(root)
    if not path.is_file():
        return None
    thread: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return thread if thread.get("status") == "open" else None


def _save_thread(root: Path, thread: dict[str, Any]) -> None:
    folder = root / STATE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ".gitignore").write_text("*\n", encoding="utf-8")  # checkpoints stay local
    _thread_file(root).write_text(json.dumps(thread, ensure_ascii=False), encoding="utf-8")


def has_open_interview(root: Path) -> bool:
    return _open_thread(root) is not None


async def interview_project(
    root: Path,
    answer: Answer,
    *,
    brief: str | None = None,
    restart: bool = False,
    profile: str | None = None,
    budget_usd: float | None = None,
    max_turns: int | None = None,
    max_iter: int | None = None,
    reviewer: Literal["llm", "template"] = "llm",
    interviewer: Literal["coverage", "free"] = "coverage",
    offline: bool = False,
    models: Mapping[str, Model] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> Outcome:
    """Start or resume the project's interview; ask until it is over or the answer pauses it."""
    store, project = load_project(root)
    thread = None if restart else _open_thread(root)
    events_file = root / "reports" / EVENTS
    if thread is None:
        thread = {"thread_id": uuid.uuid4().hex[:12], "started": time.time(), "status": "open"}
        events_file.unlink(missing_ok=True)
    text = brief if brief is not None else project.files.get(BRIEF_FILE)  # used at the start only
    options: dict[str, Any] = {"store": store, "offline": offline, "models": models or {}}
    options |= {"reviewer": reviewer, "interviewer": interviewer}
    if profile is not None:
        options["profile"] = profile
    if max_iter is not None:
        options["max_iter"] = max_iter
    if max_turns is not None:
        options["max_turns"] = max_turns
    tee = ConsoleEvents(JsonlEvents(events_file), on_line, interviewing=True)
    ctx = RunContext.for_project(project, events=tee, **options)
    config: Any = {"configurable": {"thread_id": thread["thread_id"]}}
    _save_thread(root, thread)

    async with sqlite_saver(root / STATE_DIR / "checkpoints.sqlite") as saver:
        graph = build_graph(checkpointer=saver)
        snapshot = await graph.aget_state(config)
        if snapshot.next:  # paused on a question: the state, budget and turns are in the checkpoint
            result: dict[str, Any] = {"__interrupt__": snapshot.interrupts}
        else:
            budget = BudgetState.default()
            if budget_usd is not None:
                budget = BudgetState(usd=budget_usd, tokens=budget.tokens)
            state = ctx.initial_state("interview", budget=budget, brief=text or None)
            result = await graph.ainvoke(state, config, context=ctx)
        while "__interrupt__" in result:
            pending = result["__interrupt__"][0].value
            reply = await answer(pending["question"], pending["turn"])
            if reply is None:
                return Outcome(paused=True, turns=pending["turn"] - 1)
            resume = dict(DONE) if reply == DONE else str(reply)
            result = await graph.ainvoke(Command(resume=resume), config, context=ctx)
    out = RunState(**result)  # type: ignore[typeddict-item]
    thread["status"] = "done"
    _save_thread(root, thread)
    report = out["ci"]
    assert report is not None  # ci_check always runs
    calls = [e for e in _read_events(events_file) if e["type"] == "llm_call"]
    seconds = time.time() - thread["started"]  # wall time since the start, pauses included
    budget_total = out["budget"].usd
    summary = summarize(ctx, out, report, calls, seconds, budget_total)
    write_reports(root, summary, report)
    return Outcome(paused=False, turns=out["turns"], summary=summary, report=report)


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
