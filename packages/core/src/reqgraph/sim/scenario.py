"""What the simulated client knows (T-302, T-303): the scenario of an experiment.

The files live in evals/scenarios/<id>/ (loaded and checked by reqgraph_evals.scenario); the models
are here because the simulator (sim/stakeholder.py) reads them and reqgraph never imports evals.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from reqgraph.graph.store.config import Area

_ID = re.compile(r"^H-\d{3}$")


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ScenarioInfo(_Strict):
    id: str = Field(pattern=r"^(dev|test)-\d{2}$")
    title: str = Field(min_length=1)
    domain: str = Field(min_length=1, description="предметная область")
    size: Literal["S", "M", "L"]
    split: Literal["dev", "test"]

    @model_validator(mode="after")
    def _split_matches_id(self) -> "ScenarioInfo":
        if not self.id.startswith(self.split):
            raise ValueError(f"{self.id}: split «{self.split}» не совпадает с id")
        return self


class Persona(_Strict):
    name: str = Field(min_length=1)
    role: str = Field(min_length=1, description="кто он в компании")
    facts: list[str] = Field(min_length=1, description="что он знает о деле, кроме требований")
    style: str = Field(min_length=1, description="манера речи")


class HiddenRequirement(_Strict):
    id: str
    kind: Literal["BR", "UR", "FR", "NFR", "CON"]
    area: Area
    statement: str = Field(min_length=10, description="требование словами заказчика")
    reveal: str = Field(min_length=3, description="тема вопроса, на который оно раскрывается")
    priority: Literal["must", "should", "could"] = "should"
    in_brief: bool = False  # already in the brief: part of the reference, not hidden
    source: str = Field(default="own", pattern=r"^(own|PURE:.+)$")

    @field_validator("id")
    @classmethod
    def _id_format(cls, value: str) -> str:
        if not _ID.fullmatch(value):
            raise ValueError(f"id «{value}»: нужен формат H-001")
        return value


class Hidden(_Strict):
    requirements: list[HiddenRequirement] = Field(min_length=1)


class Scenario(_Strict):
    info: ScenarioInfo
    brief: str
    persona: Persona
    hidden: Hidden

    @property
    def id(self) -> str:
        return self.info.id
