"""T-505 without a database: the new addresses need a sign-in; the Storage client (no network)."""

import logging
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from reqgraph_api.app import create_app
from reqgraph_api.auth import TokenVerifier
from reqgraph_api.settings import Settings
from reqgraph_api.storage import StorageError, SupabaseStorage

pytestmark = pytest.mark.anyio
SECRET = "service-role-test-value"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/projects/{id}/report"),
        ("GET", "/projects/{id}/processes/PRC-01/bpmn"),
        ("POST", "/projects/{id}/exports"),
    ],
)
async def test_results_need_a_sign_in(verifier: TokenVerifier, method: str, path: str) -> None:
    app = create_app(Settings(), verifier=verifier)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(method, path.format(id=uuid4()))
    assert response.status_code == 401


async def test_upload_goes_to_the_bucket_with_the_server_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"Key": "exports/x"})

    storage = SupabaseStorage(
        "http://127.0.0.1:54321/", SecretStr(SECRET), transport=httpx.MockTransport(handler)
    )
    await storage.upload("p/1/srs.docx", b"doc", "application/octet-stream")
    request = seen[0]
    assert str(request.url) == "http://127.0.0.1:54321/storage/v1/object/exports/p/1/srs.docx"
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    assert request.headers["x-upsert"] == "true" and request.content == b"doc"

    failing = SupabaseStorage(
        "http://127.0.0.1:54321",
        SecretStr(SECRET),
        transport=httpx.MockTransport(lambda _: httpx.Response(403, json={"error": "denied"})),
    )
    with caplog.at_level(logging.DEBUG), pytest.raises(StorageError, match="HTTP 403") as err:
        await failing.upload("p/1/a.md", b"x", "text/markdown")
    assert SECRET not in str(err.value) and SECRET not in caplog.text
