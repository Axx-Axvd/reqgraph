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
from reqgraph.graph.store import FileStore
from reqgraph.llm.embed import embed, embedding_model
from reqgraph.llm.router import CallStats, structured
from reqgraph.sim.stakeholder import Character

from reqgraph_evals import interview
from reqgraph_evals.metrics.quality import quality
from reqgraph_evals.metrics.recall import Pair, Verdict, found_requirements, judge_prompt, recall
from reqgraph_evals.scenario import SCENARIOS, load_scenario

Method = Literal["M2", "M1"]
INTERVIEWER: dict[str, Literal["coverage", "free"]] = {"M2": "coverage", "M1": "free"}


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
    recall_all: float = 0.0  # the whole reference, the brief and assumptions included
    hidden: int = 0
    matched: int = 0
    recall_per_10q: float = 0.0
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
PAIR_FIELDS = ["run", "hidden_id", "hidden", "found_id", "found", "similarity", "judge"]


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
            "recall_all": round(result.recall_all, 4),
            "hidden": result.hidden,
            "matched": len(result.matched),
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
        row = await interview.run_interview(
            inputs.scenario,
            inputs.character,
            inputs.repeat,
            profile=profile,
            interviewer=INTERVIEWER[inputs.method],
            max_turns=max_turns,
            models=models,
            sim_model=sim_model,
            root=root,
            dialogs=dialogs,
            keep=runs / inputs.method,
        )
        return RunOutput(
            row, runs / inputs.method / f"{inputs.scenario}-{inputs.character}-r{inputs.repeat}"
        )

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
) -> tuple[list[Result], list[dict[str, Any]]]:
    """Run (or read) every case, score it, return the rows of results.csv and the judged pairs."""
    collected = Collected()
    dataset: Dataset[RunInputs, RunOutput, None] = Dataset(
        name="reqgraph",
        cases=[Case(name=c.name, inputs=c) for c in cases],
        evaluators=[
            RecallEvaluator(collected, profile, judge_model, embedder, root),
            QualityEvaluator(),
        ],
    )
    report = await dataset.evaluate(task, max_concurrency=1, progress=False)
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
                error=failure.error_message[:300],
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


def summary_markdown(results: Sequence[Result]) -> str:
    lines = [
        "# Метрики прогонов (T-304)",
        "",
        "recall — доля скрытых требований вне брифа, которые рассказал заказчик и нашла "
        "система (сопоставление: эмбеддинги → судья); recall_all — по всему эталону, с брифом "
        "и допущениями.",
        "",
        "| Прогон | Вопросов | recall | recall_all | на 10 вопросов | Требований | Неоднозначных "
        "| Validity | Soundness | Trace | Сироты | Ошибок | Вызовов LLM | $ | Минут | Ошибка |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.run} | {r.turns} | {r.recall:.0%} ({r.matched}/{r.hidden}) | {r.recall_all:.0%} "
            f"| {r.recall_per_10q} | {r.requirements} | {r.ambiguity:.0%} | {r.validity:.0%} "
            f"| {r.soundness:.0%} | {r.trace_coverage:.0%} | {r.orphan_rate:.0%} | {r.errors} "
            f"| {r.llm_calls} | {r.cost_usd:.4f} | {r.minutes} | {r.error} |"
        )
    return "\n".join(lines) + "\n"
