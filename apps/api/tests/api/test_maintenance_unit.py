"""T-506 without a database: Storage removal, memory in /health and in the worker log."""

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from reqgraph_api import maintenance
from reqgraph_api.app import create_app
from reqgraph_api.storage import StorageError, SupabaseStorage

pytestmark = pytest.mark.anyio


async def test_remove_deletes_the_paths_from_the_bucket() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    storage = SupabaseStorage(
        "http://127.0.0.1:54321", SecretStr("k"), transport=httpx.MockTransport(handler)
    )
    await storage.remove(["p/1/a.md", "p/1/b.docx"])
    await storage.remove([])  # nothing to do: no request
    assert len(seen) == 1 and seen[0].method == "DELETE"
    assert str(seen[0].url) == "http://127.0.0.1:54321/storage/v1/object/exports"
    assert seen[0].read() == b'{"prefixes":["p/1/a.md","p/1/b.docx"]}'

    failing = SupabaseStorage(
        "http://127.0.0.1:54321",
        SecretStr("k"),
        transport=httpx.MockTransport(lambda _: httpx.Response(500)),
    )
    with pytest.raises(StorageError, match="HTTP 500"):
        await failing.remove(["p/1/a.md"])


async def test_health_reports_memory_without_a_database() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = (await client.get("/health")).json()
    assert body["status"] == "degraded" and body["database"] is False
    memory = maintenance.memory_mb()
    if memory is None:  # Windows: no resource module
        assert body["memory_mb"] is None and body["peak_memory_mb"] is None
    else:
        assert body["memory_mb"] > 0 and body["peak_memory_mb"] >= body["memory_mb"] - 1
