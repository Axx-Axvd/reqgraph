"""Prompts of the agents: Jinja2 templates in agents/prompts/<agent>/<name>.md (CLAUDE.md)."""

from functools import cache

from reqgraph.llm.prompts import Prompt, read_prompt

__all__ = ["Prompt", "load_prompt"]


@cache
def load_prompt(name: str) -> Prompt:
    return read_prompt("reqgraph.agents", name)
