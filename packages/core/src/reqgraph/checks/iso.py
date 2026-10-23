"""ISO-001…005: quality of requirement wording (own checklist after ISO/IEC/IEEE 29148, no text
of the standard): no vague words, one requirement — one statement, verifiable, no TBD, EARS form."""

import re

from reqgraph.checks.base import BaseCheck, CheckContext, Finding
from reqgraph.checks.registry import register
from reqgraph.checks.text import REQUIREMENT_KINDS, requirement_texts, vague_terms, words
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import FunctionalReq, Node, NonFunctionalReq

_MODAL = {"должный", "должен", "shall"}
_PLACEHOLDER = re.compile(
    r"\b(TBD|TBA|TODO|FIXME|XXX)\b|\?{2,}|уточнить позже|будет уточнено|определить позже",
    re.IGNORECASE,
)
_EARS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^система должна\b",  # ubiquitous
        r"^когда\b.+,\s*система должна\b",  # event-driven
        r"^(пока|в то время как|во время)\b.+,\s*система должна\b",  # state-driven
        r"^если\b.+,\s*(то\s+)?система должна\b",  # unwanted behaviour
        r"^(где|при наличии|в случае)\b.+,\s*система должна\b",  # optional feature
        # time trigger: «За 24 ч до …», «В первый рабочий день месяца …», «Каждый час …»
        r"^(за|через|после|в течение|в|во|каждый|каждую|каждое|ежедневно|ежемесячно)\b"
        r".+?,?\s*система должна\b",
        r"^(when|while|if|where)\b.+,\s*(then\s+)?the system shall\b",
        r"^the system shall\b",
    )
]


def _requirements(graph: ArtifactGraph) -> list[Node]:
    return [n for kind in REQUIREMENT_KINDS for n in graph.nodes_of(kind)]


@register
class NoVagueWords(BaseCheck):
    id = "ISO-001"
    title = "нет размытых слов"
    group = "iso"
    owner = "analyst"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        found = []
        for node in _requirements(graph):
            terms: dict[str, str] = {}
            for field, text in requirement_texts(node):
                for term in vague_terms(text):
                    terms.setdefault(term, field)
            if terms:
                listed = ", ".join(f"«{t}» ({f})" for t, f in terms.items())
                found.append(
                    self.finding(
                        "error",
                        [node.id],
                        f"{node.id}: размытые формулировки: {listed}",
                        hint="замените на измеримое: число, единицу, порог, конкретный список",
                    )
                )
        return found


@register
class OneStatement(BaseCheck):
    id = "ISO-002"
    title = "одно требование — одно утверждение"
    group = "iso"
    owner = "analyst"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        """Two modal verbs, or two infinitives joined by «и» / a comma: two actions in one.
        A list of objects («с длительностью и ценой») is fine (REVIEW.md of garage61, No. 5)."""
        found = []
        for node in graph.nodes_of("FR"):
            assert isinstance(node, FunctionalReq)
            tokens = words(node.statement)
            modals = sum(w.lemma in _MODAL for w in tokens)
            actions = _joined_infinitives(node.statement)
            if modals > 1 or actions:
                what = f"действия «{actions[0]}» и «{actions[1]}»" if actions else "две «должна»"
                found.append(
                    self.finding(
                        "warning",
                        [node.id],
                        f"{node.id}: в одном требовании {what}",
                        hint="разделите на два требования, у каждого — свои критерии приёмки",
                    )
                )
        return found


def _joined_infinitives(text: str) -> tuple[str, str] | None:
    """Two infinitives joined by «и», «или» or a comma: «создать запись и отправить SMS»."""
    tokens = words(text)
    for index, word in enumerate(tokens):
        if word.pos != "INFN":
            continue
        for other in tokens[index + 1 :]:
            if other.pos == "INFN":
                between = text[text.find(word.text) + len(word.text) : text.find(other.text)]
                joiners = {w.lemma for w in words(between)}
                if joiners & {"и", "или"} or "," in between:
                    return word.text, other.text
                break
    return None


@register
class Verifiable(BaseCheck):
    id = "ISO-003"
    title = "проверяемость: критерии приёмки у ФТ, измеримый порог у НФТ"
    group = "iso"
    owner = "analyst"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        found = []
        for node in graph.nodes_of("FR"):
            assert isinstance(node, FunctionalReq)
            if not node.acceptance:
                found.append(
                    self.finding(
                        "error",
                        [node.id],
                        f"{node.id}: нет критериев приёмки",
                        hint="добавьте acceptance: как проверить, что требование выполнено",
                    )
                )
        for node in graph.nodes_of("NFR"):
            assert isinstance(node, NonFunctionalReq)
            if not re.search(r"\d", node.metric.threshold):
                found.append(
                    self.finding(
                        "error",
                        [node.id],
                        f"{node.id}: порог метрики «{node.metric.threshold}» без числа",
                        hint="задайте порог числом с единицей, например «<= 2 с»",
                    )
                )
        return found


@register
class NoPlaceholders(BaseCheck):
    id = "ISO-004"
    title = "нет TBD / TODO / ???"
    group = "iso"
    owner = "analyst"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        found = []
        for node in _requirements(graph):
            for field, text in requirement_texts(node):
                match = _PLACEHOLDER.search(text)
                if match:
                    found.append(
                        self.finding(
                            "error",
                            [node.id],
                            f"{node.id}: заглушка «{match.group()}» в {field}",
                            hint="уточните у заказчика или пометьте требование как допущение",
                        )
                    )
                    break
        return found


@register
class EarsForm(BaseCheck):
    id = "ISO-005"
    title = "форма EARS"
    group = "iso"
    owner = "analyst"

    def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
        found = []
        for node in graph.nodes_of("FR"):
            assert isinstance(node, FunctionalReq)
            text = " ".join(node.statement.split())
            if not any(p.search(text) for p in _EARS):
                found.append(
                    self.finding(
                        "info",
                        [node.id],
                        f"{node.id}: формулировка не по шаблону EARS",
                        hint="«Система должна …», «Когда …, система должна …», "
                        "«Если …, система должна …»",
                    )
                )
        return found
