"""roles.yaml: providers, model ladders per role and profile, defaults and run budget."""

import os
from functools import cached_property
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ROLES_YAML = Path(__file__).with_name("roles.yaml")
DEFAULT_PROFILE = "free"


class ConfigError(ValueError):
    """roles.yaml is invalid or a role/profile does not exist."""


class Provider(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_url: str
    base_url_env: str | None = None
    key_env: str | None
    free: bool = False
    max_input_tokens: int | None = None
    supports_seed: bool = True
    # How structured output is requested: tool call (pydantic-ai default), native JSON schema
    # (response_format) or JSON in the text. None keeps the pydantic-ai default.
    output_mode: Literal["tool", "native", "prompted"] | None = None


class Step(BaseModel):
    """One rung of a ladder: a model at a provider."""

    model_config = ConfigDict(frozen=True)

    provider: str
    model: str

    @property
    def id(self) -> str:
        return f"{self.provider}/{self.model}"

    @classmethod
    def parse(cls, raw: str) -> "Step":
        provider, sep, model = raw.partition("/")
        if not sep or not model:
            raise ConfigError(f"модель «{raw}» должна иметь вид провайдер/модель")
        return cls(provider=provider, model=model)


class Defaults(BaseModel):
    temperature: float = 0.2
    timeout_s: float = 60
    retries: int = Field(default=2, ge=0)
    seed: int | None = 42


class RoleSettings(BaseModel):
    """Settings of one role that differ from the defaults (the simulator answers at 0.7)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    temperature: float | None = Field(default=None, ge=0, le=2)


class Budget(BaseModel):
    run_usd: float = Field(gt=0)
    run_tokens: int = Field(gt=0)


class RolesConfig(BaseModel):
    providers: dict[str, Provider]
    profiles: dict[str, dict[str, list[str]]]
    defaults: Defaults = Defaults()
    role_settings: dict[str, RoleSettings] = {}
    budget: Budget = Budget(run_usd=0.5, run_tokens=800_000)

    @model_validator(mode="after")
    def _known_providers(self) -> "RolesConfig":
        for profile, roles in self.profiles.items():
            for role, ids in roles.items():
                for raw in ids:
                    step = Step.parse(raw)
                    if step.provider not in self.providers:
                        raise ConfigError(
                            f"{profile}.{role}: неизвестный провайдер «{step.provider}» в «{raw}»"
                        )
        return self

    @cached_property
    def _ladders(self) -> dict[str, dict[str, tuple[Step, ...]]]:
        return {
            profile: {role: tuple(Step.parse(raw) for raw in ids) for role, ids in roles.items()}
            for profile, roles in self.profiles.items()
        }

    def ladder(self, role: str, profile: str | None = None) -> tuple[Step, ...]:
        """Models to try for a role, in order. The "*" entry covers roles not listed explicitly."""
        name = profile or os.environ.get("REQGRAPH_PROFILE") or DEFAULT_PROFILE
        if name not in self._ladders:
            raise ConfigError(
                f"нет профиля «{name}» в roles.yaml (есть: {', '.join(self._ladders)})"
            )
        roles = self._ladders[name]
        steps = roles.get(role) or roles.get("*")
        if not steps:
            raise ConfigError(f"в профиле «{name}» нет роли «{role}» и нет записи «*»")
        return steps

    def temperature(self, role: str) -> float:
        """The role's own temperature, else the default one."""
        own = self.role_settings.get(role)
        if own is not None and own.temperature is not None:
            return own.temperature
        return self.defaults.temperature

    def is_free(self, step: Step) -> bool:
        """Free tier provider, or an OpenRouter model whose id ends with ":free"."""
        return self.providers[step.provider].free or step.model.endswith(":free")


def load_roles(path: Path | None = None) -> RolesConfig:
    """Read and validate roles.yaml (the bundled one by default)."""
    source = path or ROLES_YAML
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    try:
        cfg = RolesConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{source}: {exc}") from exc
    if (usd := os.environ.get("REQGRAPH_RUN_BUDGET_USD")) is not None:
        cfg.budget = Budget(run_usd=float(usd), run_tokens=cfg.budget.run_tokens)
    return cfg
