"""The simulated client (T-302, 03_agents): answers the interviewer from hidden requirements.

Two steps per answer, so the client cannot give away what it was not asked about:
1. select — a model sees the hidden list and the question and only picks the items the question
   is about (at most MAX_ITEMS); code checks the ids and keeps what was told;
2. reply — a model writes the answer in the persona's manner and sees only the picked items.

The character is code, not a prompt wish: a vague client tells an item in general words the first
time and its details only when asked again; a contradictory client sometimes names a wrong number
and corrects it later — when, is decided by a seeded random generator, so a run can be repeated.
The model is of another family than the agents (roles.yaml, against self-preference).
"""

import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.models import Model

from reqgraph.llm.prompts import Prompt, read_prompt
from reqgraph.llm.router import CallStats, structured
from reqgraph.sim.scenario import HiddenRequirement, Scenario

Character = Literal["cooperative", "vague", "contradictory"]
Mode = Literal["tell", "general", "detail", "wrong", "correct", "repeat"]

MAX_ITEMS = 3  # requirements one answer may reveal (09_eval: no hints without a question)
WRONG_CHANCE = 0.3  # a contradictory client names a wrong number in about every third answer
FIX_CHANCE = 0.5  # and corrects it in one of the next answers
RECENT = 4  # turns of the dialog the reply sees
RECENT_SELECT = 1  # the choice needs only the question and the last exchange (tokens per day)


@cache
def load_prompt(name: str) -> Prompt:
    return read_prompt("reqgraph.sim", name)


class _Out(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class Selection(_Out):
    topic: str = Field(default="", description="о чём вопрос, 2–5 слов")
    ids: list[str] = Field(default_factory=list, description="id требований, о которых вопрос")
    details: bool = Field(default=False, description="вопрос уточняет уже сказанное")


class Reply(_Out):
    text: str = Field(min_length=1, description="ответ заказчика")


@dataclass(frozen=True)
class Told:
    """One requirement in one answer and how it was said."""

    id: str
    mode: Mode


@dataclass
class SimAnswer:
    text: str
    told: list[Told]
    stats: list[CallStats]

    @property
    def revealed(self) -> list[str]:
        """Requirements told in full in this answer (a general mention does not count)."""
        return [t.id for t in self.told if t.mode in ("tell", "detail", "correct")]


@dataclass
class Stakeholder:
    scenario: Scenario
    character: Character = "cooperative"
    seed: int = 42
    profile: str | None = None
    model: Model | None = None  # a stub in tests; else the stakeholder ladder of roles.yaml
    revealed: set[str] = field(default_factory=set)
    mentioned: set[str] = field(default_factory=set)  # told in general words (vague)
    wrong: list[str] = field(default_factory=list)  # told with a wrong number, not corrected yet
    log: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rng = random.Random(f"{self.seed}:{self.scenario.id}:{self.character}")
        self.items = {r.id: r for r in self.scenario.hidden.requirements}

    async def answer(self, question: str, history: Sequence[tuple[str, str]] = ()) -> SimAnswer:
        """The client's answer to one question; history — earlier (question, answer) pairs."""
        recent = list(history)[-RECENT:]
        selection, select_stats = await self._ask(
            "stakeholder/select",
            Selection,
            question=question,
            recent=recent[-RECENT_SELECT:],
            items=list(self.items.values()),
            revealed=sorted(self.revealed),
            max_items=MAX_ITEMS,
        )
        picked = [i for i in dict.fromkeys(selection.ids) if i in self.items][:MAX_ITEMS]
        told = self._modes(picked, selection.details)
        told += self._correction(told, {self.items[i].area for i in picked})
        reply, reply_stats = await self._ask(
            "stakeholder/reply",
            Reply,
            question=question,
            recent=recent,
            persona=self.scenario.persona,
            brief=self.scenario.brief,
            character=self.character,
            told=[(self.items[t.id], t.mode) for t in told],
        )
        told = _checked(told, reply.text, self.items)
        for t in told:
            if t.mode in ("tell", "detail", "correct"):
                self.revealed.add(t.id)
            elif t.mode == "general":
                self.mentioned.add(t.id)
            elif t.mode == "wrong":
                self.wrong.append(t.id)
        answer = SimAnswer(reply.text, told, [select_stats, reply_stats])
        self.log.append(
            {
                "turn": len(self.log) + 1,
                "picked": picked,
                "told": [{"id": t.id, "mode": t.mode} for t in told],
                "details": selection.details,
                "topic": selection.topic,
            }
        )
        return answer

    def _modes(self, picked: list[str], details: bool) -> list[Told]:
        told = []
        for item_id in picked:
            if item_id in self.revealed:  # asked again: the client says the same, not «no idea»
                told.append(Told(item_id, "repeat"))
                continue
            if item_id in self.wrong:  # asked again about a wrong number: now it is right
                self.wrong.remove(item_id)
                told.append(Told(item_id, "correct"))
                continue
            if self.character == "vague" and item_id not in self.mentioned and not details:
                told.append(Told(item_id, "general"))
            elif self.character == "vague" and item_id in self.mentioned:
                told.append(Told(item_id, "detail"))
            elif (
                self.character == "contradictory"
                and _has_number(self.items[item_id])
                and item_id not in self.wrong
                and self.rng.random() < WRONG_CHANCE
            ):
                told.append(Told(item_id, "wrong"))
            else:
                told.append(Told(item_id, "tell"))
        return told

    def _correction(self, told: list[Told], areas: set[str]) -> list[Told]:
        """A contradictory client corrects an earlier wrong number when the talk comes back to its
        area — not out of the blue, which would tell it without a question."""
        if any(t.mode in ("wrong", "correct") for t in told):
            return []  # one mistake or correction per answer
        due = [i for i in self.wrong if self.items[i].area in areas]
        if not due or self.rng.random() >= FIX_CHANCE:
            return []
        self.wrong.remove(due[0])
        return [Told(due[0], "correct")]

    async def _ask[T](self, name: str, output: type[T], **values: Any) -> tuple[T, CallStats]:
        prompt = load_prompt(name)
        result, stats = await structured(
            "stakeholder", prompt.render(**values), output, profile=self.profile, model=self.model
        )
        return result, stats


_QUANTITY = re.compile(r"(?<![\w-])\d+(?:[.,]\d+)?(?!\s*-?\s*ФЗ)(?![\w-])")


def _has_number(item: HiddenRequirement) -> bool:
    """A quantity to get wrong (a count, a share, a term) — not the number of a law (152-ФЗ)."""
    return _QUANTITY.search(item.statement) is not None


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in _QUANTITY.findall(text)}


def _checked(told: list[Told], text: str, items: Mapping[str, HiddenRequirement]) -> list[Told]:
    """A wrong number counts only if the reply names one: a number none of the told requirements
    has. A model that said the right numbers (or only words) told the requirement as it is."""
    known = set().union(*(_numbers(items[t.id].statement) for t in told)) if told else set()
    named_wrong = bool(_numbers(text) - known)
    return [Told(t.id, "tell") if t.mode == "wrong" and not named_wrong else t for t in told]


def summary(sim: Stakeholder) -> Mapping[str, int]:
    """What the client told by the end: in full, only in general words, wrong and not corrected."""
    hidden = [r for r in sim.scenario.hidden.requirements if not r.in_brief]
    return {
        "hidden": len(hidden),
        "revealed": sum(r.id in sim.revealed for r in hidden),
        "mentioned_only": len(sim.mentioned - sim.revealed),
        "wrong_left": len(sim.wrong),
    }
