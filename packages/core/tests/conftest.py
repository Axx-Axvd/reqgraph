"""Shared pytest configuration for reqgraph core tests."""

from pathlib import Path
from typing import Any

import pytest

CASSETTES = Path(__file__).parent / "cassettes"
SECRET_HEADERS = ["authorization", "x-goog-api-key", "api-key", "cookie", "set-cookie"]


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, Any]:
    """Cassettes never store keys: request and response headers with secrets are dropped."""
    return {
        "filter_headers": SECRET_HEADERS,
        "before_record_response": _strip_response_headers,
        "decode_compressed_response": True,
    }


@pytest.fixture(scope="module")
def vcr_cassette_dir() -> str:
    return str(CASSETTES)


def _strip_response_headers(response: dict[str, Any]) -> dict[str, Any]:
    headers = response.get("headers", {})
    for name in list(headers):
        if name.lower() in SECRET_HEADERS:
            del headers[name]
    return response
