"""Node models of the artifact graph: 12 kinds, fields per 04_data («Узлы графа»)."""

import re
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from reqgraph.graph.errors import BadFields

Status = Literal["draft", "reviewed", "approved"]
Priority = Literal["must", "should", "could", "wont"]
Text = Annotated[str, Field(min_length=1)]


class NodeKind(StrEnum):
    BR = "BR"  # business requirement
    UR = "UR"  # user requirement
    FR = "FR"  # functional requirement
    NFR = "NFR"  # non-functional requirement
    CON = "CON"  # constraint
    ACT = "ACT"  # actor
    PRC = "PRC"  # process
    ENT = "ENT"  # data entity
    UC = "UC"  # use case
    C4 = "C4"  # C4 element
    TURN = "TURN"  # interview turn
    SEC = "SEC"  # document section


KIND_PREFIX: dict[NodeKind, str] = {k: k.value for k in NodeKind}

# Allowed id formats. More digits than the minimum are fine once a counter overflows (FR-1000).
ID_FORMAT: dict[NodeKind, re.Pattern[str]] = {
    NodeKind.BR: re.compile(r"BR-\d{3,}"),
    NodeKind.UR: re.compile(r"UR-\d{3,}"),
    NodeKind.FR: re.compile(r"FR-\d{3,}"),
    NodeKind.NFR: re.compile(r"NFR-\d{3,}"),
    NodeKind.CON: re.compile(r"CON-\d{3,}"),
    NodeKind.ACT: re.compile(r"ACT-\d{2,}"),
    NodeKind.PRC: re.compile(r"PRC-\d{2,}"),
    NodeKind.ENT: re.compile(r"ENT-\d{2,}"),
    NodeKind.UC: re.compile(r"UC-\d{2,}"),
    NodeKind.C4: re.compile(r"C4-(SYS|CNT-\d{2,}|EXT-\d{2,})"),
    NodeKind.TURN: re.compile(r"TURN-\d{4,}"),
    NodeKind.SEC: re.compile(r"SEC-[A-Za-z0-9._-]+"),
}

ISO25010 = Literal[
    "functional_suitability",
    "performance_efficiency",
    "compatibility",
    "usability",
    "interaction_capability",
    "reliability",
    "security",
    "maintainability",
    "portability",
    "flexibility",
    "safety",
]


class GoalMetric(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Text
    unit: Text
    baseline: float | None = None
    target: Text
    horizon: str | None = None


class Metric(BaseModel):
    """A measurable non-functional requirement: characteristic, unit, threshold, test method."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Text
    unit: Text
    threshold: Text
    method: Text


class Attribute(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Text
    type: str | None = None
    note: str | None = None


class _Base(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    status: Status = "draft"
    area: str | None = None  # interview coverage area (goals, scenarios, nfr, ...)
    assumption: bool = False  # not confirmed by a turn: an analyst's assumption

    @model_validator(mode="after")
    def _id_matches_kind(self) -> "_Base":
        kind = NodeKind(getattr(self, "kind"))  # noqa: B009 - set by the subclasses
        if not ID_FORMAT[kind].fullmatch(self.id):
            raise ValueError(
                f"id «{self.id}» не соответствует формату {ID_FORMAT[kind].pattern} вида {kind}"
            )
        return self


class BusinessReq(_Base):
    kind: Literal["BR"] = "BR"
    title: Text
    statement: Text
    goal_metric: GoalMetric | None = None
    priority: Priority | None = None


class UserReq(_Base):
    kind: Literal["UR"] = "UR"
    title: Text
    statement: Text
    actor: str | None = None  # ACT id
    scenario: list[Text] = []
    priority: Priority | None = None


class FunctionalReq(_Base):
    kind: Literal["FR"] = "FR"
    title: Text
    statement: Text
    priority: Priority | None = None
    acceptance: list[Text] = []


class NonFunctionalReq(_Base):
    kind: Literal["NFR"] = "NFR"
    title: Text
    statement: Text
    iso25010: ISO25010
    metric: Metric
    priority: Priority | None = None


class Constraint(_Base):
    kind: Literal["CON"] = "CON"
    title: Text
    type: Literal["legal", "budget", "time", "tech"]
    statement: Text


class ActorNode(_Base):
    kind: Literal["ACT"] = "ACT"
    name: Text
    description: str | None = None


class ProcessNode(_Base):
    kind: Literal["PRC"] = "PRC"
    name: Text
    dsl: dict[str, Any] | None = None
    bpmn_path: str | None = None


class EntityNode(_Base):
    kind: Literal["ENT"] = "ENT"
    name: Text
    attributes: list[Attribute] = []


class UseCaseNode(_Base):
    kind: Literal["UC"] = "UC"
    name: Text
    actor: str | None = None  # ACT id
    goal: str | None = None
    puml: str | None = None


class C4Node(_Base):
    kind: Literal["C4"] = "C4"
    name: Text
    c4_kind: Literal["system", "container", "external"]
    technology: str | None = None
    dsl: str | None = None


class InterviewTurn(_Base):
    kind: Literal["TURN"] = "TURN"
    role: Literal["agent", "client"]
    text: Text
    area_tags: list[Text] = []


class SectionNode(_Base):
    kind: Literal["SEC"] = "SEC"
    template: Text
    text: str
    refs: list[str] = []


Node = Annotated[
    BusinessReq
    | UserReq
    | FunctionalReq
    | NonFunctionalReq
    | Constraint
    | ActorNode
    | ProcessNode
    | EntityNode
    | UseCaseNode
    | C4Node
    | InterviewTurn
    | SectionNode,
    Field(discriminator="kind"),
]
NODE_ADAPTER: TypeAdapter[Node] = TypeAdapter(Node)

# Fields that hold the id of another node; they are checked when a patch is applied.
REF_FIELDS: dict[NodeKind, dict[str, NodeKind]] = {
    NodeKind.UR: {"actor": NodeKind.ACT},
    NodeKind.UC: {"actor": NodeKind.ACT},
}


def parse_node(data: dict[str, Any]) -> Node:
    return NODE_ADAPTER.validate_python(data)


def validation_text(exc: ValidationError, kind: str) -> str:
    """Pydantic errors as `field: message; ...` without the discriminator in the location."""
    parts = []
    for err in exc.errors():
        loc = [str(x) for x in err["loc"] if x != kind]
        message = err["msg"].removeprefix("Value error, ")  # our own validators speak Russian
        parts.append(f"{'.'.join(loc) or 'узел'}: {message}")
    return "; ".join(parts)


def node_from_dict(data: dict[str, Any], label: str) -> Node:
    """parse_node() raising BadFields that names `label` (node id, file), not ValidationError."""
    try:
        return NODE_ADAPTER.validate_python(data)
    except ValidationError as exc:
        raise BadFields(f"{label}: {validation_text(exc, str(data.get('kind')))}") from None
