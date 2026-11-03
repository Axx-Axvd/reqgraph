"""reqgraph-evals analyst (T-202) on a stub model: rows, violation share, CSV, summary."""

import csv
from pathlib import Path

import pytest
from pydantic_ai.models.test import TestModel
from reqgraph_evals.analyst import (
    CSV_FIELDS,
    DEV,
    SCENARIOS,
    by_brief,
    run_scenario,
    summary_markdown,
    write_csv,
)

pytestmark = pytest.mark.anyio

DRAFT = {
    "actors": [{"ref": "act_patient", "name": "Пациент", "sources": ["TURN-0001"]}],
    "requirements": [
        {
            "ref": "br",
            "kind": "BR",
            "title": "Меньше неявок",
            "statement": "Доля неявок должна снизиться с 10% до 5% за 6 месяцев.",
            "sources": ["TURN-0001"],
        },
        {
            "ref": "ur",
            "kind": "UR",
            "title": "Онлайн-запись",
            "statement": "Пациент записывается к врачу через сайт.",
            "actor": "act_patient",
            "refines": ["br"],
            "sources": ["TURN-0002"],
        },
        {
            "ref": "fr",
            "kind": "FR",
            "title": "Удобный выбор",
            "statement": "Система должна удобно показывать свободное время врача.",  # ISO-001
            "refines": ["ur"],
            "sources": ["TURN-0002"],  # and no acceptance: ISO-003
        },
    ],
}


MODELS = {"analyst": TestModel(custom_output_args=DRAFT)}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_dev_briefs_exist() -> None:
    for scenario in DEV:
        text = (SCENARIOS / scenario / "brief.md").read_text(encoding="utf-8")
        assert text.startswith("# Бриф") and "условный" in text


async def test_row_counts_requirements_and_violations() -> None:
    row = await run_scenario("dev-01", 1, models=MODELS, brief_recall=False)
    assert (
        row.error == "" and row.applied and row.llm_calls == 2
    )  # T-311: no acceptance, asked again
    assert row.retried and "нет критериев приёмки" in row.dropped_reasons
    assert (row.requirements, row.actors) == (3, 1)
    assert (row.iso001, row.iso003, row.violating) == (1, 1, 1)
    assert row.violation_share == pytest.approx(0.333)
    assert row.provider == "test" and len(row.prompt_hash) == 12 and row.package_version


async def test_failed_run_is_a_row_with_the_error(tmp_path: Path) -> None:
    (tmp_path / "dev-x").mkdir()
    (tmp_path / "dev-x" / "brief.md").write_text("# Бриф\n\nТекст.\n", encoding="utf-8")
    broken = TestModel(custom_output_args={"requirements": "не список"})
    row = await run_scenario(
        "dev-x", 1, models={"analyst": broken}, root=tmp_path, brief_recall=False
    )
    assert row.error and not row.applied


async def test_csv_and_summary(tmp_path: Path) -> None:
    row = await run_scenario("dev-01", 1, models=MODELS, brief_recall=False)
    write_csv([row], tmp_path / "a.csv")
    with (tmp_path / "a.csv").open(encoding="utf-8") as fh:
        (saved,) = list(csv.DictReader(fh))
    assert list(saved) == CSV_FIELDS and saved["scenario"] == "dev-01"
    summary = summary_markdown([row])
    assert "с нарушениями ISO-001/003: 1 (33%)" in summary and "все патчи применены: нет" in summary


async def test_kinds_facts_of_the_brief_and_saved_runs(tmp_path: Path) -> None:
    """T-311: requirements by kind, the facts of the brief through the judge, the saved run."""
    from pydantic_ai.embeddings import TestEmbeddingModel

    judge = TestModel(custom_output_args={"level": "full", "matches": [1]})
    row = await run_scenario(
        "dev-01",
        2,
        models=MODELS,
        judge_model=judge,
        embedder=TestEmbeddingModel(),
        save=tmp_path / "runs",
    )
    assert (row.br, row.ur, row.fr, row.nfr, row.con) == (1, 1, 1, 0, 0)
    assert row.brief_facts > 0 and row.brief_found == row.brief_facts and row.brief_share == 1.0
    assert row.judge_calls == row.brief_facts and row.judge_model.startswith("test/")
    saved = (tmp_path / "runs" / "dev-01-2.json").read_text(encoding="utf-8")
    assert '"FR-001"' in saved
    summary = summary_markdown([row, row])
    assert "## Факты брифа и разброс ФТ (T-311)" in summary
    (brief,) = by_brief([row, row])
    assert brief["brief_worst"] == 1.0 and brief["fr_spread"] == 1.0 and brief["passes"]
