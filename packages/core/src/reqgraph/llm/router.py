"""The only way agents call LLMs: role -> model ladder -> structured output (ADR-013).

``structured()`` builds a pydantic-ai FallbackModel from roles.yaml, asks for a Pydantic object,
retries invalid output, falls back to the next model on 429 / 5xx / timeout, and reports tokens,
cost and latency as ``CallStats``. API keys are read from the environment and never logged.
"""

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic_ai import Agent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from reqgraph.llm.config import Provider, RolesConfig, Step, load_roles

log = logging.getLogger(__name__)

# Without a key in the environment a placeholder is sent: in cloud sessions the egress proxy
# injects the real key; elsewhere the provider answers 401 and the error names key_env.
PLACEHOLDER_KEY = "placeholder"
CHARS_PER_TOKEN = 3  # rough estimate for Russian text, enough to skip small-context providers


class BudgetExceeded(RuntimeError):
    """The run has spent its dollar or token budget."""


@dataclass(frozen=True)
class CallStats:
    """One structured() call, as written to run_events."""

    role: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    requests: int
    cost_usd: float
    list_cost_usd: float | None
    latency_ms: int
    outcome: Literal["ok"]


@dataclass
class RunBudget:
    """Dollars and tokens left for one run (REQGRAPH_RUN_BUDGET_USD, roles.yaml budget)."""

    usd: float
    tokens: int
    spent_usd: float = 0.0
    spent_tokens: int = 0

    def check(self) -> None:
        if self.spent_usd >= self.usd or self.spent_tokens >= self.tokens:
            raise BudgetExceeded(
                f"бюджет прогона исчерпан: ${self.spent_usd:.4f} из ${self.usd:.2f}, "
                f"{self.spent_tokens} из {self.tokens} токенов"
            )

    def add(self, stats: CallStats) -> None:
        self.spent_usd += stats.cost_usd
        self.spent_tokens += stats.input_tokens + stats.output_tokens


def _api_key(provider: Provider) -> str:
    if provider.key_env is None:
        return "ollama"
    return os.environ.get(provider.key_env) or PLACEHOLDER_KEY


def _base_url(provider: Provider) -> str:
    if provider.base_url_env and (url := os.environ.get(provider.base_url_env)):
        return url
    return provider.base_url


_CONFIG: RolesConfig | None = None


def _config() -> RolesConfig:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = load_roles()
    return _CONFIG


def _build_model(step: Step) -> Model:
    cfg = _config()
    provider = cfg.providers[step.provider]
    settings = ModelSettings()
    if cfg.defaults.seed is not None and provider.supports_seed:
        settings["seed"] = cfg.defaults.seed
    client = OpenAIProvider(base_url=_base_url(provider), api_key=_api_key(provider))
    model = OpenAIChatModel(step.model, provider=client, settings=settings)
    if provider.output_mode is None:
        return model
    profile = model.profile.copy()
    profile["default_structured_output_mode"] = provider.output_mode
    return OpenAIChatModel(step.model, provider=client, settings=settings, profile=profile)


def _fitting_steps(role: str, profile: str | None, prompt_chars: int) -> tuple[Step, ...]:
    cfg = _config()
    tokens = prompt_chars // CHARS_PER_TOKEN
    steps = tuple(
        s
        for s in cfg.ladder(role, profile)
        if (limit := cfg.providers[s.provider].max_input_tokens) is None or tokens <= limit
    )
    if not steps:
        raise ValueError(f"промпт (~{tokens} токенов) не помещается ни в одну модель роли «{role}»")
    return steps


def model_for(role: str, profile: str | None = None, *, prompt_chars: int = 0) -> Model:
    """The model for a role: a single model or a FallbackModel over the ladder."""
    models = [_build_model(s) for s in _fitting_steps(role, profile, prompt_chars)]
    return models[0] if len(models) == 1 else FallbackModel(*models)


def _list_price(response: ModelResponse) -> float | None:
    """Price by the public price list (genai-prices); None if the model is not listed."""
    try:
        return float(response.cost().total_price)
    except Exception:  # LookupError and friends: unknown model or provider in genai-prices
        log.warning("нет цены для модели %s", response.model_name)
        return None


def _answered_by(steps: tuple[Step, ...], model_name: str | None) -> Step:
    for step in steps:
        if step.model == model_name:
            return step
    return steps[0]


async def structured[T](
    role: str,
    prompt: str,
    output_type: type[T],
    *,
    instructions: str | None = None,
    profile: str | None = None,
    budget: RunBudget | None = None,
    on_call: Callable[[CallStats], None] | None = None,
    model_id: str | None = None,
) -> tuple[T, CallStats]:
    """Ask the role's models for an ``output_type`` object; return it with call statistics.

    ``model_id`` ("provider/model") pins one model without fallback: used by probe (T-006) to
    compare models on the same tasks.
    """
    cfg = _config()
    if budget is not None:
        budget.check()
    if model_id is not None:
        step = Step.parse(model_id)
        if step.provider not in cfg.providers:
            raise ValueError(f"неизвестный провайдер «{step.provider}» в «{model_id}»")
        steps: tuple[Step, ...] = (step,)
    else:
        steps = _fitting_steps(role, profile, len(prompt) + len(instructions or ""))
    models = [_build_model(s) for s in steps]
    model = models[0] if len(models) == 1 else FallbackModel(*models)
    # seed is set per model in _build_model: not every provider accepts it.
    settings = ModelSettings(temperature=cfg.defaults.temperature, timeout=cfg.defaults.timeout_s)
    token_cap = cfg.budget.run_tokens if budget is None else budget.tokens - budget.spent_tokens
    agent = Agent(
        model, output_type=output_type, instructions=instructions, retries=cfg.defaults.retries
    )

    started = time.perf_counter()
    try:
        result = await agent.run(
            prompt,
            model_settings=settings,
            usage_limits=UsageLimits(
                request_limit=cfg.defaults.retries + 2, total_tokens_limit=token_cap
            ),
        )
    except UsageLimitExceeded as exc:
        raise BudgetExceeded(
            f"вызов роли «{role}» превысил остаток токенов прогона: {exc}"
        ) from exc
    latency_ms = int((time.perf_counter() - started) * 1000)

    step = _answered_by(steps, result.response.model_name)
    usage = result.usage
    list_price = _list_price(result.response)
    stats = CallStats(
        role=role,
        model=step.model,
        provider=step.provider,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        requests=usage.requests,
        cost_usd=0.0 if cfg.is_free(step) else (list_price or 0.0),
        list_cost_usd=list_price,
        latency_ms=latency_ms,
        outcome="ok",
    )
    if budget is not None:
        budget.add(stats)
    if on_call is not None:
        on_call(stats)
    log.info(
        "llm %s %s/%s in=%d out=%d $%.4f %dms",
        role,
        stats.provider,
        stats.model,
        stats.input_tokens,
        stats.output_tokens,
        stats.cost_usd,
        latency_ms,
    )
    return result.output, stats
