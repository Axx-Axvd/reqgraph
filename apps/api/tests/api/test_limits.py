"""Demo limits and the user's own key (T-503): 3 runs a day, the daily cap, admins, BYOK."""

import asyncio
from collections.abc import Callable
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg
import pytest
from httpx import AsyncClient
from reqgraph_api.limits import seconds_to_midnight

from .conftest import Token

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

KEY = "sk-or-test-own-key-1234567890"


def auth(token: Token, user: UUID, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(user)}", **extra}


def sql(database_url: str, query: str, params: list[object]) -> list[tuple[object, ...]]:
    with psycopg.connect(database_url, autocommit=True) as conn:
        cur = conn.execute(query, params)
        return cur.fetchall() if cur.description else []


async def project(client: AsyncClient, headers: dict[str, str]) -> str:
    made = await client.post(
        "/projects", json={"name": "Клиника", "brief": "Бриф."}, headers=headers
    )
    return str(made.json()["id"])


async def test_the_fourth_run_of_the_day_is_429_with_a_clear_text(
    client: AsyncClient, token: Token, new_user: Callable[[], UUID]
) -> None:
    headers = auth(token, new_user())
    pid = await project(client, headers)
    for _ in range(3):
        made = await client.post(f"/projects/{pid}/runs", json={"kind": "brief"}, headers=headers)
        assert made.status_code == 201, made.text
    fourth = await client.post(f"/projects/{pid}/runs", json={"kind": "brief"}, headers=headers)
    assert fourth.status_code == 429
    text = fourth.json()["detail"]
    assert (
        "не больше 3 прогонов в день" in text and "по Москве" in text and "X-OpenRouter-Key" in text
    )
    assert 0 < int(fourth.headers["Retry-After"]) <= 24 * 3600
    usage = (await client.get("/usage", headers=headers)).json()
    assert usage == {"runs_today": 3, "runs_limit": 3, "cost_today_usd": 0.0, "unlimited": False}


async def test_an_own_key_is_not_counted_and_is_not_stored(
    client: AsyncClient, token: Token, new_user: Callable[[], UUID], database_url: str
) -> None:
    user = new_user()
    headers = auth(token, user)
    pid = await project(client, headers)
    for _ in range(3):
        await client.post(f"/projects/{pid}/runs", json={"kind": "brief"}, headers=headers)
    own = await client.post(
        f"/projects/{pid}/runs",
        json={"kind": "brief"},
        headers=auth(token, user, **{"X-OpenRouter-Key": KEY}),
    )
    assert own.status_code == 201 and own.json()["run"]["byok"] is True
    assert sql(
        database_url, "select model_profile from runs where id = %s", [own.json()["run"]["id"]]
    ) == [("byok",)]
    assert (await client.get("/usage", headers=headers)).json()["runs_today"] == 3
    with psycopg.connect(database_url) as conn:
        dump = conn.execute("select string_agg(t::text, ' ') from runs t").fetchone()
    assert dump is not None and KEY not in (dump[0] or "")


async def test_two_requests_at_once_cannot_both_take_the_last_run(
    client: AsyncClient, token: Token, new_user: Callable[[], UUID]
) -> None:
    headers = auth(token, new_user())
    pid = await project(client, headers)
    for _ in range(2):
        await client.post(f"/projects/{pid}/runs", json={"kind": "brief"}, headers=headers)
    both = await asyncio.gather(
        *(
            client.post(f"/projects/{pid}/runs", json={"kind": "brief"}, headers=headers)
            for _ in range(2)
        )
    )
    assert sorted(r.status_code for r in both) == [201, 429]


async def test_an_admin_has_no_limit(
    client: AsyncClient, token: Token, new_user: Callable[[], UUID], database_url: str
) -> None:
    admin = new_user()
    sql(database_url, "update profiles set role = 'admin' where id = %s", [admin])
    headers = auth(token, admin)
    pid = await project(client, headers)
    for _ in range(4):
        made = await client.post(f"/projects/{pid}/runs", json={"kind": "brief"}, headers=headers)
        assert made.status_code == 201
    usage = (await client.get("/usage", headers=headers)).json()
    assert usage["unlimited"] is True and usage["runs_limit"] is None


async def test_above_the_daily_cap_new_runs_go_to_free_models(
    client: AsyncClient, token: Token, new_user: Callable[[], UUID], database_url: str
) -> None:
    rich, user = new_user(), new_user()
    sql(
        database_url,
        "update projects set config = jsonb_set(config, '{models,profile}', '\"cheap\"') "
        "where owner_id = %s",
        [user],
    )
    headers = auth(token, user)
    pid = await project(client, headers)
    sql(
        database_url,
        "update projects set config = jsonb_set(config, '{models,profile}', '\"cheap\"') "
        "where id = %s",
        [pid],
    )
    first = (
        await client.post(f"/projects/{pid}/runs", json={"kind": "brief"}, headers=headers)
    ).json()
    assert first["run"]["id"]
    assert sql(
        database_url, "select model_profile from runs where id = %s", [first["run"]["id"]]
    ) == [("cheap",)]
    sql(
        database_url,
        "insert into usage_daily (user_id, day, runs, cost_usd) "
        "values (%s, (now() at time zone 'Europe/Moscow')::date, 1, 0.75) "
        "on conflict (user_id, day) do update set cost_usd = 0.75",
        [rich],
    )
    second = (
        await client.post(f"/projects/{pid}/runs", json={"kind": "brief"}, headers=headers)
    ).json()
    assert sql(
        database_url, "select model_profile from runs where id = %s", [second["run"]["id"]]
    ) == [("free",)]
    sql(database_url, "delete from usage_daily where user_id = %s", [rich])  # the shared total


async def test_an_answer_to_a_run_on_an_own_key_needs_the_key_again(
    client: AsyncClient, token: Token, new_user: Callable[[], UUID], database_url: str
) -> None:
    user = new_user()
    headers = auth(token, user)
    pid = await project(client, headers)
    own = auth(token, user, **{"X-OpenRouter-Key": KEY})
    run = (
        await client.post(f"/projects/{pid}/runs", json={"kind": "interview"}, headers=own)
    ).json()["run"]
    sql(database_url, "update runs set status = 'waiting_input' where id = %s", [run["id"]])
    without = await client.post(f"/runs/{run['id']}/answer", json={"text": "Да."}, headers=headers)
    assert without.status_code == 400 and "X-OpenRouter-Key" in without.json()["detail"]
    assert (
        await client.post(f"/runs/{run['id']}/answer", json={"text": "Да."}, headers=own)
    ).status_code == 202


def test_a_new_day_starts_at_midnight_in_moscow() -> None:
    late = datetime(2026, 11, 19, 23, 30, tzinfo=ZoneInfo("Europe/Moscow"))
    assert seconds_to_midnight("Europe/Moscow", late) == 30 * 60
    utc_evening = datetime(2026, 11, 19, 21, 30, tzinfo=ZoneInfo("UTC"))  # 00:30 in Moscow
    assert seconds_to_midnight("Europe/Moscow", utc_evening) == 23 * 3600 + 30 * 60
