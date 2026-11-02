"""Analyst on the dev briefs (T-202): is the patch valid, how many requirements break ISO-001/003.

Only intake -> analyst runs. The result is checked by the same deterministic checks as
`reqgraph check`; one CSV row per scenario and repeat, with the model, provider, temperature, seed,
prompt hash, package version, tokens, cost and time.

T-311 adds what the spread between repeats needs: requirements by kind, the reasons of dropped
items, and how many facts of the brief (`in_brief` in hidden.yaml) the Analyst kept — the recall
of T-304 on those facts, with the judge of another model family (its calls and cost are written
apart). `save` writes the requirements of every run for reading them side by side.
"""

import csv
import json
import statistics
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from importlib.metadata import version
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from pydantic_ai.embeddings import EmbeddingModel
from pydantic_ai.models import Model
from reqgraph.agents.analyst import analyst
from reqgraph.agents.nodes import intake
from reqgraph.agents.runtime import MemoryEvents, RunContext
from reqgraph.agents.state import RunState
from reqgraph.checks.runner import run_checks
from reqgraph.checks.text import REQUIREMENT_KINDS
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.store import FileStore
from reqgraph.llm.config import load_roles
from reqgraph.llm.embed import embed, embedding_model
from reqgraph.llm.router import structured

from reqgraph_evals.metrics.recall import Verdict, found_requirements, judge_prompt, recall
from reqgraph_evals.scenario import load_scenario

SCENARIOS = Path(__file__).resolve().parent.parent / "scenarios"
DEV = ("dev-01", "dev-02", "dev-03")
MEASURED = ("ISO-001", "ISO-003")  # the threshold of T-202: <= 15% of requirements
THRESHOLD = 0.15
# T-311, the rule written before the measurement: on every brief the worst of the repeats keeps
# >= 80% of the facts of the brief and the most FRs are at most twice the fewest
BRIEF_SHARE = 0.8
FR_SPREAD = 2.0


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
    br: int = 0  # T-311: requirements by kind
    ur: int = 0
    fr: int = 0
    nfr: int = 0
    con: int = 0
    brief_facts: int = 0  # requirements of hidden.yaml stated in the brief
    brief_found: int = 0  # of them matched fully by the judge
    brief_partial: int = 0  # matched only partly
    brief_share: float = 0.0
    brief_missed: str = ""  # hidden ids not found
    judge_model: str = ""
    judge_calls: int = 0
    judge_cost_usd: float = 0.0
    dropped_reasons: str = ""
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
    brief_recall: bool = True,
    judge_model: Model | None = None,
    embedder: EmbeddingModel | None = None,
    save: Path | None = None,
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
    reasons = [r for e in events.events if e["type"] == "dropped" for r in e["reasons"]]
    row.dropped = len(reasons)
    row.dropped_reasons = " | ".join(reasons)[:500]
    for kind in REQUIREMENT_KINDS:
        setattr(row, kind.lower(), kinds.count(kind))
    if save is not None:
        _save(graph, save / f"{scenario}-{repeat}.json")
    if brief_recall:
        await _brief(row, graph, root, profile, judge_model, embedder)
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


def _save(graph: ArtifactGraph, path: Path) -> None:
    """The requirements of one run, for reading the repeats side by side."""
    items = [
        {
            "id": n.id,
            "title": getattr(n, "title", ""),
            "statement": getattr(n, "statement", ""),
            "assumption": n.assumption,
        }
        for kind in REQUIREMENT_KINDS
        for n in graph.nodes_of(kind)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


async def _brief(
    row: Row,
    graph: ArtifactGraph,
    root: Path,
    profile: str,
    judge_model: Model | None,
    embedder: EmbeddingModel | None,
) -> None:
    """How many facts of the brief became requirements: recall (T-304) on the in_brief ones."""
    facts = [
        h.model_copy(update={"in_brief": False})  # counted as hidden: matched told or not
        for h in load_scenario(row.scenario, root).hidden.requirements
        if h.in_brief
    ]
    row.brief_facts = len(facts)
    model, model_id = (embedder, embedder.model_name) if embedder else embedding_model(profile)
    calls = []

    async def vectors(texts: Sequence[str]) -> list[list[float]]:
        return await embed(texts, model=model, model_id=model_id)

    async def judge(reference: str, candidates: list[str]) -> Verdict:
        prompt = judge_prompt().render(reference=reference, candidates=candidates)
        verdict, stats = await structured(
            "judge", prompt, Verdict, profile=profile, model=judge_model
        )
        calls.append(stats)
        return verdict

    try:
        result = await recall(facts, found_requirements(graph), embed=vectors, judge=judge)
    except Exception as exc:  # the judge failed: the run itself still counts
        row.error = (row.error + f" judge: {type(exc).__name__}: {exc}")[:300]
        return
    row.brief_found = len(result.matched_all)
    partly = {p.hidden_id for p in result.pairs if p.level == "partial" and p.judge}
    row.brief_partial = len(partly - set(result.matched_all))
    row.brief_share = round(row.brief_found / row.brief_facts, 3) if row.brief_facts else 0.0
    row.brief_missed = ", ".join(h.id for h in facts if h.id not in result.matched_all)
    row.judge_calls = len(calls)
    row.judge_cost_usd = round(sum(c.cost_usd for c in calls), 6)
    if calls:
        row.judge_model = f"{calls[-1].provider}/{calls[-1].model}"


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


def by_brief(rows: Sequence[Row]) -> list[dict[str, Any]]:
    """Per brief (T-311): the facts of the brief kept — median and worst — and the FR spread."""
    found = []
    for scenario in dict.fromkeys(r.scenario for r in rows):
        mine = [r for r in rows if r.scenario == scenario and not r.error]
        if not mine:
            found.append({"scenario": scenario, "runs": 0})
            continue
        shares = [r.brief_share for r in mine]
        frs = [r.fr for r in mine]
        violating = sum(r.violating for r in mine)
        total = sum(r.requirements for r in mine)
        spread = max(frs) / min(frs) if min(frs) else float("inf")
        found.append(
            {
                "scenario": scenario,
                "runs": len(mine),
                "brief_median": statistics.median(shares),
                "brief_worst": min(shares),
                "fr": frs,
                "fr_spread": spread,
                "violation_share": violating / total if total else 0.0,
                "passes": min(shares) >= BRIEF_SHARE and spread <= FR_SPREAD,
            }
        )
    return found


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
    lines += [
        "",
        "## Факты брифа и разброс ФТ (T-311)",
        "",
        f"Правило T-311 на бриф: худший повтор — не меньше {BRIEF_SHARE:.0%} фактов брифа, "
        f"ФТ max/min — не больше {FR_SPREAD:g}; доля нарушений ISO-001/003 сравнивается с замером "
        "до правки.",
        "",
        "| Сценарий | Прогонов | Факты брифа: медиана | худший | ФТ по повторам | max/min ФТ "
        "| Доля нарушений | Правило |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for b in by_brief(rows):
        if not b["runs"]:
            lines.append(f"| {b['scenario']} | 0 | — | — | — | — | — | нет |")
            continue
        lines.append(
            f"| {b['scenario']} | {b['runs']} | {b['brief_median']:.0%} | {b['brief_worst']:.0%} "
            f"| {', '.join(map(str, b['fr']))} | {b['fr_spread']:.1f} "
            f"| {b['violation_share']:.0%} | {_yes(b['passes'])} |"
        )
    lines += [
        "",
        "| Сценарий | Повтор | БТ | ПТ | ФТ | НФТ | Огр. | Фактов брифа | Найдено | Частично "
        "| Не найдены | Отсеяно кодом |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.scenario} | {r.repeat} | {r.br} | {r.ur} | {r.fr} | {r.nfr} | {r.con} "
            f"| {r.brief_facts} | {r.brief_found} | {r.brief_partial} | {r.brief_missed} "
            f"| {r.dropped_reasons} |"
        )
    return "\n".join(lines) + "\n"
