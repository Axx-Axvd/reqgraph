"""Limits of the public demo (T-503, 07_deploy): runs per user per day, a total daily cap in
dollars, no limits for an admin or a run on the user's own key.

A day is Moscow time (author's decision 19.11). The per-user counter is taken and checked in one
statement (insert … on conflict … where runs < limit), so two requests at once cannot both pass."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from reqgraph_api.db import Conn, elevate
from reqgraph_api.settings import Settings

FREE = "free"
BYOK = "byok"


@dataclass(frozen=True)
class Admission:
    profile: str
    byok: bool


class LimitReached(Exception):
    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def seconds_to_midnight(tz: str, now: datetime | None = None) -> int:
    local = (now or datetime.now(ZoneInfo(tz))).astimezone(ZoneInfo(tz))
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - local).total_seconds()))


async def is_admin(conn: Conn) -> bool:
    """Under the user's role: RLS shows only their own profile."""
    row = await (
        await conn.execute("select role from public.profiles where id = (select auth.uid())")
    ).fetchone()
    return row is not None and row["role"] == "admin"


async def admit(
    conn: Conn, user_id: UUID, *, byok: bool, profile: str, settings: Settings
) -> Admission:
    """May the user start a run, and on which models. Call after the project was found under RLS;
    leaves the transaction in the backend role (db.elevate)."""
    if byok:
        await elevate(conn)
        return Admission(BYOK, True)
    admin = await is_admin(conn)
    await elevate(conn)
    tz = settings.demo_timezone
    if not admin:
        row = await (
            await conn.execute(
                "insert into public.usage_daily (user_id, day, runs) "
                "values (%(user)s, (now() at time zone %(tz)s)::date, 1) "
                "on conflict (user_id, day) do update set runs = usage_daily.runs + 1 "
                "where usage_daily.runs < %(limit)s returning runs",
                {"user": user_id, "tz": tz, "limit": settings.demo_runs_per_day},
            )
        ).fetchone()
        if row is None:
            raise LimitReached(
                f"Лимит демо — не больше {settings.demo_runs_per_day} прогонов в день. "
                "Новый день начнётся в 00:00 по Москве. "
                "Можно продолжить со своим ключом OpenRouter (заголовок X-OpenRouter-Key).",
                seconds_to_midnight(tz),
            )
        spent = await (
            await conn.execute("select public.demo_spent_today(%s) as usd", [tz])
        ).fetchone()
        if profile != FREE and spent is not None and spent["usd"] >= settings.demo_daily_usd_cap:
            return Admission(FREE, False)  # the daily cap: free models only, the run still goes
    return Admission(profile, False)


async def usage(conn: Conn, settings: Settings) -> dict[str, object]:
    """The user's own counter today (RLS) and whether limits apply to them."""
    admin = await is_admin(conn)
    row = await (
        await conn.execute(
            "select runs, cost_usd::float as cost from public.usage_daily "
            "where user_id = (select auth.uid()) and day = (now() at time zone %s)::date",
            [settings.demo_timezone],
        )
    ).fetchone()
    return {
        "runs_today": 0 if row is None else int(row["runs"]),
        "runs_limit": None if admin else settings.demo_runs_per_day,
        "cost_today_usd": 0.0 if row is None else float(row["cost"]),
        "unlimited": admin,
    }
