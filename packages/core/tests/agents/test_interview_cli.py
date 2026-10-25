"""reqgraph interview (T-301): pause, resume after a restart, the terminal commands."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from reqgraph.agents.interview import Reply, has_open_interview, interview_project
from reqgraph.agents.nodes import DONE
from reqgraph.agents.run import init_project
from reqgraph.agents.runtime import RunContext
from reqgraph.cli import app
from typer.testing import CliRunner

from .conftest import BRIEF, DRAFT, QUESTION, stub_models

pytestmark = pytest.mark.anyio


def project(tmp_path: Path) -> Path:
    return init_project(tmp_path / "ulybka", name="Улыбка", brief=BRIEF)


class Script:
    """Answers in order; records the questions it was asked."""

    def __init__(self, *answers: Reply) -> None:
        self.answers: Iterator[Reply] = iter(answers)
        self.asked: list[tuple[str, int]] = []

    async def __call__(self, question: str, turn: int) -> Reply:
        self.asked.append((question, turn))
        return next(self.answers)


def stubs() -> dict[str, Any]:
    return dict(stub_models(analyst=DRAFT))


async def test_a_paused_interview_goes_on_after_a_restart(tmp_path: Path) -> None:
    root = project(tmp_path)
    first = Script("Записываются по телефону, 20% звонков без ответа.", None)
    outcome = await interview_project(root, first, models=stubs(), offline=True, max_iter=0)
    assert outcome.paused and outcome.turns == 1
    assert first.asked == [(QUESTION, 1), (QUESTION, 2)]
    assert has_open_interview(root)
    assert (root / ".reqgraph" / "checkpoints.sqlite").is_file()
    assert (root / ".reqgraph" / ".gitignore").read_text(encoding="utf-8") == "*\n"
    assert not (root / "reports" / "ci-report.md").exists()  # nothing is reported while paused

    # a new process: new connection to the same checkpoints, the same question comes back
    second = Script("Напоминать за сутки по SMS.", DONE)
    outcome = await interview_project(root, second, models=stubs(), offline=True, max_iter=0)
    assert second.asked == [(QUESTION, 2), (QUESTION, 3)]
    assert not outcome.paused and outcome.turns == 2 and not has_open_interview(root)
    assert outcome.summary is not None and outcome.summary.turns == 2
    assert (root / "reports" / "ci-report.md").is_file()
    saved = json.loads((root / "reports" / "run-summary.json").read_text(encoding="utf-8"))
    assert saved["turns"] == 2 and saved["requirements"] == 15  # the stub adds 5 on every pass
    events = (root / "reports" / "interview-events.jsonl").read_text(encoding="utf-8")
    roles = [json.loads(e)["role"] for e in events.splitlines() if '"llm_call"' in e]
    assert roles.count("interviewer") == 3 and roles.count("analyst") == 3  # brief + 2 answers
    assert saved["llm_calls"] == len(roles)  # both sessions are counted
    transcript = (root / "interview" / "transcript.jsonl").read_text(encoding="utf-8")
    assert "Напоминать за сутки" in transcript


async def test_restart_begins_a_new_interview(tmp_path: Path) -> None:
    root = project(tmp_path)
    await interview_project(root, Script("Ответ.", None), models=stubs(), offline=True)
    again = Script(None)
    outcome = await interview_project(root, again, restart=True, models=stubs(), offline=True)
    assert again.asked == [(QUESTION, 1)] and outcome.paused


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI builds its own context: give it stub models."""
    real = RunContext.for_project

    def for_project(project: Any, **options: Any) -> RunContext:
        return real(project, **(options | {"models": stubs()}))

    monkeypatch.setattr(RunContext, "for_project", staticmethod(for_project))


@pytest.mark.usefixtures("stubbed")
def test_cli_pauses_and_resumes(tmp_path: Path) -> None:
    root = project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["interview", str(root), "--offline"], input="Звонят.\n/пауза\n")
    assert result.exit_code == 0, result.output
    assert "Новое интервью." in result.output and f"Вопрос 1: {QUESTION}" in result.output
    assert "покрытие" in result.output and "Пауза. Продолжить: reqgraph interview" in result.output

    result = runner.invoke(
        app, ["interview", str(root), "--offline", "--max-iter", "1"], input="\n/готово\n"
    )
    assert result.exit_code in (0, 1), result.output
    assert "Продолжаем интервью." in result.output and "Вопрос 2:" in result.output
    assert "Интервью окончено: заказчик закончил" in result.output
    assert "Вопросов задано и отвечено: 1" in result.output, result.output
    assert "Требований: 10" in result.output  # the brief and one answer: 5 each from the stub


@pytest.mark.usefixtures("stubbed")
def test_cli_end_of_input_is_a_pause(tmp_path: Path) -> None:
    root = project(tmp_path)
    result = CliRunner().invoke(app, ["interview", str(root), "--offline"], input="")
    assert result.exit_code == 0 and "Пауза." in result.output


def test_cli_refuses_the_reference_project_and_a_bad_mode() -> None:
    from .conftest import GARAGE61

    runner = CliRunner()
    result = runner.invoke(app, ["interview", str(GARAGE61)])
    assert result.exit_code == 2 and "эталонный проект" in result.output
    result = runner.invoke(app, ["interview", str(GARAGE61), "--interviewer", "x"])
    assert result.exit_code == 2
