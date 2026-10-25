"""Metrics of T-304 on stubs: recall with embeddings and a judge, quality, agreement, labels."""

import csv
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.embeddings import TestEmbeddingModel
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from reqgraph.llm.embed import cosine, embed
from reqgraph.sim.scenario import HiddenRequirement
from reqgraph_evals.metrics import harness, label
from reqgraph_evals.metrics.agreement import agreement, cohen_kappa
from reqgraph_evals.metrics.quality import measure, quality
from reqgraph_evals.metrics.recall import Found, Verdict, recall

from .test_interview_eval import agents, simulator

pytestmark = pytest.mark.anyio
GARAGE61 = Path(__file__).resolve().parents[2] / "examples" / "garage61"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_kappa_corrects_for_chance() -> None:
    a, b = [True, True, False, False], [True, False, False, False]
    assert agreement(a, b) == 0.75 and cohen_kappa(a, b) == pytest.approx(0.5)
    assert cohen_kappa(a, a) == 1.0 and cohen_kappa([True] * 3, [True] * 3) == 1.0
    with pytest.raises(ValueError):
        agreement([True], [])


WORDS = ("отмен", "sms", "врач", "логотип")


async def by_words(texts: Sequence[str]) -> list[list[float]]:
    """A stub embedding: one dimension per keyword, so the right texts are close."""
    return [[1.0 if w in t.lower() else 0.0 for w in WORDS] + [0.01] for t in texts]


def hidden(n: int, text: str, **extra: Any) -> HiddenRequirement:
    return HiddenRequirement(
        id=f"H-{n:03d}", kind="FR", area="rules", statement=text, reveal="тема", **extra
    )


async def test_recall_counts_judged_matches_told_by_the_client() -> None:
    reference = [
        hidden(1, "Отмена записи не позднее чем за 3 часа."),
        hidden(2, "SMS за сутки до приёма."),
        hidden(3, "Врач видит своё расписание."),
        hidden(4, "Пациент записывается онлайн.", in_brief=True),
    ]
    found = [
        Found("FR-001", "Отмена: пациент отменяет запись за 3 часа", False),
        Found("FR-002", "Напоминание: SMS за 24 часа", True),  # the Analyst's assumption
        Found("FR-003", "Логотип на сайте", False),
    ]
    asked: list[tuple[str, list[str]]] = []

    async def judge(reference_text: str, candidates: list[str]) -> Verdict:
        asked.append((reference_text, candidates))
        return Verdict(match=1)  # the closest candidate is the same requirement

    result = await recall(reference, found, embed=by_words, judge=judge)
    assert result.hidden == 3 and result.in_brief == 1
    assert result.matched == {"H-001": "FR-001"}  # H-002 matched only an assumption
    assert result.matched_all == {"H-001": "FR-001", "H-002": "FR-002"}
    assert result.recall == pytest.approx(1 / 3) and result.recall_all == pytest.approx(2 / 4)
    assert "Врач видит своё расписание." not in [a[0] for a in asked]  # nothing close: no call
    assert {p.found_id for p in result.pairs if p.judge} == {"FR-001", "FR-002"}


async def test_embeddings_are_cached_per_model_and_text(tmp_path: Path) -> None:
    model = TestEmbeddingModel()
    first = await embed(["а", "б", "а"], model=model, model_id="test/m", cache=tmp_path)
    assert len(first) == 3 and first[0] == first[2]
    assert len(list((tmp_path / "test_m").glob("*.json"))) == 2

    class Failing(TestEmbeddingModel):
        async def embed(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("the cache must answer")

    again = await embed(["б", "а"], model=Failing(), model_id="test/m", cache=tmp_path)
    assert again == [first[1], first[0]] and cosine(first[0], first[0]) == pytest.approx(1.0)


async def test_quality_of_the_reference_project() -> None:
    q = await quality(GARAGE61)
    assert q.requirements > 20 and q.processes >= 2
    assert q.validity == 1.0 and q.soundness == 1.0 and q.trace_coverage == 1.0
    assert 0 <= q.ambiguity <= 0.15 and q.orphan_rate == 0.0 and q.errors == 0


def test_quality_counts_broken_models() -> None:
    from reqgraph.checks.base import Finding
    from reqgraph.checks.report import CIReport, Summary
    from reqgraph.dsl.readers import model_readers
    from reqgraph.graph.store import FileStore

    graph = FileStore(GARAGE61, readers=model_readers()).load().graph
    prc = graph.nodes_of("PRC")[0].id
    findings = [
        Finding(check_id="SCH-002", severity="error", node_ids=[prc], message="м", owner="modeler"),
        Finding(
            check_id="SND-001",
            severity="error",
            node_ids=[f"{prc}.T01"],
            message="м",
            owner="modeler",
        ),
    ]
    summary = Summary(errors=2, warnings=0, infos=0, passed=0, warned=0, failed=2, skipped=0)
    report = CIReport(project="g", checks=[], findings=findings, summary=summary)
    q = measure(graph, report, has_erd=True)
    assert q.validity < 1.0 and q.soundness < 1.0


def write_pairs(path: Path, count: int) -> None:
    rows = [
        {
            "run": "r",
            "hidden_id": f"H-{i:03d}",
            "hidden": "э",
            "found_id": "FR-001",
            "found": "с",
            "similarity": 0.9,
            "judge": str(i % 2 == 0),
        }
        for i in range(count)
    ]
    harness.write_pairs(rows, path)


def test_labels_of_a_seeded_sample_can_be_continued(tmp_path: Path) -> None:
    pairs = tmp_path / "pairs-x.csv"
    write_pairs(pairs, 20)
    picked = label.sample(label.read_pairs(pairs))
    assert len(picked) == 4 and picked == label.sample(label.read_pairs(pairs))  # 20%, repeatable
    answers = iter(["y", "maybe", "n", "q"])
    assert label.label(pairs, lambda _: next(answers), echo=lambda _: None) == 2
    answers = iter(["y", "n"])
    assert label.label(pairs, lambda _: next(answers), echo=lambda _: None) == 4
    result = label.compare(pairs)
    assert result["pairs"] == 4 and 0 <= result["agreement"] <= 1
    with pytest.raises(ValueError, match="нет разметки"):
        label.compare(tmp_path / "pairs-none.csv")


def judge_first() -> FunctionModel:
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(json.dumps({"match": 1, "reason": "то же"}))])

    return FunctionModel(fn)


async def test_the_harness_scores_a_saved_run(tmp_path: Path) -> None:
    from reqgraph_evals.interview import run_interview

    models = agents()
    models["analyst"] = TestModel(
        custom_output_args={
            "requirements": [
                {
                    "ref": "fr",
                    "kind": "FR",
                    "title": "Отмена",
                    "statement": "Система должна позволять отменить запись за 3 часа.",
                    "acceptance": ["отмена позже 3 часов недоступна"],
                    "area": "exceptions",
                    "sources": ["TURN-0006"],
                }
            ]
        }
    )
    runs = tmp_path / "runs"
    row = await run_interview(
        "dev-01",
        "cooperative",
        1,
        max_turns=1,
        max_iter=0,
        models=models,
        sim_model=simulator(["H-013"]),
        keep=runs,
    )
    rows = {"dev-01-cooperative-r1": row}
    cases = [harness.RunInputs("dev-01", "cooperative")]
    results, pairs = await harness.evaluate(
        cases,
        harness.saved_task(rows, runs),
        judge_model=judge_first(),
        embedder=TestEmbeddingModel(),
    )
    (result,) = results
    assert result.error == "" and result.run == "dev-01-cooperative-M2-r1"
    assert result.hidden == 20 and result.requirements >= 1 and 0 <= result.recall <= 1
    assert result.judge_model.startswith("function/") and result.embedding_model
    assert result.llm_calls > row.llm_calls  # the judge's calls are counted too
    assert pairs and {"run", "hidden_id", "found_id", "judge"} <= set(pairs[0])
    path = tmp_path / "results.csv"
    harness.write_results(results, path)
    with path.open(encoding="utf-8") as fh:
        assert next(iter(csv.DictReader(fh))).keys() == set(harness.RESULT_FIELDS)
    assert "| dev-01-cooperative-M2-r1 | 1 |" in harness.summary_markdown(results)
    back = harness.read_interview_rows(_csv_of(row, tmp_path))
    assert back["dev-01-cooperative-r1"] == row


def _csv_of(row: Any, tmp_path: Path) -> Path:
    from reqgraph_evals.interview import write_csv

    path = tmp_path / "interview.csv"
    write_csv([row], path)
    return path
