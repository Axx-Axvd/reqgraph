"""The whole pipeline with the repair loop on the dev briefs (T-205): does it converge, or stop
with needs_human? With --reviewer template — the «without Reviewer» ablation (09_eval)."""

import csv
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

from pydantic_ai.models import Model
from reqgraph.agents.graph import build_graph
from reqgraph.agents.runtime import MemoryEvents, RunContext
from reqgraph.llm.config import load_roles

from reqgraph_evals.analyst import SCENARIOS, _project


@dataclass
class Row:
    scenario: str
    repeat: int
    reviewer: str = "llm"
    models: str = ""  # provider/model of every role that answered
    temperature: float = 0.0
    package_version: str = ""
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    iterations: int = 0
    stop: str = ""  # budget | needs_human | "" (converged or ran out of rounds)
    errors_first: int = 0  # errors of the first CI report
    errors_final: int = 0
    warnings_final: int = 0
    converged: bool = False  # the final report has no errors
    error: str = ""


CSV_FIELDS = [f.name for f in fields(Row)]


async def run_scenario(
    scenario: str,
    repeat: int,
    *,
    profile: str = "free",
    reviewer: Literal["llm", "template"] = "llm",
    models: Mapping[str, Model] | None = None,
    root: Path = SCENARIOS,
) -> Row:
    brief = (root / scenario / "brief.md").read_text(encoding="utf-8")
    cfg = load_roles()
    row = Row(
        scenario,
        repeat,
        reviewer,
        temperature=cfg.defaults.temperature,
        package_version=version("reqgraph"),
    )
    events = MemoryEvents()
    with tempfile.TemporaryDirectory() as tmp:
        store = _project(Path(tmp), scenario, profile)
        ctx = RunContext.for_project(
            store.load(), events=events, models=models or {}, offline=True, reviewer=reviewer
        )
        try:
            out = await build_graph().ainvoke(ctx.initial_state("brief", brief=brief), context=ctx)
        except Exception as exc:  # a failed run is a result too (CLAUDE.md, honesty)
            row.error = f"{type(exc).__name__}: {exc}"[:300]
            _calls(row, events.events)
            return row
    _calls(row, events.events)
    reports = [e for e in events.events if e["type"] == "ci_report"]
    row.iterations = out["iteration"]
    row.stop = out["stop"] or ""
    row.errors_first = reports[0]["errors"] if reports else 0
    row.errors_final = out["ci"].summary.errors if out["ci"] else 0
    row.warnings_final = out["ci"].summary.warnings if out["ci"] else 0
    row.converged = out["ci"] is not None and out["ci"].ok
    return row


def _calls(row: Row, events: Sequence[dict[str, Any]]) -> None:
    calls = [e for e in events if e["type"] == "llm_call"]
    row.llm_calls = len(calls)
    by_role = {c["role"]: f"{c['provider']}/{c['model']}" for c in calls}
    row.models = "; ".join(f"{role}={model}" for role, model in sorted(by_role.items()))
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
    converged = sum(r.converged for r in rows)
    human = sum(r.stop == "needs_human" for r in rows)
    other = len(rows) - converged - human
    verdict = "да" if other == 0 else "нет"
    lines = [
        "# Цикл ремонта на dev-брифах",
        "",
        f"Прогонов: {len(rows)}; сошлись (нет ошибок): {converged}; остановились с needs_human: "
        f"{human}; иначе (лимит кругов, бюджет, сбой): {other}. Критерий T-205 («сходится или "
        f"needs_human») выполнен: {verdict}.",
        "",
        "| Сценарий | Повтор | Reviewer | Кругов | Стоп | Ошибок в начале | Ошибок в конце "
        "| Предупр. | Вызовов LLM | Токены | Время, с | Ошибка |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.scenario} | {r.repeat} | {r.reviewer} | {r.iterations} | {r.stop or '—'} "
            f"| {r.errors_first} | {r.errors_final} | {r.warnings_final} | {r.llm_calls} "
            f"| {r.input_tokens + r.output_tokens} | {r.latency_ms / 1000:.1f} | {r.error} |"
        )
    return "\n".join(lines) + "\n"
