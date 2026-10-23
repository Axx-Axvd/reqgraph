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
    ("role", "profile", "provider"),
    [
        ("reviewer", "free", "groq"),
        ("stakeholder", "free", "gemini"),
        ("analyst", "free", "openrouter"),
    ],
)
async def test_structured_through_provider(role: str, profile: str, provider: str) -> None:
    req, stats = await structured(role, PROMPT, Requirement, profile=profile)
    assert stats.provider == provider
    assert "должна" in req.statement.lower()
    assert req.acceptance
    assert stats.input_tokens > 0 and stats.output_tokens > 0
    assert stats.cost_usd == 0  # free tiers
