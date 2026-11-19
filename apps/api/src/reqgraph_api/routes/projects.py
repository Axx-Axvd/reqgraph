import asyncio
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from reqgraph.checks.report import CIReport
from reqgraph.dsl.process import DslError, parse_process

from reqgraph_api import exporting, repo, store
from reqgraph_api.auth import CurrentUser
from reqgraph_api.db import Database, database, elevate
from reqgraph_api.schemas import ExportOut, GraphOut, ProjectIn, ProjectOut
from reqgraph_api.storage import Storage, StorageError

router = APIRouter(prefix="/projects", tags=["projects"])
Db = Annotated[Database, Depends(database)]
NOT_FOUND = "проект не найден"
Rev = Annotated[int | None, Query(ge=0, description="ревизия; без неё — последняя")]
log = logging.getLogger(__name__)


@router.get("", response_model=list[ProjectOut])
async def list_projects(user: CurrentUser, db: Db) -> list[ProjectOut]:
    async with db.as_user(user) as conn:
        return [ProjectOut.model_validate(r) for r in await repo.list_projects(conn)]


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    body: ProjectIn, user: CurrentUser, db: Db, request: Request
) -> ProjectOut:
    async with db.as_user(user) as conn:
        profile = request.app.state.settings.project_profile
        row = await repo.create_project(conn, user.id, body.name, body.brief, profile)
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
    rev: Rev = None,
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


@router.get("/{project_id}/report", response_model=CIReport)
async def get_report(project_id: UUID, user: CurrentUser, db: Db, rev: Rev = None) -> CIReport:
    """The CI report of a revision: kept by the worker after a run; for an older revision it is
    computed here without network (Kroki checks are skipped) and kept."""
    from reqgraph.checks.runner import run_checks

    async with db.as_user(user) as conn:
        row = await repo.ci_report(conn, project_id, rev)
        if row is None:
            raise HTTPException(404, NOT_FOUND if rev is None else f"нет ревизии {rev}")
        if row["ci_report"] is not None:
            return CIReport.model_validate(row["ci_report"])
        project, at = await store.load(conn, project_id, row["rev"])
    report = await run_checks(project, offline=True)
    async with db.as_user(user) as conn:
        await elevate(conn)
        await repo.save_ci_report(conn, project_id, at, report.model_dump(mode="json"))
    return report


@router.get(
    "/{project_id}/processes/{process_id}/bpmn",
    response_class=Response,
    responses={200: {"content": {"application/xml": {}}, "description": "BPMN 2.0 XML"}},
)
async def get_bpmn(
    project_id: UUID, process_id: str, user: CurrentUser, db: Db, rev: Rev = None
) -> Response:
    """BPMN of a process node, compiled from its DSL by dsl/bpmn_compile.py (LLM writes no XML)."""
    from reqgraph.dsl.bpmn_compile import compile_bpmn

    async with db.as_user(user) as conn:
        row = await repo.graph(conn, project_id, rev)
    if row is None:
        raise HTTPException(404, NOT_FOUND if rev is None else f"нет ревизии {rev}")
    node = (row["graph"].get("nodes") or {}).get(process_id)
    if not node or node.get("kind") != "PRC" or not node.get("dsl"):
        raise HTTPException(404, f"нет процесса {process_id}")
    try:
        xml = compile_bpmn(parse_process(node["dsl"]))
    except DslError as exc:
        raise HTTPException(422, str(exc)) from None
    return Response(xml, media_type="application/xml")


@router.post("/{project_id}/exports", response_model=list[ExportOut])
async def make_exports(
    project_id: UUID, user: CurrentUser, db: Db, request: Request, rev: Rev = None
) -> list[ExportOut]:
    """SRS, TZ by GOST 34 and 19 (md, docx), scheme pictures and ReqIF of a revision into the
    Storage bucket exports. A revision is exported once: a repeated call returns its files."""
    storage: Storage | None = request.app.state.storage
    if storage is None:
        raise HTTPException(503, "хранилище файлов не настроено: SUPABASE_URL и ключ сервера")
    locks: dict[UUID, asyncio.Lock] = request.app.state.export_locks
    async with locks.setdefault(project_id, asyncio.Lock()):
        async with db.as_user(user) as conn:
            if await repo.get_project(conn, project_id) is None:
                raise HTTPException(404, NOT_FOUND)
            try:
                project, at = await store.load(conn, project_id, rev)
            except store.ProjectNotFound:
                raise HTTPException(404, f"нет ревизии {rev}") from None
            done = await repo.exports(conn, project_id, at)
        if done:
            return [ExportOut.model_validate(r) for r in done]
        offline = request.app.state.settings.export_offline
        try:
            files = await exporting.export_revision(
                project, project_id, at, storage, offline=offline
            )
        except StorageError as exc:
            raise HTTPException(502, str(exc)) from None
        except Exception as exc:  # pandoc, Kroki: the user sees why, the log has the trace
            log.exception("export of %s rev %s failed", project_id, at)
            raise HTTPException(502, f"выгрузка не собрана: {exc}") from None
        async with db.as_user(user) as conn:
            await elevate(conn)
            rows = await repo.add_exports(conn, project_id, at, files)
    return [ExportOut.model_validate(r) for r in rows]
