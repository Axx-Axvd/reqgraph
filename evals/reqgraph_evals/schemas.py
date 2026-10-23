"""Answer formats for probe tasks (T-006). Temporary: not public schemas of reqgraph."""

from typing import Literal

from pydantic import BaseModel, Field


class ExtractedRequirement(BaseModel):
    kind: Literal["FR", "NFR", "CON"]
    text: str = Field(description="одно требование короткой фразой на русском")


class Extraction(BaseModel):
    requirements: list[ExtractedRequirement]


class Node(BaseModel):
    id: str = Field(description="короткий латинский идентификатор узла: start, t1, g1, end1")
    kind: Literal["start", "task", "xor", "end"]
    name: str = Field(description="название по-русски; задача начинается с глагола")


class Flow(BaseModel):
    source: str = Field(description="id узла, из которого идёт переход")
    target: str = Field(description="id узла, в который идёт переход")
    condition: str | None = Field(default=None, description="условие перехода из развилки xor")


class ProcessSketch(BaseModel):
    nodes: list[Node]
    flows: list[Flow]


class Rewrite(BaseModel):
    statement: str = Field(description="«Система должна …»")
    acceptance: list[str] = Field(min_length=1, description="критерии приёмки")


class Question(BaseModel):
    question: str
    area: str = Field(description="тема вопроса одним-двумя словами")


OUTPUT_TYPES: dict[str, type[BaseModel]] = {
    "extract": Extraction,
    "process": ProcessSketch,
    "rewrite": Rewrite,
    "question": Question,
}
ROLES = {
    "extract": "analyst",
    "process": "modeler",
    "rewrite": "standards",
    "question": "interviewer",
}
