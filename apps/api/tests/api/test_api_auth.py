"""Sign-in and the parts of the API that need no database (T-501): no network, no Postgres."""

from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient
from reqgraph_api.__main__ import openapi_text
from reqgraph_api.app import create_app
from reqgraph_api.auth import InvalidToken, TokenVerifier
from reqgraph_api.settings import Settings

from .conftest import KID, ROOT, Token

pytestmark = pytest.mark.anyio


def test_a_valid_token_gives_the_user(verifier: TokenVerifier, token: Token) -> None:
    user = uuid4()
    assert verifier.verify(token(user, email="a@example.invalid")).id == user


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [({"ttl": -10}, "срок токена истёк"), ({"aud": "anon"}, "InvalidAudienceError")],
)
def test_an_expired_or_foreign_audience_token_is_refused(
    verifier: TokenVerifier, token: Token, kwargs: dict[str, object], reason: str
) -> None:
    with pytest.raises(InvalidToken, match=reason):
        verifier.verify(token(uuid4(), **kwargs))


def test_a_token_signed_by_another_key_is_refused(verifier: TokenVerifier) -> None:
    other = ec.generate_private_key(ec.SECP256R1())
    payload = {"sub": str(uuid4()), "aud": "authenticated", "exp": 4_102_444_800}
    forged = jwt.encode(payload, other, algorithm="ES256", headers={"kid": KID})
    with pytest.raises(InvalidToken, match="InvalidSignatureError"):
        verifier.verify(forged)


def test_hs256_only_with_a_secret() -> None:
    payload = {"sub": str(uuid4()), "aud": "authenticated", "exp": 4_102_444_800}
    secret = "local-cli-secret-of-at-least-32-bytes!!"
    signed = jwt.encode(payload, secret, algorithm="HS256")
    with pytest.raises(InvalidToken, match="HS256"):
        TokenVerifier().verify(signed)
    assert str(TokenVerifier(hs256_secret=secret).verify(signed).id) == payload["sub"]


@pytest.fixture
async def bare(verifier: TokenVerifier) -> AsyncClient:
    app = create_app(Settings(database_url=None), verifier=verifier)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_without_a_token_every_route_but_health_is_401(bare: AsyncClient) -> None:
    async with bare as client:
        for path in ("/projects", f"/runs/{uuid4()}", f"/projects/{uuid4()}/graph"):
            response = await client.get(path)
            assert response.status_code == 401, path
            assert "Authorization" in response.json()["detail"]
        assert (
            await client.get("/projects", headers={"Authorization": "Bearer x"})
        ).status_code == 401
        assert (await client.get("/health")).json() == {"status": "degraded", "database": False}


async def test_without_a_database_a_signed_in_request_is_503(
    bare: AsyncClient, token: Token
) -> None:
    async with bare as client:
        auth = {"Authorization": f"Bearer {token(uuid4())}"}
        response = await client.get("/projects", headers=auth)
    assert response.status_code == 503 and "DATABASE_URL" in response.json()["detail"]


def test_the_committed_openapi_description_is_up_to_date() -> None:
    path: Path = ROOT / "schemas" / "openapi.json"
    assert path.read_text(encoding="utf-8") == openapi_text(), (
        "uv run reqgraph-api openapi --out schemas/openapi.json, затем pnpm -C apps/web gen:api"
    )
