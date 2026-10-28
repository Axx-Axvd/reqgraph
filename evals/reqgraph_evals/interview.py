"""The interview with the simulated client on a scenario (T-302): M2 (or M1) from brief to report.

The interviewer asks, the stakeholder simulator answers from the hidden requirements of the
scenario, the Analyst writes requirements after every answer; then the usual pipeline. One CSV row
per scenario, character and repeat (models, temperatures, seed, prompt hashes, package version,
tokens, cost, time — CLAUDE.md), a readable dialog for the manual check of 09_eval (what was told on
which question) and the project folder of the run, for the metrics of T-304.
"""

import csv
import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, fields
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

from pydantic_ai.models import Model
from reqgraph.agents.interview import EVENTS, interview_project
from reqgraph.agents.run import init_project
from reqgraph.llm.config import load_roles
from reqgraph.sim.stakeholder import Character, Stakeholder, summary

from reqgraph_evals.scenario import SCENARIOS, load_scenario

CHARACTERS: tuple[Character, ...] = ("cooperative", "vague", "contradictory")
MODES = {
    "tell": "рассказал",
    "detail": "уточнил",
    "general": "упомянул в общих словах",
    "wrong": "назвал неверное число",
    "correct": "поправил число",
    "repeat": "повторил уже сказанное",
}


@dataclass
class Row:
    scenario: str
    character: str
    repeat: int
    interviewer: str = "coverage"
    models: str = ""  # role=provider/model of every role that answered, the simulator included
    temperature: float = 0.0  # agents
    sim_temperature: float = 0.0
    seed: int | None = None
    prompt_hashes: str = ""
    package_version: str = ""
    turns: int = 0
    end: str = ""  # coverage | limit | client | interviewer | stop
    hidden: int = 0  # hidden requirements not in the brief
    revealed: int = 0  # of them, told in full by the simulator
    revealed_share: float = 0.0
    mentioned_only: int = 0
    wrong_left: int = 0
    off_topic: int = 0  # told items whose area is not the area the question aimed at
    empty: int = 0  # questions whose answer told no hidden requirement anew (T-305)
    coverage: str = ""  # area got/need at the end
    requirements: int = 0
    errors_final: int = 0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    error: str = ""


CSV_FIELDS = [f.name for f in fields(Row)]


@dataclass
class Turn:
    number: int
    question: str
    area: str | None
    answer: str
    told: list[dict[str, str]] = field(default_factory=list)


async def run_interview(
    scenario_id: str,
    character: Character,
    repeat: int,
    *,
    profile: str = "free",
    interviewer: Literal["coverage", "free"] = "coverage",
    max_turns: int | None = None,
    max_iter: int | None = None,
    models: Mapping[str, Model] | None = None,
    sim_model: Model | None = None,
    root: Path = SCENARIOS,
    dialogs: Path | None = None,
    keep: Path | None = None,
) -> Row:
    scenario = load_scenario(scenario_id, root)
    cfg = load_roles()
    row = Row(scenario_id, character, repeat, interviewer, package_version=version("reqgraph"))
    row.temperature, row.sim_temperature = (
        cfg.temperature("analyst"),
        cfg.temperature("stakeholder"),
    )
    row.seed = (cfg.defaults.seed or 0) + repeat  # the simulator's random choices per repeat
    sim = Stakeholder(scenario, character, seed=row.seed, profile=profile, model=sim_model)
    turns: list[Turn] = []
    history: list[tuple[str, str]] = []
    sim_calls: list[dict[str, Any]] = []

    async def answer(question: str, number: int) -> str:
        reply = await sim.answer(question, history)
        history.append((question, reply.text))
        sim_calls.extend(asdict(s) for s in reply.stats)
        told = [{"id": t.id, "mode": t.mode, "area": sim.items[t.id].area} for t in reply.told]
        turns.append(Turn(number, question, None, reply.text, told))
        return reply.text

    with tempfile.TemporaryDirectory() as tmp:
        project = init_project(
            Path(tmp) / scenario_id,
            name=scenario.info.title,
            brief=scenario.brief,
            project_id=scenario_id,
        )
        try:
            outcome = await interview_project(
                project,
                answer,
                profile=profile,
                interviewer=interviewer,
                max_turns=max_turns,
                max_iter=max_iter,
                offline=True,
                models=models,
            )
        except Exception as exc:  # a failed run is a result too (CLAUDE.md, honesty)
            row.error = f"{type(exc).__name__}: {exc}"[:300]
            outcome = None
        events = _events(project / "reports" / EVENTS)
        _fill(row, events, sim_calls, turns, sim)
        if outcome is not None and outcome.summary is not None:
            row.requirements = outcome.summary.requirements
            row.errors_final = outcome.summary.errors
        if keep is not None:
            target = keep / f"{scenario_id}-{character}-r{repeat}"
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(project, target, ignore=shutil.ignore_patterns(".reqgraph"))
    if dialogs is not None:
        dialogs.mkdir(parents=True, exist_ok=True)
        path = dialogs / f"{scenario_id}-{character}-r{repeat}.md"
        path.write_text(dialog_markdown(row, turns, sim), encoding="utf-8")
    return row


def _events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _fill(
    row: Row,
    events: Sequence[dict[str, Any]],
    sim_calls: Sequence[dict[str, Any]],
    turns: list[Turn],
    sim: Stakeholder,
) -> None:
    calls = [e for e in events if e["type"] == "llm_call"] + list(sim_calls)
    row.llm_calls = len(calls)
    by_role = {c["role"]: f"{c['provider']}/{c['model']}" for c in calls}
    row.models = "; ".join(f"{role}={model}" for role, model in sorted(by_role.items()))
    hashes = {c["prompt"]: c["prompt_hash"] for c in calls if "prompt" in c}
    row.prompt_hashes = "; ".join(f"{k}={v}" for k, v in sorted(hashes.items()))
    row.input_tokens = sum(c["input_tokens"] for c in calls)
    row.output_tokens = sum(c["output_tokens"] for c in calls)
    row.cost_usd = round(sum(c["cost_usd"] for c in calls), 6)
    row.latency_ms = sum(c["latency_ms"] for c in calls)
    areas = [e.get("area") for e in events if e["type"] == "question"]
    for turn, area in zip(turns, areas, strict=False):
        turn.area = area
        new = [t for t in turn.told if t["mode"] != "repeat" and not sim.items[t["id"]].in_brief]
        row.empty += not new
        row.off_topic += sum(  # a repeat is not a hint: it was told before
            1 for t in turn.told if area is not None and t["area"] != area and t["mode"] != "repeat"
        )
    ends = [e["reason"] for e in events if e["type"] == "interview_end"]
    row.end = ends[-1] if ends else ""
    row.turns = len(turns)
    coverage = [e for e in events if e["type"] == "coverage"]
    if coverage:
        got, need = coverage[-1]["got"], coverage[-1]["need"]
        row.coverage = " ".join(f"{a}={got[a]}/{n}" for a, n in need.items())
    told = summary(sim)
    row.hidden, row.revealed = told["hidden"], told["revealed"]
    row.revealed_share = round(row.revealed / row.hidden, 3) if row.hidden else 0.0
    row.mentioned_only, row.wrong_left = told["mentioned_only"], told["wrong_left"]


def dialog_markdown(row: Row, turns: Sequence[Turn], sim: Stakeholder) -> str:
    """The dialog for the manual check: every answer with what it told and on which question."""
    items = sim.items
    lines = [
        f"# Диалог {row.scenario} · {row.character} · повтор {row.repeat}",
        "",
        f"Интервьюер: {row.interviewer}; модели: {row.models}; seed {row.seed}; "
        f"вопросов {row.turns}, конец: {row.end or '—'}.",
        f"Рассказано полностью {row.revealed} из {row.hidden} скрытых требований (вне брифа), "
        f"только упомянуто {row.mentioned_only}, неверных чисел не поправлено {row.wrong_left}; "
        f"не в области вопроса — {row.off_topic}; вопросов без нового требования — {row.empty}.",
        "",
        "Проверка (09_eval): каждое раскрытое требование должно относиться к теме вопроса. "
        "Отметка «⚠» — область требования не совпадает с областью, о которой спрашивал "
        "интервьюер: это не обязательно ошибка, но такие места читаем внимательно.",
        "",
    ]
    for turn in turns:
        lines += [f"## Вопрос {turn.number} ({turn.area or 'область не названа'})", ""]
        lines += [f"**Интервьюер:** {turn.question}", "", f"**Заказчик:** {turn.answer}", ""]
        for t in turn.told:
            item = items[t["id"]]
            off = turn.area is not None and item.area != turn.area and t["mode"] != "repeat"
            flag = " ⚠" if off else ""
            lines.append(
                f"- {t['id']} ({item.area}){flag} — {MODES[t['mode']]}: {item.statement} "
                f"[тема: {item.reveal}]"
            )
        if not turn.told:
            lines.append("- ничего из скрытых требований")
        lines.append("")
    left = [
        r for r in sim.scenario.hidden.requirements if not r.in_brief and r.id not in sim.revealed
    ]
    lines += ["## Не рассказано", ""]
    lines += [f"- {r.id} ({r.area}): {r.statement}" for r in left] or ["- всё рассказано"]
    return "\n".join(lines) + "\n"


def write_csv(rows: Sequence[Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def summary_markdown(rows: Sequence[Row]) -> str:
    lines = [
        "# Интервью с симулятором заказчика",
        "",
        "| Сценарий | Характер | Повтор | Вопросов | Конец | Рассказано | Пустых вопросов "
        "| Упомянуто | Неверных | Вне области | Требований | Ошибок | Вызовов LLM | Токены "
        "| Время, с | Ошибка |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.scenario} | {r.character} | {r.repeat} | {r.turns} | {r.end or '—'} "
            f"| {r.revealed}/{r.hidden} ({r.revealed_share:.0%}) | {r.empty} | {r.mentioned_only} "
            f"| {r.wrong_left} | {r.off_topic} | {r.requirements} | {r.errors_final} "
            f"| {r.llm_calls} | {r.input_tokens + r.output_tokens} | {r.latency_ms / 1000:.1f} "
            f"| {r.error} |"
        )
    return "\n".join(lines) + "\n"
