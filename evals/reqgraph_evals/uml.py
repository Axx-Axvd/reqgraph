"""Modeler's views on the dev briefs (T-207): intake -> Analyst -> Modeler, then the use case
diagram and the C4 model are compiled by Kroki (SCH-004, SCH-005, online) and checked for orphans.

The threshold of T-207: SCH-004 and SCH-005 clean after at most 3 answers of the views question in
100% of the runs; every UC and C4 element realizes an FR (no TRC-003 among them); every role has a
use case. One CSV row per scenario and repeat.
"""

import csv
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from importlib.metadata import version
from pathlib import Path
from typing import Any

from pydantic_ai.models import Model
from reqgraph.agents.modeler_views import VIEW_PREFIXES, c4_file, uml_file, view_problems
from reqgraph.agents.nodes import run_project
from reqgraph.agents.runtime import MemoryEvents, RunContext
from reqgraph.checks.registry import all_checks
from reqgraph.checks.runner import run_checks
from reqgraph.graph.nodes import C4Node
from reqgraph.llm.config import load_roles

from reqgraph_evals.analyst import DEV, SCENARIOS, _project
from reqgraph_evals.modeler import _graph

MAX_ANSWERS = 3
_CHECKS = ("SCH-004", "SCH-005", "TRC-003")


@dataclass
class Row:
    scenario: str
    repeat: int
    model: str = ""
    provider: str = ""
    temperature: float = 0.0
    seed: int | None = None
    prompt_hash: str = ""  # of the views prompt
    package_version: str = ""
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    attempts: int = 0  # answers to the views question, 1..3
    functional: int = 0
    actors: int = 0
    use_cases: int = 0
    containers: int = 0
    externals: int = 0
    has_uml: bool = False
    has_c4: bool = False
    sch004: int = 0  # Kroki online; -1: not checked (no Kroki)
    sch005: int = 0
    orphans: int = 0  # TRC-003 on UC and C4
    roles_without_uc: int = 0
    dropped: int = 0  # problems the best answer still had
    error: str = ""


CSV_FIELDS = [f.name for f in fields(Row)]


async def run_scenario(
    scenario: str,
    repeat: int,
    *,
    profile: str = "free",
    models: Mapping[str, Model] | None = None,
    root: Path = SCENARIOS,
    offline: bool = False,
) -> Row:
    brief = (root / scenario / "brief.md").read_text(encoding="utf-8")
    cfg = load_roles()
    row = Row(
        scenario, repeat, temperature=cfg.defaults.temperature, package_version=version("reqgraph")
    )
    events = MemoryEvents()
    with tempfile.TemporaryDirectory() as tmp:
        store = _project(Path(tmp), scenario, profile)
        ctx = RunContext.for_project(
            store.load(), events=events, models=models or {}, offline=offline
        )
        try:
            out = await _graph().ainvoke(ctx.initial_state("brief", brief=brief), context=ctx)
            project = run_project(ctx, out)
            checks = [c for c in all_checks() if c.id in _CHECKS]
            report = await run_checks(project, checks, offline=offline)
        except Exception as exc:  # a failed run is a result too (CLAUDE.md, honesty)
            row.error = f"{type(exc).__name__}: {exc}"[:300]
            _calls(row, events.events, cfg)
            return row
    _calls(row, events.events, cfg)
    graph, files = project.graph, project.files
    row.functional = len(graph.nodes_of("FR"))
    row.actors = len(graph.nodes_of("ACT"))
    row.use_cases = len(graph.nodes_of("UC"))
    c4 = [n for n in graph.nodes_of("C4") if isinstance(n, C4Node)]
    row.containers = sum(n.c4_kind == "container" for n in c4)
    row.externals = sum(n.c4_kind == "external" for n in c4)
    row.has_uml, row.has_c4 = uml_file(files) in files, c4_file(files) in files
    row.attempts = sum(e["type"] == "views_check" for e in events.events)
    answers = [e for e in events.events if e["type"] == "views_check"]
    row.dropped = min((len(e["problems"]) for e in answers), default=0)
    row.roles_without_uc = sum("у роли нет" in p for p in view_problems(graph, files))
    for check_id in ("SCH-004", "SCH-005"):
        found = [f for f in report.findings if f.check_id == check_id]
        skipped = any(f.severity == "info" for f in found)
        errors = sum(f.severity == "error" for f in found)
        setattr(row, check_id.lower().replace("-", ""), -1 if skipped and not errors else errors)
    row.orphans = sum(
        f.check_id == "TRC-003" and f.node_ids[0].startswith(VIEW_PREFIXES) for f in report.findings
    )
    return row


def _calls(row: Row, events: Sequence[dict[str, Any]], cfg: Any) -> None:
    calls = [e for e in events if e["type"] == "llm_call"]
    row.llm_calls = len(calls)
    mine = [c for c in calls if c["role"] == "modeler_views"]
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


def passed(row: Row) -> bool:
    """The run meets T-207: both files compile, no orphans, every role has a use case."""
    return (
        not row.error
        and row.has_uml
        and row.has_c4
        and 1 <= row.attempts <= MAX_ANSWERS
        and row.sch004 == 0
        and row.sch005 == 0
        and row.orphans == 0
        and row.roles_without_uc == 0
    )


def write_csv(rows: Sequence[Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def summary_markdown(rows: Sequence[Row]) -> str:
    ok = sum(passed(r) for r in rows)
    compiled = sum(r.sch004 == 0 and r.sch005 == 0 and r.has_uml and r.has_c4 for r in rows)
    verdict = "да" if rows and ok == len(rows) else "нет"
    lines = [
        "# Modeler: сценарии использования и C4 на dev-брифах",
        "",
        f"Прогонов: {len(rows)}; PlantUML и Structurizr компилируются (SCH-004, SCH-005): "
        f"{compiled}; все условия T-207 выполнены: {ok}. Порог T-207 (100% прогонов за ≤ "
        f"{MAX_ANSWERS} ответа, без сирот UC и C4, сценарий у каждой роли) выполнен: {verdict}.",
        "",
        "SCH-004 и SCH-005: −1 — Kroki недоступен, не проверено.",
        "",
        "| Сценарий | Повтор | Модель | Ответов | ФТ | Ролей | UC | Контейнеров | Внешних "
        "| SCH-004 | SCH-005 | Сирот | Ролей без UC | Осталось проблем | Токены | Время, с "
        "| Ошибка |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.scenario} | {r.repeat} | {r.provider}/{r.model} | {r.attempts} "
            f"| {r.functional} | {r.actors} | {r.use_cases} | {r.containers} | {r.externals} "
            f"| {r.sch004} | {r.sch005} | {r.orphans} | {r.roles_without_uc} | {r.dropped} "
            f"| {r.input_tokens + r.output_tokens} | {r.latency_ms / 1000:.1f} | {r.error} |"
        )
    return "\n".join(lines) + "\n"


__all__ = ["DEV", "Row", "passed", "run_scenario", "summary_markdown", "write_csv"]
