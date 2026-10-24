"""Analyst on the dev briefs (T-202): is the patch valid, how many requirements break ISO-001/003.

Only intake -> analyst runs (the rest of the pipeline is not built yet). The result is checked by
the same deterministic checks as `reqgraph check`; one CSV row per scenario and repeat, with the
model, provider, temperature, seed, prompt hash, package version, tokens, cost and time.
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
from reqgraph.agents.nodes import intake
from reqgraph.agents.runtime import MemoryEvents, RunContext
from reqgraph.agents.state import RunState
from reqgraph.checks.runner import run_checks
from reqgraph.checks.text import REQUIREMENT_KINDS
from reqgraph.graph.store import FileStore
from reqgraph.llm.config import load_roles

SCENARIOS = Path(__file__).resolve().parent.parent / "scenarios"
DEV = ("dev-01", "dev-02", "dev-03")
MEASURED = ("ISO-001", "ISO-003")  # the threshold of T-202: <= 15% of requirements
THRESHOLD = 0.15


@dataclass
class Row:
    scenario: str
    repeat: int
    model: str = ""
    provider: str = ""
    temperature: float = 0.0
    seed: int | None = None
    prompt_hash: str = ""
    package_version: str = ""
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    applied: bool = False  # the patch went into the graph
    retried: bool = False
    dropped: int = 0  # items the guard or the schema dropped after the retry
    requirements: int = 0
    actors: int = 0
    violating: int = 0  # requirements with ISO-001 or ISO-003
    violation_share: float = 0.0
    iso001: int = 0
    iso002: int = 0
    iso003: int = 0
    iso004: int = 0
    iso005: int = 0
    trc001: int = 0
    trc006: int = 0
    error: str = ""


CSV_FIELDS = [f.name for f in fields(Row)]


def _graph() -> Any:
    g = StateGraph(RunState, context_schema=RunContext)
    g.add_node("intake", intake)
    g.add_node("analyst", analyst)
    g.add_edge(START, "intake")
    g.add_edge("intake", "analyst")
    g.add_edge("analyst", END)
    return g.compile()


def _project(folder: Path, scenario: str, profile: str) -> FileStore:
    text = f'project:\n  id: {scenario}\n  name: "{scenario}"\nmodels:\n  profile: {profile}\n'
    (folder / "reqgraph.yaml").write_text(text, encoding="utf-8")
    return FileStore(folder)


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
        scenario=scenario,
        repeat=repeat,
        temperature=cfg.defaults.temperature,
        package_version=version("reqgraph"),
    )
    events = MemoryEvents()
    with tempfile.TemporaryDirectory() as tmp:
        store = _project(Path(tmp), scenario, profile)
        ctx = RunContext.for_project(store.load(), events=events, models=models or {})
        ctx.offline = True
        try:
            out = await _graph().ainvoke(ctx.initial_state("brief", brief=brief), context=ctx)
        except Exception as exc:  # a failed run is a result too (CLAUDE.md, honesty)
            row.error = f"{type(exc).__name__}: {exc}"[:300]
            _calls(row, events.events, cfg)
            return row
        report = await run_checks(ctx.project.with_graph(out["graph"]), offline=True)
    _calls(row, events.events, cfg)
    graph = out["graph"]
    kinds = [n.kind for n in graph.nodes.values()]
    row.requirements = sum(kinds.count(k) for k in REQUIREMENT_KINDS)
    row.actors = kinds.count("ACT")
    row.applied = any(e["type"] == "agent_end" for e in events.events)
    row.retried = any(e["type"] == "patch_retry" for e in events.events)
    row.dropped = sum(len(e["reasons"]) for e in events.events if e["type"] == "dropped")
    counts: dict[str, int] = {}
    violating: set[str] = set()
    for finding in report.findings:
        counts[finding.check_id] = counts.get(finding.check_id, 0) + 1
        if finding.check_id in MEASURED:
            violating.update(finding.node_ids)
    row.violating = len(violating)
    row.violation_share = round(row.violating / row.requirements, 3) if row.requirements else 0.0
    for check_id in ("ISO-001", "ISO-002", "ISO-003", "ISO-004", "ISO-005", "TRC-001", "TRC-006"):
        setattr(row, check_id.lower().replace("-", ""), counts.get(check_id, 0))
    return row


def _calls(row: Row, events: Sequence[dict[str, Any]], cfg: Any) -> None:
    calls = [e for e in events if e["type"] == "llm_call"]
    row.llm_calls = len(calls)
    if not calls:
        return
    last = calls[-1]
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


def _yes(value: bool) -> str:
    return "да" if value else "нет"


def summary_markdown(rows: Sequence[Row]) -> str:
    total = sum(r.requirements for r in rows)
    violating = sum(r.violating for r in rows)
    share = violating / total if total else 0.0
    verdict = "да" if share <= THRESHOLD and all(r.applied for r in rows) else "нет"
    lines = [
        "# Analyst на dev-брифах",
        "",
        f"Прогонов: {len(rows)}; требований: {total}; с нарушениями ISO-001/003: {violating} "
        f"({share:.0%}); порог T-202 — не больше {THRESHOLD:.0%}, все патчи применены: {verdict}.",
        "",
        "| Сценарий | Повтор | Модель | Применён | Повтор запроса | Отброшено | Требований "
        "| Нарушений | Доля | ISO-001 | ISO-003 | TRC-006 | Токены | Время, с | Ошибка |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.scenario} | {r.repeat} | {r.provider}/{r.model} | {_yes(r.applied)} "
            f"| {_yes(r.retried)} | {r.dropped} | {r.requirements} | {r.violating} "
            f"| {r.violation_share:.0%} | {r.iso001} | {r.iso003} | {r.trc006} "
            f"| {r.input_tokens + r.output_tokens} | {r.latency_ms / 1000:.1f} | {r.error} |"
        )
    return "\n".join(lines) + "\n"
