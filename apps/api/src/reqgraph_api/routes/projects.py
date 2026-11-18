from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from reqgraph_api import repo
from reqgraph_api.auth import CurrentUser
from reqgraph_api.db import Database, database
from reqgraph_api.schemas import ExportOut, GraphOut, ProjectIn, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])
Db = Annotated[Database, Depends(database)]
NOT_FOUND = "проект не найден"


@router.get("", response_model=list[ProjectOut])
async def list_projects(user: CurrentUser, db: Db) -> list[ProjectOut]:
    async with db.as_user(user) as conn:
        return [ProjectOut.model_validate(r) for r in await repo.list_projects(conn)]


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectIn, user: CurrentUser, db: Db) -> ProjectOut:
    async with db.as_user(user) as conn:
        row = await repo.create_project(conn, user.id, body.name, body.brief)
    return ProjectOut.model_validate(row)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: UUID, user: CurrentUser, db: Db) -> ProjectOut:
    async with db.as_user(user) as conn:
        row = await repo.get_project(conn, project_id)
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return ProjectOut.model_validate(row)


@router.get("/{project_id}/graph", response_model=GraphOut)
async def get_graph(
    project_id: UUID,
    user: CurrentUser,
    db: Db,
    rev: Annotated[int | None, Query(ge=0, description="ревизия; без неё — последняя")] = None,
) -> GraphOut:
    async with db.as_user(user) as conn:
        row = await repo.graph(conn, project_id, rev)
    if row is None:
        raise HTTPException(404, NOT_FOUND if rev is None else f"нет ревизии {rev}")
    return GraphOut.model_validate(row)


@router.get("/{project_id}/exports", response_model=list[ExportOut])
async def list_exports(project_id: UUID, user: CurrentUser, db: Db) -> list[ExportOut]:
    async with db.as_user(user) as conn:
        if await repo.get_project(conn, project_id) is None:
            raise HTTPException(404, NOT_FOUND)
        return [ExportOut.model_validate(r) for r in await repo.exports(conn, project_id)]
