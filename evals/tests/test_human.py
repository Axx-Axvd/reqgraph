"""The pilot «a person instead of the simulator» (T-306) on stub agents: one turn per call, the
session survives between calls, marks are checked, the result is read by the metrics command."""

import json
from pathlib import Path

import pytest
from reqgraph_evals import human
from reqgraph_evals.metrics.harness import read_interview_rows
from reqgraph_evals.scenario import SealedScenario

from .test_interview_eval import QUESTION, agents

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_the_card_has_the_persona_the_rules_and_the_hidden_list_by_area() -> None:
    card = human.card("dev-01")
    assert card["persona"]["name"] and card["brief"] and "1–4 предложения" in card["rules"]
    ids = [r["id"] for area in card["areas"] for r in area["requirements"]]
    assert "H-013" in ids and len(ids) == len(set(ids))
    assert all(not r["in_brief"] for area in card["areas"] for r in area["requirements"])
    assert card["character"] == "cooperative"


def test_test_scenarios_have_no_card() -> None:
    with pytest.raises(SealedScenario):
        human.card("test-01")


async def test_a_session_goes_one_turn_per_call_and_resumes_in_a_new_call(
    tmp_path: Path,
) -> None:
    session = await human.start("dev-01", root=tmp_path, max_turns=3, models=agents())
    assert session.pending is not None
    assert (session.pending.turn, session.pending.question) == (1, QUESTION)
    assert session.pending.area == "exceptions"

    # a new call, as from a new process: the session is read from its folder
    again = human.load(session.folder)
    assert again.pending == session.pending
    step = await human.answer(
        again.folder, "Отменить можно за 3 часа до приёма.", told=["H-013"], models=agents()
    )
    assert step.pending is not None and step.pending.turn == 2 and step.status == "asking"
    turns = [json.loads(line) for line in step.log.read_text(encoding="utf-8").splitlines()]
    assert turns == [
        {
            "number": 1,
            "question": QUESTION,
            "area": "exceptions",
            "answer": "Отменить можно за 3 часа до приёма.",
            "told": ["H-013"],
        }
    ]


async def test_an_unknown_mark_is_refused_before_the_answer_is_sent(tmp_path: Path) -> None:
    session = await human.start("dev-01", root=tmp_path, max_turns=3, models=agents())
    with pytest.raises(human.UnknownMark, match="H-999"):
        await human.answer(session.folder, "Ответ.", told=["H-999"], models=agents())
    assert not session.log.exists()
    assert human.load(session.folder).pending == session.pending  # still the same question


async def test_finish_writes_the_row_the_metrics_read_and_the_dialog(tmp_path: Path) -> None:
    session = await human.start("dev-01", root=tmp_path, max_turns=5, models=agents())
    await human.answer(session.folder, "За 3 часа.", told=["H-013"], models=agents())
    done = await human.finish(session.folder, models=agents(), max_iter=0, reports=tmp_path)
    assert done.status == "done" and done.pending is None
    rows = read_interview_rows(done.csv)
    row = rows[f"dev-01-cooperative-r{done.repeat}"]
    assert row.method == "M2-human" and row.turns == 1 and row.end == "client"
    assert row.revealed == 1 and row.hidden > 1 and row.sim_temperature == 0
    assert (done.project / "reqgraph.yaml").is_file()  # the project for the metrics
    dialog = done.dialog.read_text(encoding="utf-8")
    assert "За 3 часа." in dialog and "H-013" in dialog


async def test_the_interview_ends_by_itself_at_its_question_limit(tmp_path: Path) -> None:
    session = await human.start("dev-01", root=tmp_path, max_turns=1, models=agents())
    done = await human.answer(
        session.folder, "За 3 часа.", models=agents(), max_iter=0, reports=tmp_path
    )
    assert done.status == "done" and done.pending is None and done.csv.is_file()


def test_the_cli_prints_the_card_as_json_and_refuses_test_scenarios() -> None:
    from reqgraph_evals.cli import app
    from typer.testing import CliRunner

    shown = CliRunner().invoke(app, ["human", "card", "dev-01"])
    assert shown.exit_code == 0 and json.loads(shown.output)["scenario"] == "dev-01"
    refused = CliRunner().invoke(app, ["human", "start", "test-01"])
    assert refused.exit_code == 2 and "S6" in refused.output
