"""Users' own model keys (BYOK, T-503) in the memory of the process, by run, for a while.

07_deploy: the key lives in the browser and comes in a header; the server never stores it. The API
and the worker share one process (ADR-009), so the API hands the key to the worker here. Nothing of
it goes to the database, the events or the logs; after a restart it is gone and the user sends it
again with the next answer."""

import time
from uuid import UUID

HEADER = "X-OpenRouter-Key"


class RunKeys:
    def __init__(self, ttl_seconds: float = 2 * 3600) -> None:
        self._keys: dict[UUID, tuple[str, float]] = {}
        self._ttl = ttl_seconds

    def put(self, run_id: UUID, key: str) -> None:
        self._sweep()
        self._keys[run_id] = (key, time.monotonic() + self._ttl)

    def get(self, run_id: UUID) -> str | None:
        self._sweep()
        held = self._keys.get(run_id)
        return None if held is None else held[0]

    def drop(self, run_id: UUID) -> None:
        self._keys.pop(run_id, None)

    def _sweep(self) -> None:
        now = time.monotonic()
        for run_id in [r for r, (_, until) in self._keys.items() if until < now]:
            del self._keys[run_id]

    def __repr__(self) -> str:  # never show a key, even in a traceback
        return f"RunKeys({len(self._keys)} runs)"
