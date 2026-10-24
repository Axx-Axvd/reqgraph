"""Prompts live in agents/prompts/*.md (Jinja2), not in code (CLAUDE.md, T-202)."""

import pytest
from jinja2 import UndefinedError
from reqgraph.agents.prompts import load_prompt


def test_prompt_renders_and_has_a_stable_hash() -> None:
    prompt = load_prompt("analyst/retry")
    assert prompt.render(error="ошибка X").count("ошибка X") == 1
    assert prompt.hash == load_prompt("analyst/retry").hash and len(prompt.hash) == 12


def test_missing_value_is_an_error_not_an_empty_string() -> None:
    with pytest.raises(UndefinedError):
        load_prompt("analyst/retry").render()


def test_unknown_prompt() -> None:
    with pytest.raises(FileNotFoundError, match="analyst/nope"):
        load_prompt("analyst/nope")
