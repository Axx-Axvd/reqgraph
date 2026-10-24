"""Standards on the dev briefs (T-204): intake -> Analyst -> Modeler -> Standards, then the checks.

The threshold of T-204: TPL-001 — at least 80% of the required SRS sections filled.
"""

import csv
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from importlib.metadata import version
from itertools import pairwise
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from pydantic_ai.models import Model
from reqgraph.agents.analyst import analyst
from reqgraph.agents.modeler import modeler
from reqgraph.agents.nodes import intake, run_project
from reqgraph.agents.runtime import MemoryEvents, RunContext
from reqgraph.agents.standards import standards
from reqgraph.agents.state import RunState
from reqgraph.checks.runner import run_checks
from reqgraph.graph.nodes import SectionNode
from reqgraph.llm.config import load_roles
from reqgraph.standards import load_structure

from reqgraph_evals.analyst import SCENARIOS, _project

FILLED_SHARE = 0.8  # T-204: TPL-001 >= 80% of the required sections


@dataclass
class Row:
    scenario: str
    repeat: int
    model: str = ""
    provider: str = ""
    temperature: float = 0.0
    seed: int | None = None
    prompt_hash: str = ""  # of the Standards prompt
    package_version: str = ""
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    retried: bool = False
    sections: int = 0
    required: int = 0
    empty_required: int = 0  # TPL-001 findings
    filled_share: float = 0.0
    glossary_terms: int = 0
    purpose_chars: int = 0
    scope_chars: int = 0
    error: str = ""


CSV_FIELDS = [f.name for f in fields(Row)]


def _graph() -> Any:
    g = StateGraph(RunState, context_schema=RunContext)
    steps = (
        ("intake", intake),
        ("analyst", analyst),
        ("modeler", modeler),
        ("standards", standards),
    )
    for name, node in steps:
        g.add_node(name, node)
    g.add_edge(START, "intake")
    for (a, _), (b, _) in pairwise(steps):
        g.add_edge(a, b)
    g.add_edge("standards", END)
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
    structure = load_structure("iso29148_srs")
    row.required = len(structure.required)
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
    sections = {n.id: n for n in out["graph"].nodes_of("SEC") if isinstance(n, SectionNode)}
    row.sections = len(sections)
    row.empty_required = sum(f.check_id == "TPL-001" for f in report.findings)
    row.filled_share = round(1 - row.empty_required / row.required, 3)
    row.retried = any(
        e["type"] == "patch_retry" and e["agent"] == "standards" for e in events.events
    )
    glossary = sections.get("SEC-SRS-1.4")
    row.glossary_terms = len(glossary.text.splitlines()) if glossary and glossary.text else 0
    row.purpose_chars = len(sections["SEC-SRS-1.1"].text) if "SEC-SRS-1.1" in sections else 0
    row.scope_chars = len(sections["SEC-SRS-1.2"].text) if "SEC-SRS-1.2" in sections else 0
    return row


def _calls(row: Row, events: Sequence[dict[str, Any]], cfg: Any) -> None:
    calls = [e for e in events if e["type"] == "llm_call"]
    row.llm_calls = len(calls)
    mine = [c for c in calls if c["role"] == "standards"]
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


def _yes(value: bool) -> str:
    return "да" if value else "нет"


def summary_markdown(rows: Sequence[Row]) -> str:
    required = sum(r.required for r in rows)
    filled = required - sum(r.empty_required for r in rows)
    share = filled / required if required else 0.0
    verdict = "да" if share >= FILLED_SHARE and not any(r.error for r in rows) else "нет"
    lines = [
        "# Standards на dev-брифах",
        "",
        f"Прогонов: {len(rows)}; обязательных разделов SRS: {required}; заполнено: {filled} "
        f"({share:.0%}); порог T-204 — не меньше {FILLED_SHARE:.0%}: {verdict}.",
        "",
        "| Сценарий | Повтор | Модель | Повтор запроса | Разделов | Пустых обязательных "
        "| Заполнено | Терминов | Назначение, симв. | Область, симв. | Токены | Время, с "
        "| Ошибка |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.scenario} | {r.repeat} | {r.provider}/{r.model} | {_yes(r.retried)} "
            f"| {r.sections} | {r.empty_required} | {r.filled_share:.0%} | {r.glossary_terms} "
            f"| {r.purpose_chars} | {r.scope_chars} | {r.input_tokens + r.output_tokens} "
            f"| {r.latency_ms / 1000:.1f} | {r.error} |"
        )
    return "\n".join(lines) + "\n"
