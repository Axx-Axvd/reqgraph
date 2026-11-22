from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from reqgraph_api import limits, repo
from reqgraph_api.auth import CurrentUser
from reqgraph_api.db import Database, database
from reqgraph_api.keys import HEADER, RunKeys
from reqgraph_api.schemas import AnswerIn, EventOut, JobOut, RunCreated, RunIn, RunOut, UsageOut

router = APIRouter(tags=["runs"])
Db = Annotated[Database, Depends(database)]
NOT_FOUND = "прогон не найден"


OwnKey = Annotated[
    str | None,
    Header(
        alias=HEADER,
        min_length=8,
        max_length=200,
        description="свой ключ OpenRouter (BYOK): прогон за счёт пользователя, без лимитов демо; "
        "на сервере не сохраняется",
    ),
]


def run_keys(request: Request) -> RunKeys:
    keys: RunKeys = request.app.state.keys
    return keys


@router.post(
    "/projects/{project_id}/runs",
    response_model=RunCreated,
    status_code=201,
    responses={429: {"description": "лимит демо на сегодня исчерпан"}},
)
async def create_run(
    project_id: UUID,
    body: RunIn,
    user: CurrentUser,
    db: Db,
    request: Request,
    own_key: OwnKey = None,
) -> RunCreated:
    """A queued run and its start job; the worker (T-502) takes it from the queue. Demo limits
    (T-503): runs per day and the daily cap; with an own key — none."""
    settings = request.app.state.settings
    async with db.as_user(user) as conn:
        config = await repo.project_config(conn, project_id)
        if config is None:
            raise HTTPException(404, "проект не найден")
        try:
            admission = await limits.admit(
                conn,
                user.id,
                byok=own_key is not None,
                profile=config.models.profile,
                settings=settings,
            )
        except limits.LimitReached as exc:
            raise HTTPException(
                429, str(exc), headers={"Retry-After": str(exc.retry_after)}
            ) from None
        run, job = await repo.create_run(
            conn,
            project_id,
            config,
            body.kind,
            body.brief,
            body.max_turns,
            profile=admission.profile,
            byok=admission.byok,
            client_level=body.client_level if body.kind == "interview" else None,
        )
        if own_key is not None:
            run_keys(request).put(run["id"], own_key)
    return RunCreated(run=RunOut.model_validate(run), job=JobOut.model_validate(job))


@router.get("/usage", response_model=UsageOut)
async def get_usage(user: CurrentUser, db: Db, request: Request) -> UsageOut:
    """Runs and dollars of the signed-in user today and the demo limit (a day is Moscow time)."""
    async with db.as_user(user) as conn:
        return UsageOut.model_validate(await limits.usage(conn, request.app.state.settings))


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: UUID, user: CurrentUser, db: Db) -> RunOut:
    async with db.as_user(user) as conn:
        row = await repo.get_run(conn, run_id)
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return RunOut.model_validate(row)


@router.get("/runs/{run_id}/events", response_model=list[EventOut])
async def get_events(
    run_id: UUID,
    user: CurrentUser,
    db: Db,
    after: Annotated[int, Query(ge=0, description="id последнего полученного события")] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[EventOut]:
    """Events after a given id: the fallback when Realtime is not available (07_deploy)."""
    async with db.as_user(user) as conn:
        if await repo.get_run(conn, run_id) is None:
            raise HTTPException(404, NOT_FOUND)
        return [EventOut.model_validate(r) for r in await repo.events(conn, run_id, after, limit)]


async def _job(
    run_id: UUID,
    user: CurrentUser,
    db: Database,
    body: AnswerIn | None = None,
    keys: RunKeys | None = None,
    own_key: str | None = None,
) -> JobOut:
    async with db.as_user(user) as conn:
        run = await repo.get_run(conn, run_id)
        if run is None:
            raise HTTPException(404, NOT_FOUND)
        if body is not None and run["byok"] and run["status"] == "waiting_input":
            if own_key is None:
                raise HTTPException(
                    400, f"прогон идёт на своём ключе: передайте его снова в заголовке {HEADER}"
                )
            assert keys is not None
            keys.put(run["id"], own_key)
        try:
            job = (
                await repo.cancel(conn, run)
                if body is None
                else await repo.answer(conn, run, body.text, body.done, body.simpler)
            )
        except repo.Conflict as exc:
            raise HTTPException(409, str(exc)) from None
    return JobOut.model_validate(job)


@router.post("/runs/{run_id}/answer", response_model=JobOut, status_code=202)
async def answer(
    run_id: UUID,
    body: AnswerIn,
    user: CurrentUser,
    db: Db,
    request: Request,
    own_key: OwnKey = None,
) -> JobOut:
    """The answer to the waiting interview question, done: true to end the interview, or
    simpler: true to hear the same question in plainer words (no question spent); a run on
    the user's own key needs the key again (the server keeps it only in memory)."""
    return await _job(run_id, user, db, body, run_keys(request), own_key)


@router.post("/runs/{run_id}/cancel", response_model=JobOut, status_code=202)
async def cancel(run_id: UUID, user: CurrentUser, db: Db) -> JobOut:
    return await _job(run_id, user, db)
