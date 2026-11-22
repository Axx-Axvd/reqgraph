"""T-320: a question is checked by code before the client sees it — jargon above the client's
level (the T-316 dictionary) and several questions in one."""

import pytest
from reqgraph.agents.prompts import load_prompt
from reqgraph.agents.question_check import check_question
from reqgraph.agents.state import Coverage


def test_jargon_above_the_level_is_a_problem() -> None:
    question = "Нужна ли интеграция с внешними системами?"
    issues = check_question(question, level=0)
    assert len(issues) == 1 and "интеграция" in issues[0] and "внешние системы" in issues[0]
    assert check_question(question, level=2) == []  # someone who has ordered IT projects


def test_a_term_explained_next_to_it_is_fine() -> None:
    question = "Нужен ли личный кабинет — страница, где клиент видит свои записи?"
    assert check_question(question, level=0) == []


def test_several_questions_in_one_are_a_problem_at_any_level() -> None:
    issues = check_question("Какие сроки? А какой бюджет?", level=3)
    assert issues == ["несколько вопросов в одном: оставь один вопрос"]


def test_a_specialist_may_hear_any_term() -> None:
    assert check_question("Какие требования к отказоустойчивости и интеграции с API?", 3) == []


def test_a_plain_question_passes() -> None:
    question = "Что будет, если запись не работает час в понедельник утром?"
    assert all(check_question(question, level) == [] for level in range(4))


def _render(name: str, level: int) -> str:
    return load_prompt(name).render(
        gaps=[("nfr", 0, 4)],
        coverage=Coverage(),
        facts={"nfr": []},
        asked_before=set(),
        recent=[],
        asked=[],
        assumptions=[],
        turn=1,
        max_turns=20,
        level=level,
        rephrase=None,
        issues=[],
    )


@pytest.mark.parametrize("name", ["interviewer/ask", "interviewer/ask_free"])
def test_the_prompt_tells_how_to_speak_at_the_chosen_level(name: str) -> None:
    plain, expert = _render(name, 0), _render(name, 3)
    assert "не разбирается в технике" in plain and "не разбирается в технике" not in expert
    assert "можно профессиональные термины" in expert
    assert "<question_issues>" not in plain and "<rephrase>" not in plain


def test_rule_two_no_longer_asks_about_a_whole_area_in_analyst_words() -> None:
    """The root of the author's 22.11 feedback: the example question of rule 2."""
    text = _render("interviewer/ask", 1)
    assert "скорости, доступности и удобству" not in text
