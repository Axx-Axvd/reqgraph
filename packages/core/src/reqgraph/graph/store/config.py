"""ProjectConfig: the format of reqgraph.yaml (public schema v1, project-config.schema.json)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Area = Literal[
    "goals",
    "stakeholders",
    "scenarios",
    "exceptions",
    "data",
    "rules",
    "integrations",
    "nfr",
    "constraints",
]
CheckId = Annotated[str, Field(pattern=r"^[A-Z]{3}-\d{3}$")]


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ProjectInfo(_Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1)
    description: str | None = None
    reference: bool = False  # the reference project: only checks and export, no agents
    standards: list[Literal["iso29148", "gost34_602"]] = []
    langs: list[Literal["ru", "en"]] = ["ru"]
    dsl_version: Literal[1] = 1


class ModelsConfig(_Strict):
    profile: Literal["free", "cheap", "local"] = "free"  # profiles of llm/roles.yaml


class InterviewConfig(_Strict):
    max_turns: int = Field(default=40, ge=1)
    coverage_need: dict[Area, Annotated[int, Field(ge=0)]] = {}


class ChecksConfig(_Strict):
    max_iterations: int = Field(default=5, ge=1)
    disabled: list[CheckId] = []


class ProjectConfig(_Strict):
    """Settings of one project folder: standards, languages, model profile, coverage thresholds."""

    schema_version: Literal[1] = 1
    project: ProjectInfo
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    interview: InterviewConfig = Field(default_factory=InterviewConfig)
    checks: ChecksConfig = Field(default_factory=ChecksConfig)
