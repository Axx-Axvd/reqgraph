"""One run from a brief to a report (T-206): what `reqgraph init` and `reqgraph run` call.

The project folder is the store: requirements, processes, the ERD and reports/ (ci-report.json|md,
run-events.jsonl, run-summary.json) are written into it. A run never touches a reference project.
"""

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

from pydantic_ai.models import Model

from reqgraph.agents.graph import build_graph
from reqgraph.agents.nodes import ReferenceProject
from reqgraph.agents.runtime import JsonlEvents, RunContext
from reqgraph.agents.state import BudgetState, RunState
from reqgraph.checks.report import CIReport
from reqgraph.dsl.readers import model_readers
from reqgraph.graph.store import FileStore, StoreError
from reqgraph.graph.store.config import ModelsConfig, ProjectConfig, ProjectInfo
from reqgraph.graph.store.formats import BRIEF_FILE, CONFIG_FILE, render_config
from reqgraph.llm.config import load_roles

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_STEPS = {
    "intake": "Бриф → реплики заказчика",
    "interviewer": "Interviewer: вопрос",
    "analyst": "Analyst: требования",
    "modeler": "Modeler: процессы и модель данных",
    "standards": "Standards: разделы SRS",
    "ci_check": "Проверки",
    "reviewer": "Reviewer: задачи ремонта",
    "export": "Экспорт",
    "persist": "Сохранение проекта",
}


class RunFailed(RuntimeError):
    """The run cannot start: no project, no brief, a reference project."""


@dataclass
class RunSummary:
    project: str
    profile: str
    reviewer: str
    package_version: str
    budget_usd: float
    models: dict[str, str] = field(default_factory=dict)  # role -> provider/model
    prompt_hashes: dict[str, str] = field(default_factory=dict)  # prompt -> hash
    temperature: float = 0.0
    seeds: dict[str, int | None] = field(default_factory=dict)  # role -> seed sent (None: ignored)
    iterations: int = 0
    stop: str | None = None  # budget | needs_human | None
    errors: int = 0
    warnings: int = 0
    requirements: int = 0
    actors: int = 0
    processes: int = 0
    entities: int = 0
    sections: int = 0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0
    headline: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _Tee:
    """Events to the JSONL file (when written) and a short line per step to the console."""

    file: JsonlEvents | None
    on_line: Callable[[str], None] | None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def emit(self, type: str, **payload: Any) -> None:
        if self.file is not None:
            self.file.emit(type, **payload)
        if type == "llm_call":
            self.calls.append(payload)
        line = _line(type, payload)
        if line and self.on_line is not None:
            self.on_line(line)


def _line(type: str, payload: dict[str, Any]) -> str | None:
    if type == "node_start" and payload["node"] in _STEPS:
        return f"→ {_STEPS[payload['node']]}"
    if type == "self_check" and payload["problems"]:
        return f"  самопроверка {payload['attempt']}: проблем {len(payload['problems'])}"
    if type == "ci_report":
        return f"  ошибок {payload['errors']}, предупреждений {payload['warnings']}"
    if type == "repair":
        return f"  круг ремонта {payload['iteration']}: задач {len(payload['tasks'])}"
    if type == "needs_human":
        why = "ошибки не уходят" if payload.get("reason") == "stuck" else "круги кончились"
        return f"  нужен человек: {why}"
    if type == "stop":
        return f"  остановка: {payload['reason']}"
    return None


def init_project(
    root: Path,
    *,
    name: str,
    brief: str,
    project_id: str | None = None,
    profile: Literal["free", "cheap", "local"] = "free",
) -> Path:
    """A new project folder: reqgraph.yaml and brief.md."""
    if (root / CONFIG_FILE).exists():
        raise RunFailed(f"{root}: проект уже есть ({CONFIG_FILE})")
    pid = project_id or root.name.lower()
    if not _ID.fullmatch(pid):
        raise RunFailed(
            f"«{root.name}» не годится как id проекта: задайте --id латиницей (dental-1)"
        )
    config = ProjectConfig(
        project=ProjectInfo(id=pid, name=name), models=ModelsConfig(profile=profile)
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / CONFIG_FILE).write_text(render_config(config), encoding="utf-8")
    (root / BRIEF_FILE).write_text(brief, encoding="utf-8")
    return root


async def run_project(
    root: Path,
    *,
    brief: str | None = None,
    profile: str | None = None,
    budget_usd: float | None = None,
    max_iter: int | None = None,
    reviewer: Literal["llm", "template"] = "llm",
    offline: bool = False,
    write: bool = True,
    models: Mapping[str, Model] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> tuple[RunSummary, CIReport]:
    """Brief -> Analyst -> Modeler -> Standards -> checks -> repair; the report in any case."""
    store = FileStore(root, readers=model_readers())
    try:
        project = store.load()
    except StoreError as exc:
        raise RunFailed(f"проект не прочитан: {exc}") from None
    info = project.config.project
    if info.reference:
        raise RunFailed(f"{info.id}: эталонный проект — агенты не запускаются, только проверки")
    text = brief if brief is not None else project.files.get(BRIEF_FILE)
    if not text or not text.strip():
        raise RunFailed(f"{root}: нет брифа — положите {BRIEF_FILE} или задайте --brief")
    reports = root / "reports"
    events_file = reports / "run-events.jsonl"
    if write:
        events_file.unlink(missing_ok=True)
    tee = _Tee(JsonlEvents(events_file) if write else None, on_line)
    options: dict[str, Any] = {"store": store if write else None, "events": tee, "offline": offline}
    options |= {"models": models or {}, "reviewer": reviewer}
    if profile is not None:
        options["profile"] = profile
    if max_iter is not None:
        options["max_iter"] = max_iter
    ctx = RunContext.for_project(project, **options)
    budget = BudgetState.default()
    if budget_usd is not None:
        budget = BudgetState(usd=budget_usd, tokens=budget.tokens)
    started = time.perf_counter()
    try:
        result = await build_graph().ainvoke(
            ctx.initial_state("brief", budget=budget, brief=text), context=ctx
        )
        out = RunState(**result)  # type: ignore[typeddict-item]
    except ReferenceProject as exc:
        raise RunFailed(str(exc)) from None
    report = out["ci"]
    assert report is not None  # ci_check always runs
    summary = _summary(ctx, out, report, tee.calls, time.perf_counter() - started, budget.usd)
    if write:
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "ci-report.json").write_bytes(report.to_json().encode("utf-8"))
        (reports / "ci-report.md").write_bytes(report.to_markdown().encode("utf-8"))
        data = json.dumps(summary.to_dict(), ensure_ascii=False, indent=2) + "\n"
        (reports / "run-summary.json").write_bytes(data.encode("utf-8"))
    return summary, report


def _summary(
    ctx: RunContext,
    out: RunState,
    report: CIReport,
    calls: list[dict[str, Any]],
    seconds: float,
    budget_usd: float,
) -> RunSummary:
    graph = out["graph"]
    kinds = [n.kind for n in graph.nodes.values()]
    cfg = load_roles()
    seeds = {
        c["role"]: cfg.defaults.seed
        if c["provider"] not in cfg.providers or cfg.providers[c["provider"]].supports_seed
        else None
        for c in calls
    }
    return RunSummary(
        project=ctx.project.config.project.id,
        profile=ctx.profile or "",
        reviewer=ctx.reviewer,
        package_version=version("reqgraph"),
        budget_usd=budget_usd,
        models={c["role"]: f"{c['provider']}/{c['model']}" for c in calls},
        prompt_hashes={c["prompt"]: c["prompt_hash"] for c in calls if "prompt" in c},
        temperature=cfg.defaults.temperature,
        seeds=seeds,
        iterations=out["iteration"],
        stop=out["stop"],
        errors=report.summary.errors,
        warnings=report.summary.warnings,
        requirements=sum(kinds.count(k) for k in ("BR", "UR", "FR", "NFR", "CON")),
        actors=kinds.count("ACT"),
        processes=kinds.count("PRC"),
        entities=kinds.count("ENT"),
        sections=kinds.count("SEC"),
        llm_calls=len(calls),
        input_tokens=sum(c["input_tokens"] for c in calls),
        output_tokens=sum(c["output_tokens"] for c in calls),
        cost_usd=round(sum(c["cost_usd"] for c in calls), 6),
        seconds=round(seconds, 1),
        headline=report.headline(),
    )
