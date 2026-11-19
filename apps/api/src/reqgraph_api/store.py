"""PgStore: a project in Postgres — the same Project as FileStore keeps in a folder.

projects.config holds reqgraph.yaml, every save is a new row of graph_revisions (graph, the
model files as read, the node -> file layout) and moves projects.head_rev. The graph itself
changes only through GraphPatch -> ArtifactGraph.apply() in the core; this only stores it.
"""

import json
from pathlib import Path
from typing import Literal
from uuid import UUID

from psycopg.types.json import Jsonb
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.store.config import ProjectConfig
from reqgraph.graph.store.project import Project

from reqgraph_api.db import Conn

Author = Literal["agent", "user"]


class ProjectNotFound(LookupError):
    pass


def project_root(project_id: UUID) -> Path:
    """A stand-in for the folder of a FileStore project: nothing is read from it."""
    return Path("projects") / str(project_id)


async def load(conn: Conn, project_id: UUID, rev: int | None = None) -> tuple[Project, int]:
    """The project at a revision (the latest by default) and that revision's number."""
    project = await (
        await conn.execute("select config from public.projects where id = %s", [project_id])
    ).fetchone()
    if project is None:
        raise ProjectNotFound(str(project_id))
    query = (
        "select rev, graph, files, layout from public.graph_revisions where project_id = %s "
        + ("and rev = %s" if rev is not None else "order by rev desc limit 1")
    )
    params: list[object] = [project_id] if rev is None else [project_id, rev]
    row = await (await conn.execute(query, params)).fetchone()
    if row is None:
        raise ProjectNotFound(f"{project_id} rev {rev}")
    graph = (
        ArtifactGraph.from_json(json.dumps(row["graph"])) if row["graph"] else ArtifactGraph.empty()
    )
    loaded = Project(
        root=project_root(project_id),
        config=ProjectConfig.model_validate(project["config"]),
        graph=graph,
        files=dict(row["files"]),
        layout=dict(row["layout"]),
    )
    return loaded, int(row["rev"])


def graph_json(graph: ArtifactGraph) -> Jsonb:
    """The graph as ArtifactGraph.to_json() writes it (same keys and order checks on load)."""
    return Jsonb(json.loads(graph.to_json()))


async def save(conn: Conn, project_id: UUID, project: Project, author: Author) -> int:
    """A new revision head_rev + 1 with the project's graph, files and layout; the config too.
    Run as the backend (db.elevate): users have no insert policy on graph_revisions."""
    row = await (
        await conn.execute(
            "update public.projects set head_rev = head_rev + 1, config = %s "
            "where id = %s returning head_rev",
            [Jsonb(project.config.model_dump(mode="json")), project_id],
        )
    ).fetchone()
    if row is None:
        raise ProjectNotFound(str(project_id))
    rev = int(row["head_rev"])
    await conn.execute(
        "insert into public.graph_revisions (project_id, rev, graph, files, layout, author) "
        "values (%s, %s, %s, %s, %s, %s)",
        [
            project_id,
            rev,
            graph_json(project.graph),
            Jsonb(project.files),
            Jsonb(project.layout),
            author,
        ],
    )
    return rev
