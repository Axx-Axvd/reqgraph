from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from reqgraph_api import repo
from reqgraph_api.auth import CurrentUser
from reqgraph_api.db import Database, database
from reqgraph_api.schemas import AnswerIn, EventOut, JobOut, RunCreated, RunIn, RunOut

router = APIRouter(tags=["runs"])
Db = Annotated[Database, Depends(database)]
NOT_FOUND = "прогон не найден"


@router.post("/projects/{project_id}/runs", response_model=RunCreated, status_code=201)
async def create_run(project_id: UUID, body: RunIn, user: CurrentUser, db: Db) -> RunCreated:
    """A queued run and its start job; the worker (T-502) takes it from the queue."""
    async with db.as_user(user) as conn:
        made = await repo.create_run(conn, project_id, body.kind, body.brief, body.max_turns)
    if made is None:
        raise HTTPException(404, "проект не найден")
    run, job = made
    return RunCreated(run=RunOut.model_validate(run), job=JobOut.model_validate(job))


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
    run_id: UUID, user: CurrentUser, db: Database, body: AnswerIn | None = None
) -> JobOut:
    async with db.as_user(user) as conn:
        run = await repo.get_run(conn, run_id)
        if run is None:
            raise HTTPException(404, NOT_FOUND)
        try:
            job = (
                await repo.cancel(conn, run)
                if body is None
                else await repo.answer(conn, run, body.text, body.done)
            )
        except repo.Conflict as exc:
            raise HTTPException(409, str(exc)) from None
    return JobOut.model_validate(job)


@router.post("/runs/{run_id}/answer", response_model=JobOut, status_code=202)
async def answer(run_id: UUID, body: AnswerIn, user: CurrentUser, db: Db) -> JobOut:
    """The answer to the waiting interview question, or done: true to end the interview."""
    return await _job(run_id, user, db, body)


@router.post("/runs/{run_id}/cancel", response_model=JobOut, status_code=202)
async def cancel(run_id: UUID, user: CurrentUser, db: Db) -> JobOut:
    return await _job(run_id, user, db)
