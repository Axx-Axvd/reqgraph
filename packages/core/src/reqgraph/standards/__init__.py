"""Document structures (standards/*.yaml): own section lists, names only — no text of ISO or GOST
(ADR-012). The Standards agent fills them, TPL-001/002 check them, exporters render them."""

from functools import cache
from importlib.resources import files
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

LlmField = Literal["purpose", "scope", "glossary"]


class Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^SEC-[A-Za-z0-9._-]+$")
    title: str = Field(min_length=1)
    fill: str = Field(
        pattern=r"^(none|acceptance|assumptions|llm:(purpose|scope|glossary)|nodes:[A-Z0-9,]+)$"
    )
    required: bool = False

    @property
    def node_kinds(self) -> list[str]:
        return self.fill.removeprefix("nodes:").split(",") if self.fill.startswith("nodes:") else []

    @property
    def llm_field(self) -> str | None:
        return self.fill.removeprefix("llm:") if self.fill.startswith("llm:") else None


class DocumentStructure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    document: str
    title: str
    sections: list[Section]

    @property
    def required(self) -> list[Section]:
        return [s for s in self.sections if s.required]


@cache
def load_structure(name: str) -> DocumentStructure:
    """`iso29148_srs` -> standards/iso29148_srs.yaml."""
    text = files("reqgraph.standards").joinpath(f"{name}.yaml").read_text(encoding="utf-8")
    return DocumentStructure.model_validate(yaml.safe_load(text))
