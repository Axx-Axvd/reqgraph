"""The worker on stub models (T-502): the queue, an interview through the API, a run that goes on
after its process died, cancel and retries. No network, no money."""

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import UUID

import psycopg
import pytest
from httpx import AsyncClient
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from reqgraph_api.db import Database
from reqgraph_api.worker import queue
from reqgraph_api.worker.loop import run_once
from reqgraph_api.worker.runner import Runner

from .conftest import Token

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

QUESTION = "Как пациенты записываются сейчас?"
SRS = {
    "purpose": "Онлайн-запись в клинику.",
    "scope": "Запись и напоминания.",
    "perspective": "Новая система.",
    "glossary": [{"term": "Запись", "definition": "время у врача"}],
}
BRIEF = "Стоматологическая клиника, 3 кресла. Пациенты записываются по телефону."
STALE = 60


def stub_models(**overrides: Model) -> dict[str, Model]:
    """Every agent answers an empty draft, the interviewer asks QUESTION (as in the core tests)."""
    models: dict[str, Model] = {
        "*": TestModel(custom_output_args={"ops": []}),
        "interviewer": TestModel(custom_output_args={"text": QUESTION}),
        "modeler_views": TestModel(custom_output_args={}),
        "standards": TestModel(custom_output_args=SRS),
    }
    return models | overrides


class Gate:
    """A model whose first call hangs (a process that dies or a step that is cancelled there);
    later calls answer an empty draft. `entered` tells the test the call has started."""

    def __init__(self) -> None:
        self.calls = 0
        self.entered = asyncio.Event()

    def model(self) -> FunctionModel:
        async def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            self.calls += 1
            if self.calls == 1:
                self.entered.set()
                await asyncio.Event().wait()
            return ModelResponse(parts=[TextPart('{"ops": []}')])

        return FunctionModel(fn)


class Counter:
    def __init__(self, fail: bool = False) -> None:
        self.calls, self.fail = 0, fail

    def model(self) -> FunctionModel:
        def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            self.calls += 1
            if self.fail:
                raise RuntimeError("провайдер недоступен")
            return ModelResponse(parts=[TextPart('{"ops": []}')])

        return FunctionModel(fn)


@pytest.fixture(autouse=True)
def empty_queue(database_url: str) -> None:
    """Jobs left by other tests in the shared database are not this test's: close them."""
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("update jobs set status = 'done' where status in ('queued', 'running')")


@pytest.fixture
async def make_runner(
    database: Database, database_url: str
) -> AsyncIterator[Callable[..., Runner]]:
    def make(**models: Model) -> Runner:
        options = {"models": stub_models(**models), "offline": True, "max_iter": 0}
        return Runner(database, database_url, options=options, poll=0.05)

    await make().setup()
    yield make


def auth(token: Token, user: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(user)}"}


async def start(client: AsyncClient, headers: dict[str, str], kind: str, **run: Any) -> str:
    project = await client.post(
        "/projects", json={"name": "Клиника", "brief": BRIEF}, headers=headers
    )
    pid = project.json()["id"]
    made = await client.post(f"/projects/{pid}/runs", json={"kind": kind, **run}, headers=headers)
    return str(made.json()["run"]["id"])


def rows(database_url: str, query: str, params: list[object]) -> list[tuple[Any, ...]]:
    with psycopg.connect(database_url) as conn:
        return conn.execute(query, params).fetchall()


async def test_an_interview_through_the_api_ends_in_a_new_graph_revision(
    client: AsyncClient,
    token: Token,
    new_user: Callable[[], UUID],
    make_runner: Callable[..., Runner],
    database: Database,
    database_url: str,
) -> None:
    headers = auth(token, new_user())
    run_id = await start(client, headers, "interview", max_turns=3)
    runner = make_runner()
    assert await run_once(database, runner, STALE)
    run = (await client.get(f"/runs/{run_id}", headers=headers)).json()
    assert run["status"] == "waiting_input" and run["started_at"]
    answer = await client.post(
        f"/runs/{run_id}/answer", json={"text": "По телефону."}, headers=headers
    )
    assert answer.status_code == 202
    assert await run_once(database, runner, STALE)
    assert (await client.get(f"/runs/{run_id}", headers=headers)).json()[
        "status"
    ] == "waiting_input"
    await client.post(f"/runs/{run_id}/answer", json={"done": True}, headers=headers)
    assert await run_once(database, runner, STALE)
    assert not await run_once(database, runner, STALE)  # the queue is empty
    run = (await client.get(f"/runs/{run_id}", headers=headers)).json()
    assert run["status"] == "succeeded" and run["finished_at"] and run["error"] is None
    turns = rows(
        database_url,
        "select role, content from interview_turns where run_id = %s order by id",
        [run_id],
    )
    assert turns == [("agent", QUESTION), ("client", "По телефону."), ("agent", QUESTION)]
    pid = run["project_id"]
    graph = (await client.get(f"/projects/{pid}/graph", headers=headers)).json()
    assert graph["rev"] == 1 and graph["author"] == "agent"
    assert graph["ci_summary"]["run_id"] == run_id and "headline" in graph["ci_summary"]
    assert "TURN-0001" in graph["graph"]["nodes"]  # the brief and the dialog are in the graph
    events = (await client.get(f"/runs/{run_id}/events", headers=headers)).json()
    kinds = [e["type"] for e in events]
    assert {"run_start", "question", "answer", "run_end"} <= set(kinds) and kinds[-1] == "run_end"
    assert [e["id"] for e in events] == sorted(e["id"] for e in events)


async def test_a_brief_run_goes_through_without_pauses(
    client: AsyncClient,
    token: Token,
    new_user: Callable[[], UUID],
    make_runner: Callable[..., Runner],
    database: Database,
) -> None:
    headers = auth(token, new_user())
    run_id = await start(client, headers, "brief")
    assert await run_once(database, make_runner(), STALE)
    run = (await client.get(f"/runs/{run_id}", headers=headers)).json()
    assert run["status"] == "succeeded"
    graph = (await client.get(f"/projects/{run['project_id']}/graph", headers=headers)).json()
    assert graph["rev"] == 1 and graph["ci_summary"]["stop"] in (None, "needs_human")


async def test_a_run_abandoned_mid_step_goes_on_from_its_checkpoint(
    client: AsyncClient,
    token: Token,
    new_user: Callable[[], UUID],
    make_runner: Callable[..., Runner],
    database: Database,
    database_url: str,
) -> None:
    """The process dies in the Modeler: the next worker takes the job again and does not call the
    Analyst a second time — its step is in the checkpoint."""
    headers = auth(token, new_user())
    run_id = await start(client, headers, "brief")
    analyst, modeler = Counter(), Gate()
    runner = make_runner(analyst=analyst.model(), modeler=modeler.model())
    task = asyncio.create_task(run_once(database, runner, STALE))
    await asyncio.wait_for(modeler.entered.wait(), 10)
    task.cancel()  # the process is gone: no error, no finish — the job stays «running»
    with pytest.raises(asyncio.CancelledError):
        await task
    assert rows(database_url, "select status from jobs where run_id = %s", [run_id]) == [
        ("running",)
    ]
    assert not await run_once(database, runner, STALE)  # still locked: nobody takes it yet
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(
            "update jobs set locked_at = now() - interval '10 minutes' where run_id = %s", [run_id]
        )
    assert await run_once(database, runner, STALE)
    assert analyst.calls == 1 and modeler.calls == 2
    assert rows(database_url, "select status, attempts from jobs where run_id = %s", [run_id]) == [
        ("done", 2)
    ]
    assert (await client.get(f"/runs/{run_id}", headers=headers)).json()["status"] == "succeeded"


async def test_a_failing_run_is_retried_then_fails_with_the_reason(
    client: AsyncClient,
    token: Token,
    new_user: Callable[[], UUID],
    make_runner: Callable[..., Runner],
    database: Database,
) -> None:
    headers = auth(token, new_user())
    run_id = await start(client, headers, "brief")
    analyst = Counter(fail=True)
    runner = make_runner(analyst=analyst.model())
    for _ in range(queue.MAX_ATTEMPTS):
        assert await run_once(database, runner, STALE)
    assert not await run_once(database, runner, STALE)
    run = (await client.get(f"/runs/{run_id}", headers=headers)).json()
    assert run["status"] == "failed" and "провайдер недоступен" in run["error"]


async def test_the_queue_takes_one_job_of_a_run_at_a_time_and_skips_locked_jobs(
    client: AsyncClient,
    token: Token,
    new_user: Callable[[], UUID],
    database: Database,
    database_url: str,
) -> None:
    headers = auth(token, new_user())
    first, second = await start(client, headers, "brief"), await start(client, headers, "brief")
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("insert into jobs (run_id, kind) values (%s, 'cancel')", [first])
    mine = {UUID(first), UUID(second)}
    async with database.as_service() as one:
        taken = await queue.claim(one, STALE)
        assert taken is not None
        async with database.as_service() as two:  # another worker while the first holds its lock
            other = await queue.claim(two, STALE)
            assert other is not None and other["id"] != taken["id"]
        async with database.as_service() as three:
            later = await queue.claim(three, STALE)
            # the cancel of `first` waits for its start job, which is running
            assert later is None or later["run_id"] not in mine


async def test_cancel_a_waiting_and_a_running_run(
    client: AsyncClient,
    token: Token,
    new_user: Callable[[], UUID],
    make_runner: Callable[..., Runner],
    database: Database,
) -> None:
    headers = auth(token, new_user())
    waiting = await start(client, headers, "interview")
    runner = make_runner()
    assert await run_once(database, runner, STALE)
    assert (await client.post(f"/runs/{waiting}/cancel", headers=headers)).status_code == 202
    assert await run_once(database, runner, STALE)
    assert (await client.get(f"/runs/{waiting}", headers=headers)).json()["status"] == "cancelled"
    late = await client.post(f"/runs/{waiting}/answer", json={"text": "Поздно."}, headers=headers)
    assert late.status_code == 409

    running = await start(client, headers, "brief")
    analyst = Gate()
    busy = make_runner(analyst=analyst.model())
    task = asyncio.create_task(run_once(database, busy, STALE))
    await asyncio.wait_for(analyst.entered.wait(), 10)
    assert (await client.get(f"/runs/{running}", headers=headers)).json()["status"] == "running"
    assert (await client.post(f"/runs/{running}/cancel", headers=headers)).status_code == 202
    assert await asyncio.wait_for(task, 10)
    assert (await client.get(f"/runs/{running}", headers=headers)).json()["status"] == "cancelled"
    assert not await run_once(database, busy, STALE)  # the cancel job is done as well
