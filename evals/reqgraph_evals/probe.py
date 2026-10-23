"""Probe (T-006): the same 20 tasks for several models, deterministic scores, CSV and Markdown."""

import csv
import hashlib
import json
import statistics
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date
from importlib.metadata import version
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import BaseModel
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, LLMJudge
from reqgraph.llm import CallStats, load_roles, model_for, structured
from reqgraph.llm.config import Step

from reqgraph_evals import scoring
from reqgraph_evals.schemas import OUTPUT_TYPES, ROLES, Extraction, ProcessSketch, Question, Rewrite

PROBE_DIR = Path(__file__).resolve().parent.parent / "probe"
BLOCKS = ("extract", "process", "rewrite", "question")
CSV_FIELDS = [
    "date",
    "model_id",
    "provider",
    "block",
    "case",
    "repeat",
    "valid",
    "score",
    "scores",
    "judge",
    "input_tokens",
    "output_tokens",
    "requests",
    "cost_usd",
    "list_cost_usd",
    "latency_ms",
    "temperature",
    "seed",
    "prompt_sha",
    "package_version",
    "error",
    "answer",
]


@dataclass(frozen=True)
class ProbeInput:
    block: str
    prompt: str
    prompt_sha: str
    case: dict[str, Any]


@dataclass(frozen=True)
class ProbeOutput:
    answer: BaseModel
    stats: CallStats


@dataclass
class Row:
    date: str
    model_id: str
    provider: str
    block: str
    case: str
    repeat: int
    valid: int
    score: float
    scores: str
    judge: str
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0
    cost_usd: float = 0.0
    list_cost_usd: float | None = None
    latency_ms: int = 0
    temperature: float = 0.0
    seed: int | None = None
    prompt_sha: str = ""
    package_version: str = ""
    error: str = ""
    answer: str = ""


def load_cases(path: Path | None = None) -> list[tuple[str, dict[str, Any]]]:
    data = yaml.safe_load((path or PROBE_DIR / "cases.yaml").read_text(encoding="utf-8"))
    return [(block, case) for block in BLOCKS for case in data.get(block, [])]


def render(block: str, case: dict[str, Any], prompts: Path | None = None) -> tuple[str, str]:
    """Prompt text and the sha256 of its template (12 hex chars) for reproducibility."""
    folder = prompts or PROBE_DIR / "prompts"
    env = Environment(loader=FileSystemLoader(folder), undefined=StrictUndefined, autoescape=False)
    source = (folder / f"{block}.md").read_text(encoding="utf-8")
    sha = hashlib.sha256(source.encode()).hexdigest()[:12]
    return env.get_template(f"{block}.md").render(**case), sha


class BlockScore(Evaluator[ProbeInput, ProbeOutput, None]):
    """Deterministic score of one answer (scoring.py), reported as named scores."""

    def evaluate(self, ctx: EvaluatorContext[ProbeInput, ProbeOutput, None]) -> dict[str, float]:
        case, answer = ctx.inputs.case, ctx.output.answer
        match ctx.inputs.block:
            case "extract":
                assert isinstance(answer, Extraction)
                return scoring.score_extract(answer, case["expected"])
            case "process":
                assert isinstance(answer, ProcessSketch)
                return scoring.score_process(answer, case["expected"])
            case "rewrite":
                assert isinstance(answer, Rewrite)
                return scoring.score_rewrite(answer, case["keep"])
            case _:
                assert isinstance(answer, Question)
                return scoring.score_question(answer, case)


JUDGE_RUBRIC = (
    "Ответ — переписанное требование. Оно сохраняет смысл исходного требования из входа, "
    "однозначно и проверяемо, без размытых слов."
)


def build_dataset(judge: bool = False) -> Dataset[ProbeInput, ProbeOutput, None]:
    cases = []
    for block, case in load_cases():
        prompt, sha = render(block, case)
        evaluators: list[Evaluator[ProbeInput, ProbeOutput, None]] = []
        if judge and block == "rewrite":
            evaluators.append(
                LLMJudge(rubric=JUDGE_RUBRIC, model=model_for("judge"), include_input=True)
            )
        cases.append(
            Case(
                name=case["name"],
                inputs=ProbeInput(block=block, prompt=prompt, prompt_sha=sha, case=case),
                evaluators=evaluators,
            )
        )
    return Dataset(name="probe", cases=cases, evaluators=[BlockScore()])


async def run_model(
    model_id: str,
    repeat: int,
    dataset: Dataset[ProbeInput, ProbeOutput, None],
    concurrency: int = 1,
) -> list[Row]:
    """All tasks for one model, ``repeat`` times; failures become rows with valid = 0."""
    cfg = load_roles()
    step = Step.parse(model_id)
    seed = cfg.defaults.seed if cfg.providers[step.provider].supports_seed else None
    pkg = version("reqgraph")
    today = date.today().isoformat()

    async def task(inp: ProbeInput) -> ProbeOutput:
        answer, stats = await structured(
            ROLES[inp.block], inp.prompt, OUTPUT_TYPES[inp.block], model_id=model_id
        )
        return ProbeOutput(answer=answer, stats=stats)

    by_name = {c.name: c.inputs for c in dataset.cases}
    rows: list[Row] = []
    for attempt in range(1, repeat + 1):
        report = await dataset.evaluate(
            task, name=f"{model_id}#{attempt}", max_concurrency=concurrency, progress=False
        )
        for rc in report.cases:
            inp, out = by_name[rc.name], rc.output
            scores = {
                k: float(v.value) for k, v in rc.scores.items() if isinstance(v.value, int | float)
            }
            judge = {k: v.value for k, v in rc.assertions.items()}
            rows.append(
                Row(
                    date=today,
                    model_id=model_id,
                    provider=step.provider,
                    block=inp.block,
                    case=rc.name,
                    repeat=attempt,
                    valid=1,
                    score=scores.get("score", 0.0),
                    scores=json.dumps(
                        {k: v for k, v in scores.items() if k != "score"}, ensure_ascii=False
                    ),
                    judge=json.dumps(judge, ensure_ascii=False) if judge else "",
                    input_tokens=out.stats.input_tokens,
                    output_tokens=out.stats.output_tokens,
                    requests=out.stats.requests,
                    cost_usd=out.stats.cost_usd,
                    list_cost_usd=out.stats.list_cost_usd,
                    latency_ms=out.stats.latency_ms,
                    temperature=cfg.defaults.temperature,
                    seed=seed,
                    prompt_sha=inp.prompt_sha,
                    package_version=pkg,
                    answer=out.answer.model_dump_json(),
                )
            )
        for fc in report.failures:
            inp = by_name[fc.name]
            rows.append(
                Row(
                    date=today,
                    model_id=model_id,
                    provider=step.provider,
                    block=inp.block,
                    case=fc.name,
                    repeat=attempt,
                    valid=0,
                    score=0.0,
                    scores="{}",
                    judge="",
                    temperature=cfg.defaults.temperature,
                    seed=seed,
                    prompt_sha=inp.prompt_sha,
                    package_version=pkg,
                    error=f"{fc.error_message}"[:300],
                )
            )
    return rows


def write_csv(rows: Sequence[Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for r in rows:
            d = asdict(r)
            writer.writerow({k: d[k] for k in CSV_FIELDS})


def _pct(values: list[int], q: float) -> int:
    if not values:
        return 0
    values = sorted(values)
    return values[min(len(values) - 1, round(q * (len(values) - 1)))]


def summary_markdown(rows: Sequence[Row]) -> str:
    """Per model: valid share, mean score per block (failures count as 0), latency, tokens, $."""
    lines = [
        "| Модель | Ответов | Валидных | extract | process | rewrite | question | Среднее "
        "| p50, мс | p95, мс | Токены (вх/вых) | $ факт | $ по прайсу |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for model_id in dict.fromkeys(r.model_id for r in rows):
        mine = [r for r in rows if r.model_id == model_id]
        ok = [r for r in mine if r.valid]
        per_block = []
        for block in BLOCKS:
            vals = [r.score for r in mine if r.block == block]  # failures count as 0
            per_block.append(f"{statistics.mean(vals):.2f}" if vals else "—")
        overall = statistics.mean(r.score for r in mine) if mine else 0.0
        lat = [r.latency_ms for r in ok]
        price = sum(r.list_cost_usd or 0 for r in ok)
        tokens = f"{sum(r.input_tokens for r in ok)}/{sum(r.output_tokens for r in ok)}"
        lines.append(
            f"| `{model_id}` | {len(mine)} | {len(ok) / len(mine):.0%} | {' | '.join(per_block)} "
            f"| {overall:.2f} | {_pct(lat, 0.5)} | {_pct(lat, 0.95)} | {tokens} "
            f"| {sum(r.cost_usd for r in ok):.4f} | {price:.4f} |"
        )
    return "\n".join(lines) + "\n"
