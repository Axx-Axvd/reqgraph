"""IT jargon a simulated client may not understand (T-316).

Every term of jargon.yaml has the step of the IT scale from which a client understands it without
an explanation: 1 — a confident user, 2 — someone who has ordered IT projects, 3 — a specialist; a
client at step 0 understands none of them. The dictionary was written before any run and checked by
the author, so the experiment does not tune it on its results.
"""

import re
from collections.abc import Iterable
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


NEAR = 8  # words after a term within which an example still explains it (T-317)
_SENTENCE_END = re.compile(r"[.?!\n]")
_WORD = re.compile(r"\w+")
_TAIL = re.compile(r"\w*")  # the rest of a word the term's stem matched
_ASIDE = re.compile(r"\s*(?:\(|[—–]|-\s)")  # «кабинет (…)», «кабинет — …»


def explained_terms(question: str, terms: Iterable[str]) -> set[str]:
    """The terms the question explains next to them (the author's decision of 2026-11-17): a
    marker («например», «то есть»…) at most NEAR words after the term in the same sentence, or a
    bracket or a dash right after it. An example elsewhere in the question explains nothing."""
    dictionary, markers = _dictionary()
    wanted = set(terms)
    found: set[str] = set()
    for term in (t for t in dictionary if t.term in wanted):
        for match in term.pattern.finditer(question):
            tail = _TAIL.match(question, match.end())
            end = tail.end() if tail else match.end()
            rest = _SENTENCE_END.split(question[end:], maxsplit=1)[0]
            if _ASIDE.match(rest):
                found.add(term.term)
                break
            words = list(_WORD.finditer(rest))
            window = rest[: words[NEAR - 1].end()] if len(words) >= NEAR else rest
            if any(m in window.lower() for m in markers):
                found.add(term.term)
                break
    return found
