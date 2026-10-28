"""Router behaviour without network: fallback, retries, budget, cost (T-005)."""

from collections.abc import Callable

import pytest
from pydantic import BaseModel
from pydantic_ai.exceptions import FallbackExceptionGroup, ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from reqgraph.llm import router
from reqgraph.llm.config import Step, load_roles
from reqgraph.llm.router import BudgetExceeded, RunBudget, model_for, structured

pytestmark = pytest.mark.anyio


class Requirement(BaseModel):
    statement: str
    priority: int


def answer(text: str) -> Callable[[list[ModelMessage], AgentInfo], ModelResponse]:
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(text)])

    return fn


def ok_model(name: str) -> FunctionModel:
    return FunctionModel(
        answer('{"statement": "Система должна ...", "priority": 1}'), model_name=name
    )


def failing_model(name: str, status: int = 429) -> FunctionModel:
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(status, name)

    return FunctionModel(fn, model_name=name)


@pytest.fixture
def fake_models(monkeypatch: pytest.MonkeyPatch) -> dict[str, Model]:
    """Replace real provider models with in-process fakes, keyed by 'provider/model' ids."""
    models: dict[str, Model] = {}

    def build(step: Step) -> Model:
        return models.get(step.id) or ok_model(step.model)

    monkeypatch.setattr(router, "_build_model", build)
    return models


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_structured_returns_object_and_stats(fake_models: dict[str, Model]) -> None:
    req, stats = await structured("reviewer", "Сформулируй требование", Requirement, profile="free")
    assert req.priority == 1
    assert stats.role == "reviewer"
    assert stats.provider == "groq"
    assert stats.outcome == "ok"
    assert stats.requests == 1
    assert stats.cost_usd == 0  # Groq free tier
    assert stats.latency_ms >= 0


async def test_falls_back_to_next_model_on_429(fake_models: dict[str, Model]) -> None:
    first, second = load_roles().ladder("reviewer", "free")[:2]
    fake_models[first.id] = failing_model(first.model, 429)
    _, stats = await structured("reviewer", "x", Requirement, profile="free")
    assert stats.model == second.model


async def test_falls_back_when_a_provider_blocks_the_answer(fake_models: dict[str, Model]) -> None:
    """Gemini answered a repair prompt with finish_reason «content_filter: PROHIBITED_CONTENT»
    (dev-02, 27.10): pydantic-ai raises UnexpectedModelBehavior, the ladder must go on."""
    from pydantic_ai.exceptions import UnexpectedModelBehavior

    first, second = load_roles().ladder("analyst", "free")[:2]

    def blocked(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise UnexpectedModelBehavior("Invalid response: content_filter: PROHIBITED_CONTENT")

    fake_models[first.id] = FunctionModel(blocked, model_name=first.model)
    _, stats = await structured("analyst", "x", Requirement, profile="free")
    assert stats.model == second.model


async def test_all_models_failing_raises(fake_models: dict[str, Model]) -> None:
    for step in load_roles().ladder("reviewer", "free"):
        fake_models[step.id] = failing_model(step.model, 503)
    with pytest.raises(FallbackExceptionGroup):
        await structured("reviewer", "x", Requirement, profile="free")


async def test_invalid_output_is_retried(fake_models: dict[str, Model]) -> None:
    calls = {"n": 0}

    def flaky(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        text = "не JSON" if calls["n"] == 1 else '{"statement": "ok", "priority": 2}'
        return ModelResponse(parts=[TextPart(text)])

    step = load_roles().ladder("reviewer", "free")[0]
    fake_models[step.id] = FunctionModel(flaky, model_name=step.model)
    req, stats = await structured("reviewer", "x", Requirement, profile="free")
    assert req.priority == 2
    assert stats.requests == 2


async def test_long_prompt_skips_small_context_provider(fake_models: dict[str, Model]) -> None:
    cfg = load_roles()
    groq_limit = cfg.providers["groq"].max_input_tokens
    assert groq_limit is not None
    long_prompt = "слово " * (groq_limit * 2)
    _, stats = await structured("interviewer", long_prompt, Requirement, profile="free")
    assert (
        stats.provider == "openrouter"
    )  # both Groq steps skipped up front instead of failing with 429


async def test_analyst_reads_long_interviews_on_gemini_first(fake_models: dict[str, Model]) -> None:
    long_prompt = "слово " * 30_000
    _, stats = await structured("analyst", long_prompt, Requirement, profile="free")
    assert stats.provider == "gemini"


def test_no_model_fits_is_an_error() -> None:
    with pytest.raises(ValueError, match="не помещается"):
        model_for("stakeholder", "free", prompt_chars=10**7)  # Groq only, and the prompt is huge


async def test_budget_stops_the_run(fake_models: dict[str, Model]) -> None:
    budget = RunBudget(usd=0.10, tokens=10**6)
    await structured("reviewer", "x", Requirement, profile="free", budget=budget)
    assert budget.spent_tokens > 0
    budget.tokens = budget.spent_tokens  # nothing left
    with pytest.raises(BudgetExceeded):
        await structured("reviewer", "x", Requirement, profile="free", budget=budget)


async def test_call_is_capped_by_remaining_tokens(fake_models: dict[str, Model]) -> None:
    with pytest.raises(BudgetExceeded, match="токен"):
        await structured(
            "reviewer", "x", Requirement, profile="free", budget=RunBudget(usd=1, tokens=5)
        )


async def test_paid_model_cost_is_counted(
    fake_models: dict[str, Model], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(router, "_list_price", lambda response: 0.0125)
    budget = RunBudget(usd=0.01, tokens=10**6)
    _, stats = await structured("analyst", "x", Requirement, profile="cheap", budget=budget)
    assert stats.cost_usd == pytest.approx(0.0125)
    assert stats.list_cost_usd == pytest.approx(0.0125)
    with pytest.raises(BudgetExceeded):
        await structured("analyst", "x", Requirement, profile="cheap", budget=budget)


async def test_free_model_keeps_list_price_separately(
    fake_models: dict[str, Model], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(router, "_list_price", lambda response: 0.002)
    _, stats = await structured("reviewer", "x", Requirement, profile="free")
    assert stats.cost_usd == 0
    assert stats.list_cost_usd == pytest.approx(0.002)


async def test_on_call_hook_receives_stats(fake_models: dict[str, Model]) -> None:
    seen: list[router.CallStats] = []
    await structured("reviewer", "x", Requirement, profile="free", on_call=seen.append)
    assert [s.role for s in seen] == ["reviewer"]


async def test_missing_key_uses_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    step = load_roles().ladder("reviewer", "free")[0]
    assert router._api_key(load_roles().providers[step.provider]) == "placeholder"


def test_seed_only_for_providers_that_accept_it() -> None:
    cfg = load_roles()
    groq = router._build_model(cfg.ladder("reviewer", "free")[0])
    gemini = router._build_model(cfg.ladder("analyst", "free")[0])
    assert (groq.settings or {}).get("seed") == cfg.defaults.seed
    assert "seed" not in (gemini.settings or {})


async def test_model_id_pins_one_model(fake_models: dict[str, Model]) -> None:
    _, stats = await structured("analyst", "x", Requirement, model_id="groq/openai/gpt-oss-20b")
    assert (stats.provider, stats.model) == ("groq", "openai/gpt-oss-20b")


async def test_model_id_with_unknown_provider_is_rejected(fake_models: dict[str, Model]) -> None:
    with pytest.raises(ValueError, match="провайдер"):
        await structured("analyst", "x", Requirement, model_id="nosuch/model")


def test_output_mode_from_provider() -> None:
    cfg = load_roles()
    groq = router._build_model(cfg.ladder("reviewer", "free")[0])
    gemini = router._build_model(cfg.ladder("analyst", "free")[0])
    assert groq.profile.get("default_structured_output_mode") == "native"
    assert gemini.profile.get("default_structured_output_mode") == "tool"


async def test_given_model_replaces_the_ladder() -> None:
    """Agents' tests and dry runs pass a stub model: no ladder, no provider, no cost."""
    model = ok_model("stub")
    output, stats = await structured("analyst", "бриф", Requirement, model=model)
    assert output.priority == 1
    assert (stats.provider, stats.model, stats.cost_usd, stats.list_cost_usd) == (
        "function",
        "stub",
        0.0,
        None,
    )


async def test_a_rate_limited_ladder_waits_and_asks_again(
    fake_models: dict[str, Model], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Free tiers count tokens per minute: when every model answers 429, wait and retry."""
    calls: list[int] = []

    def flaky(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(1)
        if len(calls) < 3:
            raise ModelHTTPError(429, "qwen", retry_after=7)
        return ModelResponse(parts=[TextPart('{"statement": "Система должна ...", "priority": 1}')])

    waits: list[float] = []

    async def no_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr("reqgraph.llm.router.asyncio.sleep", no_sleep)
    for step in load_roles().ladder("stakeholder", "free"):  # one model: no fallback to try
        fake_models[step.id] = FunctionModel(flaky, model_name=step.model)
    out, stats = await structured("stakeholder", "п", Requirement, profile="free")
    assert out.priority == 1 and waits == [7, 7] and stats.latency_ms < 7000


async def test_other_errors_and_too_many_429_are_not_waited_out(
    fake_models: dict[str, Model], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("reqgraph.llm.router.asyncio.sleep", no_sleep)
    for step in load_roles().ladder("stakeholder", "free"):
        fake_models[step.id] = failing_model(step.model, 500)
    with pytest.raises(ModelHTTPError):
        await structured("stakeholder", "п", Requirement, profile="free")
    for step in load_roles().ladder("stakeholder", "free"):
        fake_models[step.id] = failing_model(step.model, 429)
    with pytest.raises(ModelHTTPError):
        await structured("stakeholder", "п", Requirement, profile="free")
    assert router.rate_limited(FallbackExceptionGroup("x", [ModelHTTPError(429, "a")])) == 20.0
    assert router.rate_limited(ModelHTTPError(429, "a", retry_after=3600)) is None  # a daily limit
    mixed = FallbackExceptionGroup("x", [ModelHTTPError(429, "a"), ModelHTTPError(500, "b")])
    assert router.rate_limited(mixed) is None
