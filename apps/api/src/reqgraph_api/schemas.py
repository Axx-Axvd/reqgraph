"""Requests and answers of the API: the contract the web types are generated from (OpenAPI)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

RunStatus = Literal["queued", "running", "waiting_input", "succeeded", "failed", "cancelled"]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectIn(_In):
    name: str = Field(min_length=1, max_length=200, description="название проекта")
    brief: str | None = Field(default=None, max_length=20_000, description="бриф заказчика")


class ProjectOut(BaseModel):
    id: UUID
    name: str
    head_rev: int
    standards: list[str]
    created_at: datetime


class RunIn(_In):
    kind: Literal["interview", "brief"] = Field(description="интервью или прогон по брифу")
    brief: str | None = Field(
        default=None, max_length=20_000, description="бриф вместо сохранённого"
    )
    max_turns: int | None = Field(default=None, ge=1, le=40, description="лимит вопросов интервью")
    client_level: int | None = Field(
        default=None,
        ge=0,
        le=3,
        description="как заказчик разбирается в ИТ (T-320): 0 — не разбирается, 1 — пользуется "
        "программами в работе, 2 — участвовал в ИТ-проектах, 3 — специалист; по умолчанию 1",
    )


class RunOut(BaseModel):
    id: UUID
    project_id: UUID
    kind: str
    status: RunStatus
    iteration: int
    cost_usd: float
    error: str | None
    byok: bool = Field(description="прогон на своём ключе OpenRouter (T-503)")
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AnswerIn(_In):
    """The client's answer to the last question, done — end the interview («/готово»), or
    simpler — ask the same question in plainer words («Слишком сложно — проще», T-320)."""

    text: str | None = Field(default=None, min_length=1, max_length=4_000)
    done: bool = False
    simpler: bool = False

    @model_validator(mode="after")
    def _one_of(self) -> "AnswerIn":
        if [self.text is not None, self.done, self.simpler].count(True) != 1:
            raise ValueError("нужно одно из: text, done: true, simpler: true")
        return self


class JobOut(BaseModel):
    id: int
    run_id: UUID
    kind: Literal["start", "resume", "cancel"]
    status: Literal["queued", "running", "done", "failed"]
    created_at: datetime


class RunCreated(BaseModel):
    run: RunOut
    job: JobOut


class EventOut(BaseModel):
    id: int
    type: str
    payload: dict[str, Any]
    ts: datetime


class GraphOut(BaseModel):
    project_id: UUID
    rev: int
    graph: dict[str, Any] = Field(description="ArtifactGraph (schemas/artifact-graph.schema.json)")
    ci_summary: dict[str, Any] | None
    author: Literal["agent", "user"]
    created_at: datetime


class ExportOut(BaseModel):
    id: UUID
    rev: int
    format: str = Field(description="md, docx, reqif, svg")
    path: str = Field(description="путь в бакете Storage exports: <проект>/<ревизия>/<файл>")
    name: str = Field(description="файл внутри выгрузки ревизии, например srs.docx, img/PRC-01.svg")
    created_at: datetime


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    memory_mb: float | None = Field(None, description="память процесса API сейчас, МБ (T-506)")
    peak_memory_mb: float | None = Field(None, description="пик памяти процесса API, МБ (T-506)")


class UsageOut(BaseModel):
    """The demo limits of the signed-in user today (T-503); a day is Moscow time."""

    runs_today: int
    runs_limit: int | None = Field(description="None — без лимита (администратор)")
    cost_today_usd: float
    unlimited: bool
