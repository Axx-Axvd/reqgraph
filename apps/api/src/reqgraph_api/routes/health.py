from fastapi import APIRouter, Request

from reqgraph_api.maintenance import memory_mb, peak_memory_mb
from reqgraph_api.schemas import Health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health)
async def health(request: Request) -> Health:
    """Without sign-in: the service is up; database — select 1 passes (keepalive.yml, T-506)."""
    db = request.app.state.db
    try:
        ok = db is not None and await db.ping()
    except Exception:  # an unreachable database is a state to report, not a 500
        ok = False
    return Health(
        status="ok" if ok else "degraded",
        database=ok,
        memory_mb=memory_mb(),
        peak_memory_mb=peak_memory_mb(),
    )
