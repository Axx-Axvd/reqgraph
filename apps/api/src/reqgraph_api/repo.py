"""SQL of the API. Reads run under the user's role (RLS); a write first finds the row under RLS,
then elevates to the backend role for tables users cannot write (runs, jobs, revisions)."""

import re
from typing import Any
from uuid import UUID, uuid4

from psycopg.rows import DictRow
from psycopg.types.json import Jsonb
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.store.config import ModelsConfig, ProjectConfig, ProjectInfo
from reqgraph.graph.store.project import Project

from reqgraph_api import store
from reqgraph_api.db import Conn, elevate

BRIEF_FILE = "brief.md"  # as in a FileStore folder (reqgraph init)
STANDARDS: list[Any] = ["iso29148", "gost34_602"]
PROJECT = "id, name, head_rev, standards, created_at"
RUN = (
    "id, project_id, kind, status, iteration, cost_usd::float as cost_usd, error, byok, "
    "created_at, "
    "started_at, finished_at"
)
JOB = "id, run_id, kind, status, created_at"
FINISHED = ("succeeded", "failed", "cancelled")


class Conflict(Exception):
    """The request does not fit the run's state (409); the message is for the user."""


async def _one(conn: Conn, query: str, params: list[Any]) -> DictRow | None:
    return await (await conn.execute(query, params)).fetchone()


async def list_projects(conn: Conn) -> list[DictRow]:
    cur = await conn.execute(f"select {PROJECT} from public.projects order by created_at desc")
    return await cur.fetchall()


async def get_project(conn: Conn, project_id: UUID) -> DictRow | None:
    return await _one(conn, f"select {PROJECT} from public.projects where id = %s", [project_id])


def new_config(name: str, project_id: UUID, profile: str = "free") -> ProjectConfig:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "project"
    info = ProjectInfo(id=f"{slug}-{project_id.hex[:6]}", name=name, standards=STANDARDS)
    return ProjectConfig(project=info, models=ModelsConfig.model_validate({"profile": profile}))


async def create_project(
    conn: Conn, owner: UUID, name: str, brief: str | None, profile: str = "free"
) -> DictRow:
    """The project (under RLS: owner_id must be the user) and its revision 0 — an empty graph
    and the brief as brief.md."""
    project_id = uuid4()
    config = new_config(name, project_id, profile)
    row = await _one(
        conn,
        f"insert into public.projects (id, owner_id, name, standards, config) "
        f"values (%s, %s, %s, %s, %s) returning {PROJECT}",
        [project_id, owner, name, STANDARDS, Jsonb(config.model_dump(mode="json"))],
    )
    assert row is not None
    files = {BRIEF_FILE: brief} if brief else {}
    project = Project(
        root=store.project_root(project_id), config=config, graph=ArtifactGraph.empty(), files=files
    )
    await elevate(conn)
    await conn.execute(
        "insert into public.graph_revisions (project_id, rev, graph, files, layout, author) "
        "values (%s, 0, %s, %s, '{}', 'user')",
        [project_id, store.graph_json(project.graph), Jsonb(project.files)],
    )
    return row


async def project_config(conn: Conn, project_id: UUID) -> ProjectConfig | None:
    """The project's settings under RLS; None — no such project of the user."""
    row = await _one(conn, "select config from public.projects where id = %s", [project_id])
    return None if row is None else ProjectConfig.model_validate(row["config"])


async def create_run(
    conn: Conn,
    project_id: UUID,
    config: ProjectConfig,
    kind: str,
    brief: str | None,
    max_turns: int | None,
    *,
    profile: str,
    byok: bool,
) -> tuple[DictRow, DictRow]:
    """A queued run and its start job, in the backend role (after limits.admit)."""
    settings = {"max_turns": max_turns or config.interview.max_turns}
    payload: dict[str, Any] = {"brief": brief} if brief else {}
    await elevate(conn)
    run = await _one(
        conn,
        f"insert into public.runs (project_id, kind, model_profile, config, byok) "
        f"values (%s, %s, %s, %s, %s) returning {RUN}",
        [project_id, kind, profile, Jsonb(settings), byok],
    )
    assert run is not None
    job = await _one(
        conn,
        f"insert into public.jobs (run_id, kind, payload) values (%s, 'start', %s) returning {JOB}",
        [run["id"], Jsonb(payload)],
    )
    assert job is not None
    return run, job


async def get_run(conn: Conn, run_id: UUID) -> DictRow | None:
    return await _one(conn, f"select {RUN} from public.runs where id = %s", [run_id])


async def events(conn: Conn, run_id: UUID, after: int, limit: int) -> list[DictRow]:
    cur = await conn.execute(
        "select id, type, payload, ts from public.run_events "
        "where run_id = %s and id > %s order by id limit %s",
        [run_id, after, limit],
    )
    return await cur.fetchall()


async def _job(conn: Conn, run_id: UUID, kind: str, payload: dict[str, Any]) -> DictRow:
    await elevate(conn)
    job = await _one(
        conn,
        f"insert into public.jobs (run_id, kind, payload) values (%s, %s, %s) returning {JOB}",
        [run_id, kind, Jsonb(payload)],
    )
    assert job is not None
    return job


async def answer(conn: Conn, run: DictRow, text: str | None, done: bool) -> DictRow:
    """The answer to the waiting question as a resume job (the worker resumes the graph with it;
    the text is data for the Analyst, never an instruction)."""
    if run["status"] != "waiting_input":
        raise Conflict(f"прогон не ждёт ответа (статус {run['status']})")
    await elevate(conn)
    pending = await _one(
        conn,
        "select 1 from public.jobs where run_id = %s and kind = 'resume' and status = 'queued'",
        [run["id"]],
    )
    if pending is not None:
        raise Conflict("ответ на этот вопрос уже принят")
    job = await _job(conn, run["id"], "resume", {"done": True} if done else {"answer": text})
    # the answer is taken: the run works again (T-504: the chat hides the form at once; the worker
    # sets waiting_input at the next question)
    await conn.execute(
        "update public.runs set status = 'running' where id = %s and status = 'waiting_input'",
        [run["id"]],
    )
    return job


async def cancel(conn: Conn, run: DictRow) -> DictRow:
    if run["status"] in FINISHED:
        raise Conflict(f"прогон уже завершён (статус {run['status']})")
    return await _job(conn, run["id"], "cancel", {})


async def graph(conn: Conn, project_id: UUID, rev: int | None) -> DictRow | None:
    query = (
        "select project_id, rev, graph, ci_summary, author, created_at "
        "from public.graph_revisions where project_id = %s "
        + ("and rev = %s" if rev is not None else "order by rev desc limit 1")
    )
    return await _one(conn, query, [project_id] if rev is None else [project_id, rev])


EXPORT = (
    "id, rev, format, storage_path as path, "
    "regexp_replace(storage_path, '^[^/]+/[^/]+/', '') as name, created_at"
)


async def exports(conn: Conn, project_id: UUID, rev: int | None = None) -> list[DictRow]:
    """Files of the project's exports, the latest revision first; of one revision if given."""
    cur = await conn.execute(
        f"select {EXPORT} from public.exports where project_id = %s "
        + ("and rev = %s " if rev is not None else "")
        + "order by rev desc, storage_path",
        [project_id] if rev is None else [project_id, rev],
    )
    return await cur.fetchall()


async def add_exports(
    conn: Conn, project_id: UUID, rev: int, files: list[tuple[str, str]]
) -> list[DictRow]:
    """Rows for the uploaded files (format, storage path); call after elevate()."""
    for fmt, path in files:
        await conn.execute(
            "insert into public.exports (project_id, rev, format, storage_path) "
            "values (%s, %s, %s, %s) on conflict (project_id, rev, storage_path) do nothing",
            [project_id, rev, fmt, path],
        )
    return await exports(conn, project_id, rev)


async def ci_report(conn: Conn, project_id: UUID, rev: int | None) -> DictRow | None:
    query = "select rev, ci_report from public.graph_revisions where project_id = %s " + (
        "and rev = %s" if rev is not None else "order by rev desc limit 1"
    )
    return await _one(conn, query, [project_id] if rev is None else [project_id, rev])


async def save_ci_report(conn: Conn, project_id: UUID, rev: int, report: dict[str, Any]) -> None:
    """Keep a report computed on request; call after elevate()."""
    await conn.execute(
        "update public.graph_revisions set ci_report = %s where project_id = %s and rev = %s",
        [Jsonb(report), project_id, rev],
    )
