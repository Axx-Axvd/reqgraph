"""Access tokens of Supabase Auth: the signature by the project's JWKS (ES256, RS256), the
audience and the expiry; HS256 only with a secret set (a local Supabase CLI). No network call
per request: PyJWKClient keeps the keys."""

from collections.abc import Mapping
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from reqgraph_api.settings import Settings

ASYMMETRIC = ("ES256", "RS256")


class User(BaseModel):
    id: UUID
    email: str | None = None


class InvalidToken(Exception):
    """The token is not accepted; the message says why, in Russian, without the token."""


class TokenVerifier:
    def __init__(
        self,
        *,
        jwks_url: str | None = None,
        jwks: Mapping[str, Any] | None = None,
        hs256_secret: str | None = None,
        audience: str = "authenticated",
    ) -> None:
        self._client = (
            jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=600) if jwks_url else None
        )
        self._keys = jwt.PyJWKSet.from_dict(dict(jwks)) if jwks else None
        self._secret = hs256_secret
        self._audience = audience

    @classmethod
    def from_settings(cls, settings: Settings) -> "TokenVerifier":
        return cls(
            jwks_url=settings.supabase_jwks_url,
            hs256_secret=settings.supabase_jwt_secret,
            audience=settings.supabase_jwt_aud,
        )

    def _key(self, token: str) -> tuple[Any, str]:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")
        if alg == "HS256":
            if not self._secret:
                raise InvalidToken("подпись HS256 не принимается")
            return self._secret, alg
        if alg not in ASYMMETRIC:
            raise InvalidToken(f"неизвестный алгоритм подписи {alg!r}")
        kid = header.get("kid")
        if not isinstance(kid, str):
            raise InvalidToken("в токене нет kid")
        if self._keys is not None:
            for key in self._keys.keys:
                if key.key_id == kid:
                    return key.key, alg
            raise InvalidToken("ключ подписи не найден")
        if self._client is None:
            raise InvalidToken("ключи подписи не настроены (SUPABASE_JWKS_URL)")
        return self._client.get_signing_key(kid).key, alg

    def verify(self, token: str) -> User:
        try:
            key, alg = self._key(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=[alg],
                audience=self._audience,
                options={"require": ["exp", "sub", "aud"]},
            )
            return User(id=UUID(claims["sub"]), email=claims.get("email"))
        except InvalidToken:
            raise
        except jwt.ExpiredSignatureError:
            raise InvalidToken("срок токена истёк") from None
        except (jwt.PyJWTError, ValueError) as exc:
            raise InvalidToken(type(exc).__name__) from None


_bearer = HTTPBearer(auto_error=False)


def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """The signed-in user; 401 without a valid token. Sync: a JWKS refresh runs in a thread."""
    challenge = {"WWW-Authenticate": "Bearer"}
    if credentials is None:
        raise HTTPException(401, "нужен вход: заголовок Authorization: Bearer <токен>", challenge)
    verifier: TokenVerifier = request.app.state.verifier
    try:
        return verifier.verify(credentials.credentials)
    except InvalidToken as exc:
        raise HTTPException(401, f"токен не принят: {exc}", challenge) from None


CurrentUser = Annotated[User, Depends(current_user)]
