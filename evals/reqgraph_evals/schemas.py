"""Answer formats for probe tasks (T-006). Temporary: not public schemas of reqgraph."""

from typing import Literal

from pydantic import BaseModel, Field


class ExtractedRequirement(BaseModel):
    kind: Literal["FR", "NFR", "CON"]
    text: str = Field(description="одно требование короткой фразой на русском")


class Extraction(BaseModel):
    requirements: list[ExtractedRequirement]


class Node(BaseModel):
    id: str
    kind: Literal["start", "task", "xor", "end"]
    name: str


class Flow(BaseModel):
    source: str
    target: str
    condition: str | None = None


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
