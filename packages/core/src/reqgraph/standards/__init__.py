"""Document structures (standards/*.yaml): own section lists, names only — no text of ISO or GOST
(ADR-012). The Standards agent fills them, TPL-001/002 check them, exporters render them."""

from functools import cache
from importlib.resources import files
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

LlmField = Literal[
    "purpose",
    "conventions",
    "audience",
    "scope",
    "references",
    "perspective",
    "environment",
    "user_docs",
    "ui",
    "hardware",
    "communication",
    "other",
    "glossary",
]
LLM_FIELDS: tuple[str, ...] = LlmField.__args__  # type: ignore[attr-defined]
_FILL = (
    r"^(none|acceptance|assumptions|features|interfaces|models|issues|trace"
    rf"|llm:({'|'.join(LLM_FIELDS)})|nodes:[A-Z0-9,]+|nfr:[a-z_,]+)$"
)


class Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^SEC-[A-Za-z0-9._-]+$")
    title: str = Field(min_length=1)
    title_en: str | None = None  # the original name of the section (T-408)
    fill: str = Field(pattern=_FILL)
    required: bool = False

    @property
    def node_kinds(self) -> list[str]:
        return self.fill.removeprefix("nodes:").split(",") if self.fill.startswith("nodes:") else []

    @property
    def characteristics(self) -> list[str]:
        """ISO/IEC 25010 characteristics of an `nfr:` section."""
        return self.fill.removeprefix("nfr:").split(",") if self.fill.startswith("nfr:") else []

    @property
    def number(self) -> str:
        """`SEC-SRS-3.2` -> `3.2`; an appendix (`SEC-SRS-A`) has no number of its own."""
        tail = self.id.rsplit("-", 1)[-1]
        return tail if tail[:1].isdigit() else ""

    @property
    def level(self) -> int:
        """Heading level under the document title: 1 and appendices -> 2, 1.1 -> 3, 1.4.1 -> 4."""
        return self.number.count(".") + 2 if self.number else 2

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
