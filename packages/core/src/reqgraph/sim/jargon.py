"""IT jargon a simulated client may not understand (T-316).

Every term of jargon.yaml has the step of the IT scale from which a client understands it without
an explanation: 1 — a confident user, 2 — someone who has ordered IT projects, 3 — a specialist; a
client at step 0 understands none of them. The dictionary was written before any run and checked by
the author, so the experiment does not tune it on its results.
"""

import re
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

import yaml


@dataclass(frozen=True)
class Term:
    term: str
    level: int
    pattern: re.Pattern[str]


@cache
def _dictionary() -> tuple[tuple[Term, ...], tuple[str, ...]]:
    data = yaml.safe_load(files("reqgraph.sim").joinpath("jargon.yaml").read_text(encoding="utf-8"))
    terms = tuple(
        Term(t["term"], int(t["level"]), re.compile(rf"(?<!\w)(?:{t['pattern']})", re.IGNORECASE))
        for t in data["terms"]
    )
    return terms, tuple(data["explained"])


def unknown_terms(question: str, level: int) -> list[str]:
    """Terms of the question a client at this step does not understand, in dictionary order."""
    terms, _ = _dictionary()
    return [t.term for t in terms if t.level > level and t.pattern.search(question)]


def explained(question: str) -> bool:
    """The question explains itself with an example («например», «то есть»…)."""
    _, markers = _dictionary()
    low = question.lower()
    return any(m in low for m in markers)
