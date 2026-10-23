"""Process JSON DSL v1: what the Modeler writes instead of BPMN XML (ADR-005).

Public schema, version 1 (schemas/process-dsl.schema.json). Only the form is checked here:
fields, unique ids, flows and lanes that exist. Logic (reachability, soundness) — checks SND-*.
"""

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from reqgraph.graph.nodes import validation_text

DSL_VERSION: Literal[1] = 1
ElementType = Literal[
    "start",
    "end",
    "task",
    "user_task",
    "service_task",
    "timer",
    "message",
    "xor",
    "and",
    "event_based",
]
TASKS = frozenset({"task", "user_task", "service_task"})
EVENTS = frozenset({"start", "end", "timer", "message"})
GATEWAYS = frozenset({"xor", "and", "event_based"})
ElementId = Annotated[str, Field(pattern=r"^[A-Z][A-Za-z0-9_]*$")]
FlowSpec = tuple[ElementId, ElementId] | tuple[ElementId, ElementId, str]


class DslError(ValueError):
    """The process DSL does not match the format; the message names the process and the element."""


class ProcessElement(BaseModel):
    """A step of the process: task, event or gateway. `id` is local: T01, G01, S, E1."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: ElementId
    type: ElementType
    name: str = ""
    lane: str | None = None
    realizes: list[Annotated[str, Field(pattern=r"^FR-\d{3,}$")]] = []
    event: Literal["timer", "message"] | None = None  # start events only
    timer: str | None = Field(default=None, min_length=1)  # when a timer fires

    @model_validator(mode="after")
    def _event_fields(self) -> "ProcessElement":
        if self.event is not None and self.type != "start":
            raise ValueError(f"{self.id}: поле event задаётся только у start")
        timed = self.type == "timer" or self.event == "timer"
        if timed and self.timer is None:
            raise ValueError(f"{self.id}: у таймера нужно поле timer — когда он срабатывает")
        if self.timer is not None and not timed:
            raise ValueError(f"{self.id}: поле timer бывает только у таймера")
        return self


@dataclass(frozen=True)
class Flow:
    id: str  # F01, F02 ... in the order of `flows`
    src: str
    dst: str
    label: str


class ProcessDSL(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dsl_version: Literal[1] = DSL_VERSION
    id: str = Field(pattern=r"^PRC-\d{2,}$")
    name: str = Field(min_length=1)
    refines: list[Annotated[str, Field(pattern=r"^UR-\d{3,}$")]] = []
    lanes: list[Annotated[str, Field(min_length=1)]] = []
    nodes: list[ProcessElement] = Field(min_length=1)
    flows: list[FlowSpec] = []

    @model_validator(mode="after")
    def _references(self) -> "ProcessDSL":
        seen: set[str] = set()
        for element in self.nodes:
            if element.id in seen:
                raise ValueError(f"шаг {element.id} повторяется")
            seen.add(element.id)
        if len(set(self.lanes)) != len(self.lanes):
            raise ValueError("дорожки (lanes) повторяются")
        for element in self.nodes:
            if element.lane is not None and element.lane not in self.lanes:
                raise ValueError(f"{element.id}: дорожки «{element.lane}» нет в lanes")
        for flow in self.flows:
            for end in flow[:2]:
                if end not in seen:
                    raise ValueError(f"стрелка {flow[0]} -> {flow[1]}: шага {end} нет в nodes")
        return self

    def element(self, element_id: str) -> ProcessElement:
        return next(e for e in self.nodes if e.id == element_id)

    def flow_list(self) -> list[Flow]:
        return [
            Flow(f"F{i:02d}", spec[0], spec[1], spec[2] if len(spec) == 3 else "")
            for i, spec in enumerate(self.flows, 1)
        ]


def parse_process(data: dict[str, Any]) -> ProcessDSL:
    try:
        return ProcessDSL.model_validate(data)
    except ValidationError as exc:
        raise DslError(f"процесс {data.get('id', '?')}: {validation_text(exc, '')}") from None


def ref(process: ProcessDSL, element_id: str) -> str:
    """Reference to an element as the graph writes it: `PRC-01.T05` (realized_by, BPMN ids)."""
    return f"{process.id}.{element_id}"
