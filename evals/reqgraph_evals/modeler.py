"""Modeler on the dev briefs (T-203): intake -> Analyst -> Modeler, then every check.

The threshold of T-203: SCH-002 clean for all processes after at most 3 answers, and at least
80% of the processes without SND-001 findings. One CSV row per scenario and repeat.
"""

import csv
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from importlib.metadata import version
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from pydantic_ai.models import Model
from reqgraph.agents.analyst import analyst
from reqgraph.agents.modeler import modeler
from reqgraph.agents.nodes import intake, run_project
from reqgraph.agents.runtime import MemoryEvents, RunContext
from reqgraph.agents.state import RunState
from reqgraph.checks.runner import run_checks
from reqgraph.graph.nodes import ProcessNode
from reqgraph.llm.config import load_roles

from reqgraph_evals.analyst import DEV, SCENARIOS, _project

REACHABLE_SHARE = 0.8  # T-203: SND-001 clean for >= 80% of the processes


@dataclass
class Row:
    scenario: str
    repeat: int
    model: str = ""
    provider: str = ""
    temperature: float = 0.0
    seed: int | None = None
    prompt_hash: str = ""  # of the Modeler's prompt
    package_version: str = ""
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    attempts: int = 0  # the Modeler's answers, 1..3
    applied: bool = False
    functional: int = 0  # FR written by the Analyst
    processes: int = 0
    tasks: int = 0  # task steps in all processes
    entities: int = 0
    sch001: int = 0
    sch002: int = 0
    sch003: int = 0
    snd001_processes: int = 0  # processes with SND-001 findings
    reachable_share: float = 0.0
    snd002: int = 0
    snd003: int = 0
    snd004: int = 0
    trc002: int = 0  # FR not realized by any model element
    trc003: int = 0  # orphan model elements
    trc004: int = 0
    error: str = ""


CSV_FIELDS = [f.name for f in fields(Row)]


def _graph() -> Any:
    g = StateGraph(RunState, context_schema=RunContext)
    for name, node in (("intake", intake), ("analyst", analyst), ("modeler", modeler)):
        g.add_node(name, node)
    g.add_edge(START, "intake")
    g.add_edge("intake", "analyst")
    g.add_edge("analyst", "modeler")
    g.add_edge("modeler", END)
    return g.compile()


async def run_scenario(
    scenario: str,
    repeat: int,
    *,
    profile: str = "free",
    models: Mapping[str, Model] | None = None,
    root: Path = SCENARIOS,
) -> Row:
    brief = (root / scenario / "brief.md").read_text(encoding="utf-8")
    cfg = load_roles()
    row = Row(
        scenario, repeat, temperature=cfg.defaults.temperature, package_version=version("reqgraph")
    )
    events = MemoryEvents()
    with tempfile.TemporaryDirectory() as tmp:
        store = _project(Path(tmp), scenario, profile)
        ctx = RunContext.for_project(store.load(), events=events, models=models or {}, offline=True)
        try:
            out = await _graph().ainvoke(ctx.initial_state("brief", brief=brief), context=ctx)
            report = await run_checks(run_project(ctx, out), offline=True)
        except Exception as exc:  # a failed run is a result too (CLAUDE.md, honesty)
            row.error = f"{type(exc).__name__}: {exc}"[:300]
            _calls(row, events.events, cfg)
            return row
    _calls(row, events.events, cfg)
    graph = out["graph"]
    row.functional = len(graph.nodes_of("FR"))
    processes = [n for n in graph.nodes_of("PRC") if isinstance(n, ProcessNode)]
    row.processes = len(processes)
    steps = [e for p in processes for e in (p.dsl or {}).get("nodes", [])]
    row.tasks = sum(e.get("type") in ("task", "user_task", "service_task") for e in steps)
    row.entities = len(graph.nodes_of("ENT"))
    ends = [e for e in events.events if e["type"] == "agent_end" and e["agent"] == "modeler"]
    row.applied = bool(ends)
    row.attempts = sum(e["type"] == "self_check" for e in events.events)
    counts: dict[str, int] = {}
    unreachable: set[str] = set()
    for finding in report.findings:
        counts[finding.check_id] = counts.get(finding.check_id, 0) + 1
        if finding.check_id == "SND-001":
            unreachable.update(n.split(".")[0] for n in finding.node_ids)
    row.snd001_processes = len(unreachable)
    row.reachable_share = round(1 - len(unreachable) / row.processes, 3) if row.processes else 0.0
    for check_id in (
        "SCH-001",
        "SCH-002",
        "SCH-003",
        "SND-002",
        "SND-003",
        "SND-004",
        "TRC-002",
        "TRC-003",
        "TRC-004",
    ):
        setattr(row, check_id.lower().replace("-", ""), counts.get(check_id, 0))
    return row


def _calls(row: Row, events: Sequence[dict[str, Any]], cfg: Any) -> None:
    calls = [e for e in events if e["type"] == "llm_call"]
    row.llm_calls = len(calls)
    mine = [c for c in calls if c["role"] == "modeler"]
    if mine:
        last = mine[-1]
        row.model, row.provider = last["model"], last["provider"]
        row.prompt_hash = last.get("prompt_hash", "")
        provider = cfg.providers.get(row.provider)
        row.seed = cfg.defaults.seed if provider is None or provider.supports_seed else None
    row.input_tokens = sum(c["input_tokens"] for c in calls)
    row.output_tokens = sum(c["output_tokens"] for c in calls)
    row.cost_usd = round(sum(c["cost_usd"] for c in calls), 6)
    row.latency_ms = sum(c["latency_ms"] for c in calls)


def write_csv(rows: Sequence[Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def summary_markdown(rows: Sequence[Row]) -> str:
    processes = sum(r.processes for r in rows)
    reachable = processes - sum(r.snd001_processes for r in rows)
    share = reachable / processes if processes else 0.0
    dsl_clean = all(r.applied and r.sch002 == 0 for r in rows) and all(
        r.attempts <= 3 for r in rows
    )
    verdict = "да" if dsl_clean and share >= REACHABLE_SHARE else "нет"
    lines = [
        "# Modeler на dev-брифах",
        "",
        f"Прогонов: {len(rows)}; процессов: {processes}; без SND-001: {reachable} ({share:.0%}); "
        f"SCH-002 чист во всех прогонах за ≤ 3 попытки: {'да' if dsl_clean else 'нет'}. "
        f"Порог T-203 (SCH-002 — 100%, SND-001 — не меньше {REACHABLE_SHARE:.0%}) "
        f"выполнен: {verdict}.",
        "",
        "| Сценарий | Повтор | Модель | Попыток | ФТ | Процессов | Задач | Сущностей "
        "| SCH-002 | Без SND-001 | SND-002 | SND-003 | SND-004 | TRC-002 | TRC-003 | Токены "
        "| Время, с | Ошибка |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.scenario} | {r.repeat} | {r.provider}/{r.model} | {r.attempts} | {r.functional} "
            f"| {r.processes} | {r.tasks} | {r.entities} | {r.sch002} | {r.reachable_share:.0%} "
            f"| {r.snd002} | {r.snd003} | {r.snd004} | {r.trc002} | {r.trc003} "
            f"| {r.input_tokens + r.output_tokens} | {r.latency_ms / 1000:.1f} | {r.error} |"
        )
    return "\n".join(lines) + "\n"


__all__ = ["DEV", "Row", "run_scenario", "summary_markdown", "write_csv"]
