"""T-505 on a database: the CI report, BPMN of a process and the export of a revision."""

from collections.abc import AsyncIterator, Callable
from uuid import UUID

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from reqgraph.checks.report import CIReport
from reqgraph.dsl.bpmn_compile import compile_bpmn
from reqgraph.dsl.process import parse_process
from reqgraph.dsl.readers import model_readers
from reqgraph.graph.nodes import ProcessNode
from reqgraph.graph.store.file_store import FileStore
from reqgraph_api import store
from reqgraph_api.app import create_app
from reqgraph_api.auth import TokenVerifier, User
from reqgraph_api.db import Database, elevate
from reqgraph_api.settings import Settings

from .conftest import ROOT, Token
from .test_api_db import auth, new_project

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
GARAGE = ROOT / "examples" / "garage61"


class FakeStorage:
    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, str]] = {}

    async def upload(self, path: str, data: bytes, content_type: str) -> None:
        self.files[path] = (data, content_type)

    async def remove(self, paths: list[str]) -> None:
        for path in paths:
            self.files.pop(path, None)


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
async def app_client(
    database: Database, verifier: TokenVerifier, storage: FakeStorage
) -> AsyncIterator[AsyncClient]:
    settings = Settings(export_offline=True)
    app = create_app(settings, database=database, verifier=verifier, storage=storage)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def garage(client: AsyncClient, token: Token, database: Database, user: UUID) -> UUID:
    """A project whose revision 1 is the reference project garage61."""
    pid = UUID(await new_project(client, auth(token, user)))
    async with database.as_user(User(id=user)) as conn:
        await elevate(conn)
        await store.save(conn, pid, FileStore(GARAGE, readers=model_readers()).load(), "agent")
    return pid


async def test_the_report_is_computed_once_and_kept(
    app_client: AsyncClient,
    token: Token,
    new_user: Callable[[], UUID],
    database: Database,
    database_url: str,
) -> None:
    alice = new_user()
    pid = await garage(app_client, token, database, alice)
    response = await app_client.get(f"/projects/{pid}/report", headers=auth(token, alice))
    assert response.status_code == 200, response.text
    report = CIReport.model_validate(response.json())
    assert report.checks and report.summary.errors == 0  # the reference project is clean
    with psycopg.connect(database_url) as conn:
        kept = conn.execute(
            "select ci_report from graph_revisions where project_id = %s and rev = 1", [pid]
        ).fetchone()
    assert kept is not None and CIReport.model_validate(kept[0]) == report
    other = await app_client.get(f"/projects/{pid}/report", headers=auth(token, new_user()))
    assert other.status_code == 404
    missing = await app_client.get(f"/projects/{pid}/report?rev=7", headers=auth(token, alice))
    assert missing.status_code == 404


async def test_a_kept_report_is_returned_as_is(
    app_client: AsyncClient,
    token: Token,
    new_user: Callable[[], UUID],
    database: Database,
    database_url: str,
) -> None:
    alice = new_user()
    pid = await garage(app_client, token, database, alice)
    first = (await app_client.get(f"/projects/{pid}/report", headers=auth(token, alice))).json()
    first["findings"] = [
        {
            "check_id": "TRC-001",
            "severity": "error",
            "node_ids": ["FR-001"],
            "message": "нет связи",
            "owner": "analyst",
        }
    ]
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(
            "update graph_revisions set ci_report = %s where project_id = %s and rev = 1",
            [psycopg.types.json.Jsonb(first), pid],
        )
    again = (await app_client.get(f"/projects/{pid}/report", headers=auth(token, alice))).json()
    assert again["findings"][0]["node_ids"] == ["FR-001"]


async def test_bpmn_is_compiled_from_the_process_dsl(
    app_client: AsyncClient, token: Token, new_user: Callable[[], UUID], database: Database
) -> None:
    alice = new_user()
    pid = await garage(app_client, token, database, alice)
    response = await app_client.get(
        f"/projects/{pid}/processes/PRC-01/bpmn", headers=auth(token, alice)
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/xml")
    process = FileStore(GARAGE, readers=model_readers()).load().graph.nodes["PRC-01"]
    assert isinstance(process, ProcessNode) and process.dsl
    assert response.text == compile_bpmn(parse_process(process.dsl))
    for path, user in [("PRC-99", alice), ("FR-001", alice), ("PRC-01", new_user())]:
        response = await app_client.get(
            f"/projects/{pid}/processes/{path}/bpmn", headers=auth(token, user)
        )
        assert response.status_code == 404, path


async def test_an_export_uploads_files_once_per_revision(
    app_client: AsyncClient,
    token: Token,
    new_user: Callable[[], UUID],
    database: Database,
    storage: FakeStorage,
) -> None:
    alice = new_user()
    pid = await garage(app_client, token, database, alice)
    response = await app_client.post(f"/projects/{pid}/exports", headers=auth(token, alice))
    assert response.status_code == 200, response.text
    files = response.json()
    names = {f["name"] for f in files}
    assert {"srs.md", "srs.docx", "req.reqif"} <= names
    assert all(f["rev"] == 1 and f["path"] == f"{pid}/1/{f['name']}" for f in files)
    assert set(storage.files) == {f["path"] for f in files}
    assert {f["format"] for f in files} >= {"md", "docx", "reqif"}
    uploads = len(storage.files)
    storage.files.clear()
    again = await app_client.post(f"/projects/{pid}/exports", headers=auth(token, alice))
    assert [f["id"] for f in again.json()] == [f["id"] for f in files] and not storage.files
    listed = (await app_client.get(f"/projects/{pid}/exports", headers=auth(token, alice))).json()
    assert len(listed) == uploads
    other = await app_client.post(f"/projects/{pid}/exports", headers=auth(token, new_user()))
    assert other.status_code == 404


async def test_without_storage_an_export_is_503(
    client: AsyncClient, token: Token, new_user: Callable[[], UUID]
) -> None:
    alice = new_user()
    pid = await new_project(client, auth(token, alice))
    response = await client.post(f"/projects/{pid}/exports", headers=auth(token, alice))
    assert response.status_code == 503 and "SUPABASE_URL" in response.json()["detail"]
