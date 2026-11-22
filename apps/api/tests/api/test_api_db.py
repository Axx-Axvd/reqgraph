"""Projects, runs, answers, the graph and PgStore on a database with the migrations (T-501)."""

from collections.abc import Callable
from uuid import UUID, uuid4

import psycopg
import pytest
from httpx import AsyncClient
from reqgraph.dsl.readers import model_readers
from reqgraph.graph.store.file_store import FileStore
from reqgraph_api import store
from reqgraph_api.db import Database, elevate

from .conftest import ROOT, Token

pytestmark = [pytest.mark.pg, pytest.mark.anyio]


def auth(token: Token, user: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(user)}"}


def sql(database_url: str, query: str, params: list[object]) -> None:
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(query, params)


async def new_project(client: AsyncClient, headers: dict[str, str], brief: str = "Бриф.") -> str:
    response = await client.post(
        "/projects", json={"name": "Клиника", "brief": brief}, headers=headers
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def test_a_user_sees_only_own_projects(
    client: AsyncClient, token: Token, new_user: Callable[[], UUID]
) -> None:
    alice, bob = new_user(), new_user()
    pid = await new_project(client, auth(token, alice))
    mine = (await client.get("/projects", headers=auth(token, alice))).json()
    assert [p["id"] for p in mine] == [pid] and mine[0]["head_rev"] == 0
    assert (await client.get("/projects", headers=auth(token, bob))).json() == []
    assert (await client.get(f"/projects/{pid}", headers=auth(token, bob))).status_code == 404
    graph = (await client.get(f"/projects/{pid}/graph", headers=auth(token, alice))).json()
    assert graph["rev"] == 0 and graph["author"] == "user" and graph["graph"]["nodes"] == {}
    assert (await client.get(f"/projects/{pid}/graph", headers=auth(token, bob))).status_code == 404
    missing = await client.get(f"/projects/{pid}/graph?rev=5", headers=auth(token, alice))
    assert missing.status_code == 404 and "5" in missing.json()["detail"]
    assert (await client.get(f"/projects/{pid}/exports", headers=auth(token, alice))).json() == []
    assert (
        await client.get(f"/projects/{pid}/exports", headers=auth(token, bob))
    ).status_code == 404


async def test_a_run_is_queued_with_its_start_job(
    client: AsyncClient, token: Token, new_user: Callable[[], UUID], database_url: str
) -> None:
    alice, bob = new_user(), new_user()
    pid = await new_project(client, auth(token, alice))
    body = {"kind": "interview", "max_turns": 12, "client_level": 0}
    assert (
        await client.post(f"/projects/{pid}/runs", json=body, headers=auth(token, bob))
    ).status_code == 404
    made = (
        await client.post(f"/projects/{pid}/runs", json=body, headers=auth(token, alice))
    ).json()
    run, job = made["run"], made["job"]
    assert run["status"] == "queued" and run["kind"] == "interview"
    assert job["kind"] == "start" and job["status"] == "queued" and job["run_id"] == run["id"]
    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            "select config, model_profile from runs where id = %s", [run["id"]]
        ).fetchone()
    assert row == ({"max_turns": 12, "client_level": 0}, "free")
    wrong = {"kind": "interview", "client_level": 4}
    assert (
        await client.post(f"/projects/{pid}/runs", json=wrong, headers=auth(token, alice))
    ).status_code == 422
    assert (await client.get(f"/runs/{run['id']}", headers=auth(token, bob))).status_code == 404
    assert (await client.get(f"/runs/{run['id']}", headers=auth(token, alice))).json()["id"] == run[
        "id"
    ]


async def test_an_answer_is_taken_only_while_the_run_waits_and_only_once(
    client: AsyncClient, token: Token, new_user: Callable[[], UUID], database_url: str
) -> None:
    alice = new_user()
    headers = auth(token, alice)
    pid = await new_project(client, headers)
    run = (
        await client.post(f"/projects/{pid}/runs", json={"kind": "interview"}, headers=headers)
    ).json()["run"]
    url = f"/runs/{run['id']}/answer"
    early = await client.post(
        url, json={"text": "Пациенты записываются по телефону."}, headers=headers
    )
    assert early.status_code == 409 and "queued" in early.json()["detail"]
    sql(database_url, "update runs set status = 'waiting_input' where id = %s", [run["id"]])
    for both in ({"text": "x", "done": True}, {"done": True, "simpler": True}, {}):
        assert (await client.post(url, json=both, headers=headers)).status_code == 422
    taken = await client.post(
        url, json={"text": "Пациенты записываются по телефону."}, headers=headers
    )
    assert taken.status_code == 202 and taken.json()["kind"] == "resume"
    again = await client.post(url, json={"done": True}, headers=headers)
    assert again.status_code == 409 and "running" in again.json()["detail"]
    status = (await client.get(f"/runs/{run['id']}", headers=headers)).json()["status"]
    assert status == "running"  # the answer is taken: the chat hides the form at once (T-504)
    with psycopg.connect(database_url) as conn:
        payload = conn.execute(
            "select payload from jobs where run_id = %s and kind = 'resume'", [run["id"]]
        ).fetchone()
    assert payload == ({"answer": "Пациенты записываются по телефону."},)


async def test_cancel_and_events(
    client: AsyncClient, token: Token, new_user: Callable[[], UUID], database_url: str
) -> None:
    alice, bob = new_user(), new_user()
    headers = auth(token, alice)
    pid = await new_project(client, headers)
    run = (
        await client.post(f"/projects/{pid}/runs", json={"kind": "brief"}, headers=headers)
    ).json()["run"]
    for kind in ("run_start", "question", "answer"):
        sql(
            database_url,
            "insert into run_events (run_id, type, payload) values (%s, %s, '{}')",
            [run["id"], kind],
        )
    events = (await client.get(f"/runs/{run['id']}/events", headers=headers)).json()
    assert [e["type"] for e in events] == ["run_start", "question", "answer"]
    later = await client.get(f"/runs/{run['id']}/events?after={events[0]['id']}", headers=headers)
    assert [e["type"] for e in later.json()] == ["question", "answer"]
    assert (
        await client.get(f"/runs/{run['id']}/events", headers=auth(token, bob))
    ).status_code == 404
    assert (
        await client.post(f"/runs/{run['id']}/cancel", headers=auth(token, bob))
    ).status_code == 404
    cancelled = await client.post(f"/runs/{run['id']}/cancel", headers=headers)
    assert cancelled.status_code == 202 and cancelled.json()["kind"] == "cancel"
    sql(database_url, "update runs set status = 'succeeded' where id = %s", [run["id"]])
    assert (await client.post(f"/runs/{run['id']}/cancel", headers=headers)).status_code == 409


async def test_users_see_no_jobs(
    client: AsyncClient, token: Token, new_user: Callable[[], UUID], database: Database
) -> None:
    from reqgraph_api.auth import User

    alice = new_user()
    pid = await new_project(client, auth(token, alice))
    await client.post(f"/projects/{pid}/runs", json={"kind": "brief"}, headers=auth(token, alice))
    async with database.as_user(User(id=alice)) as conn:
        assert await (await conn.execute("select * from jobs")).fetchall() == []


async def test_pgstore_keeps_the_reference_project_whole(
    client: AsyncClient, token: Token, new_user: Callable[[], UUID], database: Database
) -> None:
    from reqgraph_api.auth import User

    folder = FileStore(ROOT / "examples" / "garage61", readers=model_readers()).load()
    alice = new_user()
    pid = UUID(await new_project(client, auth(token, alice)))
    async with database.as_user(User(id=alice)) as conn:
        await elevate(conn)
        rev = await store.save(conn, pid, folder, "agent")
    async with database.as_user(User(id=alice)) as conn:
        loaded, at = await store.load(conn, pid)
        first, _ = await store.load(conn, pid, rev=0)
    assert (rev, at) == (1, 1)
    assert (
        loaded.graph == folder.graph
    )  # jsonb keeps no key order inside a node: equal, not same text
    assert loaded.files == folder.files and loaded.layout == folder.layout
    assert loaded.config == folder.config
    assert first.files == {"brief.md": "Бриф."} and not first.graph.nodes
    graph = (await client.get(f"/projects/{pid}/graph", headers=auth(token, alice))).json()
    assert graph["rev"] == 1 and len(graph["graph"]["nodes"]) == len(folder.graph.nodes)
    async with database.as_user(User(id=new_user())) as conn:
        with pytest.raises(store.ProjectNotFound):
            await store.load(conn, pid)  # RLS: another user does not see it


def test_project_ids_are_unique() -> None:
    from reqgraph_api.repo import new_config

    a, b = uuid4(), uuid4()
    assert (
        new_config("Клиника «Улыбка»", a).project.id != new_config("Клиника «Улыбка»", b).project.id
    )
    assert new_config("Garage 61", a).project.id.startswith("garage-61-")
