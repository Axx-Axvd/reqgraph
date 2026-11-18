"""Fixtures of the API tests: signed test tokens (no network) and a database for the `pg` tests.

The `pg` tests need REQGRAPH_TEST_DATABASE_URL. On a Supabase with the migrations applied
(pnpm db:start && pnpm db:reset, the CI job «db») they run as is; on a bare Postgres (a superuser
URL) a fresh database gets supabase_stub.sql and all migrations, and is dropped afterwards.
"""

import json
import os
import time
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient
from jwt.algorithms import ECAlgorithm
from psycopg.conninfo import make_conninfo
from reqgraph_api.app import create_app
from reqgraph_api.auth import TokenVerifier
from reqgraph_api.db import Database, make_pool
from reqgraph_api.settings import Settings

ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS = ROOT / "supabase" / "migrations"
STUB = Path(__file__).with_name("supabase_stub.sql")
DB_ENV = "REQGRAPH_TEST_DATABASE_URL"
KID = "test-key-1"
Token = Callable[..., str]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="session")
def verifier(signing_key: ec.EllipticCurvePrivateKey) -> TokenVerifier:
    jwk = json.loads(ECAlgorithm.to_jwk(signing_key.public_key())) | {"kid": KID, "alg": "ES256"}
    return TokenVerifier(jwks={"keys": [jwk]})


@pytest.fixture(scope="session")
def token(signing_key: ec.EllipticCurvePrivateKey) -> Token:
    """A Supabase-like access token: ES256, kid, aud «authenticated», sub — the user id."""

    def make(user: UUID, *, ttl: int = 600, aud: str = "authenticated", **claims: Any) -> str:
        now = int(time.time())
        payload = {"sub": str(user), "aud": aud, "role": "authenticated", "iat": now}
        payload |= {"exp": now + ttl, **claims}
        return jwt.encode(payload, signing_key, algorithm="ES256", headers={"kid": KID})

    return make


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    url = os.environ.get(DB_ENV)
    if not url:
        pytest.skip(f"нет {DB_ENV}: тесты с базой пропущены")
    with psycopg.connect(url, autocommit=True) as conn:
        row = conn.execute("select to_regnamespace('auth') is not null").fetchone()
        if row and row[0]:  # Supabase: the migrations are already applied
            yield url
            return
        name = f"reqgraph_test_{uuid4().hex[:8]}"
        conn.execute(f'create database "{name}"')
    test_url = make_conninfo(url, dbname=name)
    try:
        with psycopg.connect(test_url, autocommit=True) as conn:
            conn.execute(STUB.read_text(encoding="utf-8"))
            for migration in sorted(MIGRATIONS.glob("*.sql")):
                conn.execute(migration.read_text(encoding="utf-8"))
        yield test_url
    finally:
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(f'drop database if exists "{name}" with (force)')


@pytest.fixture
async def database(database_url: str) -> AsyncIterator[Database]:
    pool = make_pool(database_url, min_size=1, max_size=3)
    await pool.open()
    try:
        yield Database(pool)
    finally:
        await pool.close()


def add_user(database_url: str, email: str | None = None) -> UUID:
    """A registered user: a row in auth.users, the trigger creates the profile."""
    user = uuid4()
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(
            "insert into auth.users (id, email, aud, role) "
            "values (%s, %s, 'authenticated', 'authenticated')",
            [user, email or f"{user.hex[:8]}@example.invalid"],
        )
    return user


@pytest.fixture
def new_user(database_url: str) -> Callable[[], UUID]:
    return lambda: add_user(database_url)


@pytest.fixture
async def client(database: Database, verifier: TokenVerifier) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(), database=database, verifier=verifier)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
