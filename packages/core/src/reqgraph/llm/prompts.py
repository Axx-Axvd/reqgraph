"""Prompt templates: Jinja2 Markdown files next to the code that uses them (CLAUDE.md).

Texts are in Russian and ship as package data; code only fills in the values. The hash of the
template source goes into every llm_call event (experiment records, CLAUDE.md). Agents keep theirs
in agents/prompts/, the stakeholder simulator in sim/prompts/.
"""

import hashlib
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from jinja2 import Environment, StrictUndefined

_ENV = Environment(
    undefined=StrictUndefined,  # a missing value is an error, not an empty string
    autoescape=False,  # Markdown for a model, not HTML
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass(frozen=True)
class Prompt:
    name: str  # "analyst/extract"
    source: str

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.source.encode()).hexdigest()[:12]

    def render(self, **values: Any) -> str:
        return _ENV.from_string(self.source).render(**values)


def read_prompt(package: str, name: str) -> Prompt:
    """<package>/prompts/<name>.md as a Prompt."""
    path = files(package).joinpath("prompts", *f"{name}.md".split("/"))
    if not path.is_file():
        folder = package.removeprefix("reqgraph.").replace(".", "/")
        raise FileNotFoundError(f"нет промпта {name}: {folder}/prompts/{name}.md")
    return Prompt(name, path.read_text(encoding="utf-8"))
