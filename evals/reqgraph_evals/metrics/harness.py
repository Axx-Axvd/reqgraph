"""The experiment harness on pydantic-evals (T-304, ADR-013): runs as cases, metrics as evaluators.

A case is a scenario × character × method (M2 — with the coverage tracker, M1 — without) × repeat.
The task runs the interview with the simulator (or reads a saved run), evaluators score it: recall
with embeddings and the judge, quality from the checks. One row per case goes to results.csv with
the whole record of the run (CLAUDE.md, honesty of the experiment); every judged pair goes to the
pairs file for the manual check of the judge (label.py, agreement.py).
"""

import csv
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, fields
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

from pydantic_ai.embeddings import EmbeddingModel
from pydantic_ai.models import Model
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from reqgraph.agents.nodes import questionnaire
from reqgraph.graph.store import FileStore
from reqgraph.llm.embed import embed, embedding_model
from reqgraph.llm.router import CallStats, structured
from reqgraph.sim.stakeholder import Character

from reqgraph_evals import interview, oneshot
from reqgraph_evals.metrics.quality import quality
from reqgraph_evals.metrics.recall import (
    Pair,
    Verdict,
    by_group,
    found_requirements,
    judge_prompt,
    recall,
)
from reqgraph_evals.scenario import SCENARIOS, load_scenario

Method = Literal["M2", "M1", "B1", "B2", "B3", "A1", "A2", "A3"]
TRC = ("TRC-001", "TRC-002", "TRC-003", "TRC-004", "TRC-005", "TRC-006")


@dataclass(frozen=True)
class MethodOptions:
    """How a method of 09_eval differs from the others (T-405); the scenario, the character, the
    seed of the simulator, the model ladder and the budget are the same for all."""

    interviewer: Literal["coverage", "free", "questionnaire"]
    self_checks: bool = True  # False: agents apply their first answer (B2)
    max_iter: int | None = None  # None: the project's repair rounds; 0 — no repair
    reviewer: Literal["llm", "template"] = "llm"
    disabled: tuple[str, ...] = ()  # checks off in the run's project (A2)
    one_shot: bool = False  # B1: one request on the M1 interview of the same case


METHODS: dict[str, MethodOptions] = {
    "M2": MethodOptions("coverage"),
    "M1": MethodOptions("free"),
    "B1": MethodOptions("free", one_shot=True),
    "B2": MethodOptions("free", self_checks=False, max_iter=0),
    "B3": MethodOptions("questionnaire"),
    "A1": MethodOptions("coverage", max_iter=0),
    "A2": MethodOptions("coverage", disabled=TRC),
    "A3": MethodOptions("coverage", reviewer="template"),
}
INTERVIEWER = {name: m.interviewer for name, m in METHODS.items()}


LIMIT_SPENT = "лимит $ запуска исчерпан"


class LimitSpent(Exception):
    """The dollars of the run are spent: the case is not started (T-406)."""


@dataclass(frozen=True)
class RunInputs:
    scenario: str
    character: Character
    method: Method = "M2"
    repeat: int = 1

    @property
    def name(self) -> str:
        return f"{self.scenario}-{self.character}-{self.method}-r{self.repeat}"


@dataclass
class RunOutput:
    row: interview.Row
    project: Path


@dataclass
class Result:
    run: str
    scenario: str
    character: str
    method: str
    repeat: int
    models: str = ""
    temperature: float = 0.0
    sim_temperature: float = 0.0
    seed: int | None = None
    prompt_hashes: str = ""
    package_version: str = ""
    judge_model: str = ""
    embedding_model: str = ""
    turns: int = 0
    end: str = ""
    recall: float = 0.0  # hidden requirements outside the brief, told by the client
    recall_partial: float = 0.0  # the same, partial matches (the topic without its numbers) too
    recall_all: float = 0.0  # the whole reference, the brief and assumptions included
    hidden: int = 0
    matched: int = 0
    recall_per_10q: float = 0.0
    # T-308: hidden requirements outside the brief by group; empty for an unlabelled reference
    hidden_typical: int | None = None
    hidden_unique: int | None = None
    matched_typical: int | None = None
    matched_unique: int | None = None
    recall_typical: float | None = None
    recall_unique: float | None = None
    requirements: int = 0
    ambiguity: float = 0.0
    validity: float = 0.0
    soundness: float = 0.0
    trace_coverage: float = 0.0
    orphan_rate: float = 0.0
    errors: int = 0
    llm_calls: int = 0  # the run and the judge
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    minutes: float = 0.0
    error: str = ""


RESULT_FIELDS = [f.name for f in fields(Result)]
PAIR_FIELDS = ["run", "hidden_id", "hidden", "found_id", "found", "similarity", "judge", "level"]


@dataclass
class Collected:
    """What the evaluators gather besides scores: judged pairs and the judge's calls."""

    pairs: list[dict[str, Any]] = field(default_factory=list)
    judge_calls: dict[str, list[CallStats]] = field(default_factory=dict)
    embedding_model: str = ""


@dataclass
class RecallEvaluator(Evaluator[RunInputs, RunOutput, None]):
    collected: Collected
    profile: str = "free"
    judge_model: Model | None = None
    embedder: EmbeddingModel | None = None
    root: Path = SCENARIOS

    async def evaluate(self, ctx: EvaluatorContext[RunInputs, RunOutput, None]) -> dict[str, float]:
        scenario = load_scenario(ctx.inputs.scenario, self.root)
        graph = FileStore(ctx.output.project).load().graph
        calls = self.collected.judge_calls.setdefault(ctx.inputs.name, [])
        model, model_id = (
            (self.embedder, self.embedder.model_name)
            if self.embedder is not None
            else embedding_model(self.profile)
        )
        self.collected.embedding_model = model_id

        async def vectors(texts: Sequence[str]) -> list[list[float]]:
            return await embed(texts, model=model, model_id=model_id)

        async def judge(reference: str, candidates: list[str]) -> Verdict:
            prompt = judge_prompt().render(reference=reference, candidates=candidates)
            verdict, stats = await structured(
                "judge", prompt, Verdict, profile=self.profile, model=self.judge_model
            )
            calls.append(stats)
            return verdict

        result = await recall(
            scenario.hidden.requirements, found_requirements(graph), embed=vectors, judge=judge
        )
        self.collected.pairs += [_pair(ctx.inputs.name, p) for p in result.pairs]
        return {
            "recall": round(result.recall, 4),
            "recall_partial": round(result.recall_partial, 4),
            "recall_all": round(result.recall_all, 4),
            "hidden": result.hidden,
            "matched": len(result.matched),
            **by_group(scenario.hidden.requirements, result.matched),
        }


@dataclass
class QualityEvaluator(Evaluator[RunInputs, RunOutput, None]):
    async def evaluate(self, ctx: EvaluatorContext[RunInputs, RunOutput, None]) -> dict[str, float]:
        q = await quality(ctx.output.project)
        return {k: v for k, v in q.to_dict().items() if k in RESULT_FIELDS}


def _pair(run: str, pair: Pair) -> dict[str, Any]:
    return {"run": run, **asdict(pair)}


Task = Callable[[RunInputs], Any]


def run_task(
    *,
    profile: str = "free",
    max_turns: int = 30,
    runs: Path,
    dialogs: Path | None = None,
    models: Mapping[str, Model] | None = None,
    sim_model: Model | None = None,
    root: Path = SCENARIOS,
) -> Task:
    """The task of a case: the interview with the simulator, the project kept for the metrics."""

    async def task(inputs: RunInputs) -> RunOutput:
        options = METHODS[inputs.method]
        case = f"{inputs.scenario}-{inputs.character}-r{inputs.repeat}"
        if options.one_shot:
            row = await oneshot.run_one_shot(
                inputs.scenario,
                inputs.character,
                inputs.repeat,
                source=runs / "M1" / case,
                profile=profile,
                models=models,
                root=root,
                keep=runs / inputs.method,
            )
            return RunOutput(row, runs / inputs.method / case)
        questions = len(questionnaire()) if options.interviewer == "questionnaire" else max_turns
        row = await interview.run_interview(
            inputs.scenario,
            inputs.character,
            inputs.repeat,
            profile=profile,
            interviewer=options.interviewer,
            max_turns=questions,
            max_iter=options.max_iter,
            method=inputs.method,
            self_checks=options.self_checks,
            reviewer=options.reviewer,
            disabled=options.disabled,
            models=models,
            sim_model=sim_model,
            root=root,
            dialogs=None if dialogs is None else dialogs / inputs.method,  # a case per method
            keep=runs / inputs.method,
        )
        return RunOutput(row, runs / inputs.method / case)

    return task


def saved_task(rows: Mapping[str, interview.Row], runs: Path) -> Task:
    """The task of a case from a saved run: the interview CSV row and the kept project folder."""

    async def task(inputs: RunInputs) -> RunOutput:
        key = f"{inputs.scenario}-{inputs.character}-r{inputs.repeat}"
        return RunOutput(rows[key], runs / key)

    return task


async def evaluate(
    cases: Sequence[RunInputs],
    task: Task,
    *,
    profile: str = "free",
    judge_model: Model | None = None,
    embedder: EmbeddingModel | None = None,
    root: Path = SCENARIOS,
    max_usd: float | None = None,
) -> tuple[list[Result], list[dict[str, Any]]]:
    """Run (or read) every case, score it, return the rows of results.csv and the judged pairs.

    max_usd — the dollars of the whole run (T-406): runs, the simulator and the judge. A case that
    would start once they are spent is not run; it is a row with the reason. The case that is
    running when the limit is passed runs to its end."""
    collected = Collected()
    costs: list[float] = []  # of the cases run so far

    def spent() -> float:
        judged = sum(s.cost_usd for calls in collected.judge_calls.values() for s in calls)
        return sum(costs) + judged

    async def limited(inputs: RunInputs) -> RunOutput:
        # cases go one by one (max_concurrency=1): the judge of the last case is counted too
        if max_usd is not None and (usd := spent()) >= max_usd:
            raise LimitSpent(f"{LIMIT_SPENT}: потрачено ${usd:.4f} из ${max_usd:.4f}")
        output: RunOutput = await task(inputs)
        costs.append(output.row.cost_usd)
        return output

    order = list(METHODS)  # M1 before B1: the one-shot reads the M1 interview of its case
    # a method outside the matrix (M2-human, T-306; older saved runs) goes after the matrix
    ordered = sorted(
        cases, key=lambda c: order.index(c.method) if c.method in order else len(order)
    )
    dataset: Dataset[RunInputs, RunOutput, None] = Dataset(
        name="reqgraph",
        cases=[Case(name=c.name, inputs=c) for c in ordered],
        evaluators=[
            RecallEvaluator(collected, profile, judge_model, embedder, root),
            QualityEvaluator(),
        ],
    )
    report = await dataset.evaluate(limited, max_concurrency=1, progress=False)
    results = []
    for case in report.cases:
        scores = {k: v.value for k, v in case.scores.items()}
        results.append(_result(case.inputs, case.output.row, scores, collected, case.name))
    for failure in report.failures:
        results.append(
            Result(
                failure.name,
                failure.inputs.scenario,
                failure.inputs.character,
                failure.inputs.method,
                failure.inputs.repeat,
                error=failure.error_message.removeprefix(f"{LimitSpent.__name__}: ")[:300],
            )
        )
    for case in report.cases:  # an evaluator that failed is a result too
        if case.evaluator_failures:
            row = next(r for r in results if r.run == case.name)
            row.error = "; ".join(f.error_message[:150] for f in case.evaluator_failures)
    return results, collected.pairs


def _result(
    inputs: RunInputs,
    row: interview.Row,
    scores: Mapping[str, Any],
    collected: Collected,
    name: str,
) -> Result:
    judge = collected.judge_calls.get(name, [])
    result = Result(
        name,
        inputs.scenario,
        inputs.character,
        inputs.method,
        inputs.repeat,
        models=row.models,
        temperature=row.temperature,
        sim_temperature=row.sim_temperature,
        seed=row.seed,
        prompt_hashes=row.prompt_hashes,
        package_version=row.package_version or version("reqgraph"),
        judge_model=judge[0].provider + "/" + judge[0].model if judge else "",
        embedding_model=collected.embedding_model,
        turns=row.turns,
        end=row.end,
        llm_calls=row.llm_calls + len(judge),
        input_tokens=row.input_tokens + sum(s.input_tokens for s in judge),
        output_tokens=row.output_tokens + sum(s.output_tokens for s in judge),
        cost_usd=round(row.cost_usd + sum(s.cost_usd for s in judge), 6),
        minutes=round((row.latency_ms + sum(s.latency_ms for s in judge)) / 60000, 2),
        error=row.error,
    )
    for key, value in scores.items():
        if key in RESULT_FIELDS:
            setattr(result, key, value)
    result.requirements = int(result.requirements)
    result.hidden, result.matched, result.errors = (
        int(result.hidden),
        int(result.matched),
        int(result.errors),
    )
    for key in ("hidden_typical", "hidden_unique", "matched_typical", "matched_unique"):
        if (value := getattr(result, key)) is not None:
            setattr(result, key, int(value))
    if row.turns:
        result.recall_per_10q = round(result.matched / row.turns * 10, 3)
    return result


def write_results(results: Sequence[Result], path: Path) -> None:
    _write(path, RESULT_FIELDS, [asdict(r) for r in results])


def write_pairs(pairs: Sequence[dict[str, Any]], path: Path) -> None:
    _write(path, PAIR_FIELDS, pairs)


def _write(path: Path, names: Sequence[str], rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(names), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_interview_rows(path: Path) -> dict[str, interview.Row]:
    """Rows of a reqgraph-evals interview CSV, keyed like the kept project folders."""
    rows: dict[str, interview.Row] = {}
    types = {f.name: f.type for f in fields(interview.Row)}
    with path.open(encoding="utf-8") as fh:
        for raw in csv.DictReader(fh):
            data: dict[str, Any] = {}
            for name, value in raw.items():
                kind = str(types[name])
                if "int" in kind and "None" not in kind:
                    data[name] = int(value or 0)
                elif "float" in kind:
                    data[name] = float(value or 0)
                elif "None" in kind:
                    data[name] = int(value) if value else None
                else:
                    data[name] = value
            row = interview.Row(**data)
            rows[f"{row.scenario}-{row.character}-r{row.repeat}"] = row
    return rows


def _group(share: float | None, matched: int | None, hidden: int | None) -> str:
    return "—" if share is None else f"{share:.0%} ({matched}/{hidden})"


def summary_markdown(results: Sequence[Result]) -> str:
    lines = [
        "# Метрики прогонов (T-304)",
        "",
        "recall — доля скрытых требований вне брифа, которые рассказал заказчик и система нашла "
        "полностью (сопоставление: эмбеддинги → судья); с частичными — вместе с найденными "
        "частично (тема без чисел или главного условия); recall_all — по всему эталону, с брифом "
        "и допущениями, только полные. Типовых и уникальных — recall по группам эталона (T-308, "
        "правило — evals/scenarios/README.md); «—» — эталон не размечен.",
        "",
        "| Прогон | Вопросов | recall | с частичными | recall_all | типовых | уникальных "
        "| на 10 вопросов "
        "| Требований | Неоднозначных | Validity | Soundness | Trace | Сироты | Ошибок "
        "| Вызовов LLM | $ | Минут | Ошибка |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.run} | {r.turns} | {r.recall:.0%} ({r.matched}/{r.hidden}) "
            f"| {r.recall_partial:.0%} | {r.recall_all:.0%} "
            f"| {_group(r.recall_typical, r.matched_typical, r.hidden_typical)} "
            f"| {_group(r.recall_unique, r.matched_unique, r.hidden_unique)} "
            f"| {r.recall_per_10q} | {r.requirements} | {r.ambiguity:.0%} | {r.validity:.0%} "
            f"| {r.soundness:.0%} | {r.trace_coverage:.0%} | {r.orphan_rate:.0%} | {r.errors} "
            f"| {r.llm_calls} | {r.cost_usd:.4f} | {r.minutes} | {r.error} |"
        )
    return "\n".join([*lines, "", *methods_markdown(results)]) + "\n"


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def methods_markdown(results: Sequence[Result]) -> list[str]:
    """Means of every method over its runs without an error, money and time over all of them,
    and bar charts (Mermaid, GitHub draws them), methods in the order of METHODS (T-406)."""
    order = [m for m in METHODS if any(r.method == m for r in results)]
    lines = [
        "## Сводка по методам",
        "",
        "Средние — по прогонам без ошибки; $ и минуты — по всем прогонам метода.",
        "",
        "| Метод | Прогонов | без ошибки | recall | с частичными | Требований | Ошибок проверок "
        "| $ | Минут |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    recalls: dict[str, int] = {}
    money: dict[str, float] = {}
    for method in order:
        runs = [r for r in results if r.method == method]
        clean = [r for r in runs if not r.error]
        money[method] = sum(r.cost_usd for r in runs)
        minutes = round(sum(r.minutes for r in runs), 2)
        if clean:
            recalls[method] = round(_mean([r.recall for r in clean]) * 100)
            means = (
                f"{_mean([r.recall for r in clean]):.0%} "
                f"| {_mean([r.recall_partial for r in clean]):.0%} "
                f"| {_mean([r.requirements for r in clean]):.1f} "
                f"| {_mean([r.errors for r in clean]):.1f}"
            )
        else:
            means = "— | — | — | —"
        lines.append(
            f"| {method} | {len(runs)} | {len(clean)} | {means} | {money[method]:.4f} | {minutes} |"
        )
    if recalls:
        lines += _bars("recall по методам, %", "recall, %", recalls, 100)
    spent = {m: usd for m, usd in money.items() if usd > 0}
    if spent:
        top = max(spent.values())
        lines += _bars("$ по методам", "$", {m: round(v, 4) for m, v in spent.items()}, top)
    return lines


def _bars(title: str, axis: str, values: Mapping[str, float], top: float) -> list[str]:
    names = ", ".join(f'"{m}"' for m in values)
    bars = ", ".join(str(v) for v in values.values())
    return [
        "",
        "```mermaid",
        "xychart-beta",
        f'    title "{title}"',
        f"    x-axis [{names}]",
        f'    y-axis "{axis}" 0 --> {top}',
        f"    bar [{bars}]",
        "```",
    ]
