"""One real call per provider, replayed from cassettes without network (T-005).

Re-record (needs network and keys; in a cloud session the proxy injects keys):
    uv run pytest packages/core/tests/llm/test_live_cassettes.py \\
        --record-mode=rewrite --force-enable-socket
"""

import pytest
from pydantic import BaseModel, Field
from reqgraph.llm import structured

pytestmark = [pytest.mark.anyio, pytest.mark.vcr]

PROMPT = (
    "Клиент автосервиса сказал: <client>Хочу, чтобы за сутки до визита приходила SMS-напоминалка"
    "</client>. Сформулируй одно функциональное требование."
)


class Requirement(BaseModel):
    statement: str = Field(description="одно требование в форме «Система должна ...»")
    acceptance: list[str] = Field(min_length=1, description="критерии приёмки")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.parametrize(
    ("role", "model_id", "provider"),
    [
        ("reviewer", None, "groq"),
        ("stakeholder", None, "groq"),  # Qwen on Groq: another family than the agents
        ("analyst", None, "gemini"),  # long-context role starts on Gemini
        ("analyst", "openrouter/nvidia/nemotron-3.5-super-vl:free", "openrouter"),
    ],
    ids=["reviewer-groq", "stakeholder-groq-qwen", "analyst-gemini", "analyst-openrouter-nemotron"],
)
async def test_structured_through_provider(role: str, model_id: str | None, provider: str) -> None:
    req, stats = await structured(role, PROMPT, Requirement, profile="free", model_id=model_id)
    assert stats.provider == provider
    assert "должна" in req.statement.lower()
    assert req.acceptance
    assert stats.input_tokens > 0 and stats.output_tokens > 0
    assert stats.cost_usd == 0  # free tiers
