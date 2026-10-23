"""Text of requirements for the ISO and TRC checks: words, lemmas (pymorphy3), vague wording.

pymorphy3 is created lazily and once (+29 MB, ~1.5 s): docs/research/2026-10-versions.md.
"""

import re
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import TYPE_CHECKING, Any

import yaml

from reqgraph.graph.nodes import Node

if TYPE_CHECKING:
    import pymorphy3

_WORD = re.compile(r"[A-Za-zА-Яа-яЁё]+(?:-[A-Za-zА-Яа-яЁё]+)*")
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
_PUNCTUATION = re.compile(r"[^\w\s-]")
REQUIREMENT_KINDS = ("BR", "UR", "FR", "NFR", "CON")


@dataclass(frozen=True)
class Word:
    text: str
    lemma: str
    pos: str | None  # pymorphy3 part of speech: NOUN, INFN, VERB, ADJF …; None for English


@cache
def morph() -> "pymorphy3.MorphAnalyzer":
    import pymorphy3

    return pymorphy3.MorphAnalyzer()


def words(text: str) -> list[Word]:
    found = []
    for match in _WORD.finditer(text):
        token = match.group()
        if _CYRILLIC.search(token):
            parse = morph().parse(token.lower())[0]
            found.append(Word(token, parse.normal_form.replace("ё", "е"), parse.tag.POS))
        else:
            found.append(Word(token, token.lower(), None))
    return found


def normalize(text: str) -> str:
    return " ".join(text.lower().replace("ё", "е").split())


@cache
def vague_dictionary() -> dict[str, frozenset[str]]:
    data: dict[str, Any] = yaml.safe_load(
        files("reqgraph.checks").joinpath("vague_words.yaml").read_text(encoding="utf-8")
    )
    return {key: frozenset(normalize(v) for v in values) for key, values in data.items()}


def vague_terms(text: str) -> list[str]:
    """Vague words and phrases of the dictionary found in the text, in order of appearance."""
    vocabulary = vague_dictionary()
    plain = normalize(text)
    bare = (
        f" {' '.join(_PUNCTUATION.sub(' ', plain).split())} "  # «необходимости.» -> «необходимости»
    )
    found = []
    for phrase in sorted(vocabulary["phrases"] | vocabulary["en_phrases"]):
        dotted = "." in phrase  # «и т. д.»: punctuation is part of the phrase
        if (dotted and phrase in plain) or (not dotted and f" {phrase} " in bare):
            found.append(phrase)
    for word in words(text):
        english = word.pos is None
        if word.lemma in vocabulary["en_words" if english else "ru_lemmas"]:
            found.append(word.text)
    return list(dict.fromkeys(found))


def requirement_texts(node: Node) -> list[tuple[str, str]]:
    """(field, text) of a requirement that a reader takes as the requirement itself."""
    texts: list[tuple[str, str]] = []
    for name in ("title", "statement"):
        value = getattr(node, name, None)
        if isinstance(value, str):
            texts.append((name, value))
    for name in ("acceptance", "scenario"):
        for index, value in enumerate(getattr(node, name, None) or [], 1):
            texts.append((f"{name}[{index}]", value))
    return texts
