"""Supabase Storage for the exported files (T-505): the API uploads with the service role key,
the site downloads through signed links made under the bucket policy (owner of the project)."""

import logging
from typing import Protocol

import httpx
from pydantic import SecretStr

BUCKET = "exports"
log = logging.getLogger(__name__)


class StorageError(RuntimeError):
    """The file was not stored; the message is for the user, without keys."""


class Storage(Protocol):
    async def upload(self, path: str, data: bytes, content_type: str) -> None: ...

    async def remove(self, paths: list[str]) -> None: ...


class SupabaseStorage:
    """The Storage REST API: POST /storage/v1/object/<bucket>/<path>, overwriting a file left by
    a failed export."""

    def __init__(
        self,
        url: str,
        key: SecretStr,
        bucket: str = BUCKET,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base = f"{url.rstrip('/')}/storage/v1/object/{bucket}"
        self._key = key
        self._transport = transport

    async def upload(self, path: str, data: bytes, content_type: str) -> None:
        secret = self._key.get_secret_value()
        headers = {
            "Authorization": f"Bearer {secret}",
            "apikey": secret,
            "Content-Type": content_type,
            "x-upsert": "true",
        }
        async with httpx.AsyncClient(transport=self._transport, timeout=60) as client:
            response = await client.post(f"{self.base}/{path}", content=data, headers=headers)
        if response.status_code >= 300:
            log.warning("storage upload %s: HTTP %s", path, response.status_code)
            raise StorageError(f"файл {path} не сохранён в хранилище (HTTP {response.status_code})")

    async def remove(self, paths: list[str]) -> None:
        """Delete files of the bucket (T-506: exports older than 30 days); a missing file is not
        an error for Storage."""
        if not paths:
            return
        secret = self._key.get_secret_value()
        headers = {"Authorization": f"Bearer {secret}", "apikey": secret}
        async with httpx.AsyncClient(transport=self._transport, timeout=60) as client:
            response = await client.request(
                "DELETE", self.base, json={"prefixes": paths}, headers=headers
            )
        if response.status_code >= 300:
            log.warning("storage remove of %s files: HTTP %s", len(paths), response.status_code)
            raise StorageError(f"файлы не удалены из хранилища (HTTP {response.status_code})")
