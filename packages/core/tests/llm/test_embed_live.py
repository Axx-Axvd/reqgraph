"""Embeddings of the free profile (Gemini, T-304), replayed from a cassette without network.

Re-record (needs network and the key; in a cloud session the proxy injects it):
    uv run pytest packages/core/tests/llm/test_embed_live.py \\
        --record-mode=rewrite --force-enable-socket
"""

from pathlib import Path

import pytest
from reqgraph.llm.embed import cosine, embed

pytestmark = [pytest.mark.anyio, pytest.mark.vcr]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_paraphrases_are_closer_than_other_requirements(tmp_path: Path) -> None:
    texts = [
        "Пациент может отменить запись не позднее чем за 3 часа до приёма.",
        "Отменить приём онлайн можно не позже трёх часов до его начала.",
        "Сайт выдерживает 300 посетителей одновременно в субботнее утро.",
    ]
    a, b, c = await embed(texts, profile="free", cache=tmp_path)
    assert len(a) > 100
    assert cosine(a, b) > cosine(a, c) + 0.1
