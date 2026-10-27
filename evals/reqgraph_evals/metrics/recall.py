"""Recall of hidden requirements (09_eval): |found ∩ hidden| / |hidden|.

Matching in three steps: embeddings pick up to TOP_K candidates per hidden requirement among the
requirements of the final graph; an LLM judge of another family than the agents decides which
candidates, if any, state the same requirement — one, or several when the system split it in
parts — and whether fully or only partly (the topic without its numbers or a key condition);
20% of the judged references are labelled by a person (label.py) to check the judge (Cohen's
kappa, agreement.py). Every pair is kept for that check.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from functools import cache
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from reqgraph.graph.edges import Rel
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import InterviewTurn
from reqgraph.llm.embed import cosine
from reqgraph.llm.prompts import Prompt, read_prompt
from reqgraph.sim.scenario import HiddenRequirement

TOP_K = 3
FLOOR = 0.5  # a candidate less similar than this is not shown to the judge
KINDS = ("BR", "UR", "FR", "NFR", "CON")

Embed = Callable[[Sequence[str]], Awaitable[list[list[float]]]]


@cache
def judge_prompt() -> Prompt:
    return read_prompt("reqgraph_evals", "judge/match")


Level = Literal["full", "partial", "none"]


class Verdict(BaseModel):
    """How the candidates express the reference — fully, partly (the topic without its numbers or
    a key condition) or not at all — and which of them: one, or parts split over several."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    level: Level | None = Field(
        default=None, description="full — полностью, partial — частично, none — ни один"
    )
    matches: list[int] = Field(
        default_factory=list,
        description="номера кандидатов, которые сами или вместе выражают эталон; пусто — ни один",
    )
    reason: str = ""

    @model_validator(mode="after")
    def _level(self) -> "Verdict":
        level: Level = "none" if not self.matches else (self.level or "full")
        if self.matches and level == "none":
            level = "full"  # candidates named but the level said none: the names decide
        object.__setattr__(self, "level", level)
        if level == "none":
            object.__setattr__(self, "matches", [])
        return self

    @field_validator("matches", mode="before")
    @classmethod
    def _numbers(cls, value: Any) -> Any:
        if isinstance(value, int):  # a model may answer with one number, 0 — none
            value = [value]
        if isinstance(value, list):
            return sorted({v for v in value if isinstance(v, int) and v > 0})
        return value


Judge = Callable[[str, list[str]], Awaitable[Verdict]]


@dataclass(frozen=True)
class Found:
    id: str
    text: str
    assumption: bool  # the Analyst's guess, not told by the client


@dataclass
class Pair:
    hidden_id: str
    hidden: str
    found_id: str
    found: str
    similarity: float
    judge: bool  # this candidate is (part of) what the judge matched
    level: Level = "none"  # the judge's level for the whole reference


@dataclass
class Recall:
    hidden: int  # hidden requirements not in the brief
    matched: dict[str, str] = field(default_factory=dict)  # hidden id -> found ids (told only)
    matched_all: dict[str, str] = field(default_factory=dict)  # incl. assumptions and the brief
    partial: dict[str, str] = field(default_factory=dict)  # told only, matched partly
    pairs: list[Pair] = field(default_factory=list)
    in_brief: int = 0

    @property
    def recall(self) -> float:
        """The interview's own recall: hidden requirements outside the brief, told by the client."""
        return len(self.matched) / self.hidden if self.hidden else 0.0

    @property
    def recall_partial(self) -> float:
        """The same, with partial matches counted as found."""
        return (len(self.matched) + len(self.partial)) / self.hidden if self.hidden else 0.0

    @property
    def recall_all(self) -> float:
        """Against the whole reference, the brief and the Analyst's assumptions included."""
        total = self.hidden + self.in_brief
        return len(self.matched_all) / total if total else 0.0


def found_requirements(graph: ArtifactGraph) -> list[Found]:
    clients = {
        n.id for n in graph.nodes_of("TURN") if isinstance(n, InterviewTurn) and n.role == "client"
    }
    told = {e.src for e in graph.edges if e.rel is Rel.DERIVED_FROM and e.dst in clients}
    found = []
    for kind in KINDS:
        for node in graph.nodes_of(kind):
            title = getattr(node, "title", "")
            text = f"{title}: {getattr(node, 'statement', '')}".strip(": ")
            found.append(Found(node.id, text, node.assumption or node.id not in told))
    return found


async def recall(
    hidden: Sequence[HiddenRequirement],
    found: Sequence[Found],
    *,
    embed: Embed,
    judge: Judge,
    top_k: int = TOP_K,
    floor: float = FLOOR,
) -> Recall:
    result = Recall(
        hidden=sum(not h.in_brief for h in hidden), in_brief=sum(h.in_brief for h in hidden)
    )
    if not hidden or not found:
        return result
    vectors = await embed([h.statement for h in hidden] + [f.text for f in found])
    hidden_vectors, found_vectors = vectors[: len(hidden)], vectors[len(hidden) :]
    for item, vector in zip(hidden, hidden_vectors, strict=True):
        scored = sorted(
            ((cosine(vector, v), f) for v, f in zip(found_vectors, found, strict=True)),
            key=lambda s: -s[0],
        )
        candidates = [(score, f) for score, f in scored[:top_k] if score >= floor]
        if not candidates:
            continue
        verdict = await judge(item.statement, [f.text for _, f in candidates])
        parts = [f for number, (_, f) in enumerate(candidates, 1) if number in verdict.matches]
        level: Level = verdict.level or "none"
        for number, (score, f) in enumerate(candidates, 1):
            same = number in verdict.matches
            result.pairs.append(
                Pair(item.id, item.statement, f.id, f.text, round(score, 4), same, level)
            )
        if parts:
            ids = ", ".join(sorted(f.id for f in parts))
            told = not item.in_brief and not any(f.assumption for f in parts)  # every part told
            if level == "full":
                result.matched_all[item.id] = ids
                if told:
                    result.matched[item.id] = ids
            elif told:
                result.partial[item.id] = ids
    return result
