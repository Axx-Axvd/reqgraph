"""One job of the queue: start a run, resume it with the client's answer, or cancel it.

The run graph of the core is used as is (agents/graph.py) with LangGraph's Postgres checkpointer
in schema lg, thread_id = run_id. Before a step the runner looks at the checkpoint: a run with
a checkpoint goes on from it, so a job taken again after a restart does not redo finished nodes
(and does not pay for their LLM calls again). The result is saved through PgStore as a new
revision by the agent; questions and answers go to interview_turns as the chat of the web app.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Jsonb
from reqgraph.agents.graph import build_graph
from reqgraph.agents.nodes import DONE
from reqgraph.agents.run import summarize
from reqgraph.agents.runtime import RunContext, checkpoint_serde
from reqgraph.agents.state import BudgetState, Mode, RunState
from reqgraph.graph.store.formats import BRIEF_FILE
from reqgraph.llm.router import provider_keys

from reqgraph_api import store
from reqgraph_api.db import Database
from reqgraph_api.keys import RunKeys
from reqgraph_api.worker import queue
from reqgraph_api.worker.events import PgEvents

FINISHED = ("succeeded", "failed", "cancelled")


class RunError(RuntimeError):
    """The run cannot go on (no brief, no project): it fails at once, without retries."""


class KeyMissing(RuntimeError):
    """A run on the user's own key, but the key is not in memory (the process restarted): the
    question waits for the key to come again with the answer; our models are never used instead."""


@asynccontextmanager
async def checkpointer(url: str) -> AsyncIterator[AsyncPostgresSaver]:
    """LangGraph's Postgres saver on its own connection, tables in schema lg (04_data);
    autocommit and no prepared statements for the Supavisor session pooler (CLAUDE.md)."""
    conn = await AsyncConnection.connect(
        url, autocommit=True, prepare_threshold=None, row_factory=dict_row
    )
    try:
        await conn.execute("set search_path to lg")
        yield AsyncPostgresSaver(conn, serde=checkpoint_serde())
    finally:
        await conn.close()


@dataclass
class Runner:
    db: Database
    url: str  # the database for the checkpointer
    options: Mapping[str, Any] = field(
        default_factory=dict
    )  # RunContext overrides (tests, offline)
    poll: float = 5.0  # how often a running step looks for a cancel and renews its lock
    keys: RunKeys = field(default_factory=RunKeys)  # users' own keys by run (T-503), in memory only
    tz: str = "Europe/Moscow"  # the day of the demo counters (T-503)

    async def setup(self) -> None:
        async with checkpointer(self.url) as saver:
            await saver.setup()

    async def handle(self, job: DictRow) -> None:
        """Run the job to its end; on an error it goes back to the queue (or fails the run after
        the last attempt). A cancel of this coroutine (shutdown) leaves the job running: it is
        abandoned and taken again later."""
        if job["kind"] == "cancel":
            async with self.db.as_service() as conn:
                await queue.cancel_run(conn, job["run_id"])
                await queue.finish(conn, job["id"], "done")
            return
        step = asyncio.ensure_future(self._step(job))
        cancelled = await self._watch(job, step)
        async with self.db.as_service() as conn:
            if cancelled:
                await queue.cancel_run(conn, job["run_id"])
                await queue.finish(conn, job["id"], "done")
                return
            error = step.exception()
            if error is None:
                await queue.finish(conn, job["id"], "done")
            elif isinstance(error, KeyMissing):
                await queue.finish(conn, job["id"], "failed", str(error))
                await conn.execute(
                    "insert into public.run_events (run_id, type, payload) "
                    "values (%s, 'key_required', '{}')",
                    [job["run_id"]],
                )
                if job["kind"] == "start":
                    await queue.fail_run(conn, job["run_id"], str(error))
                else:  # the question waits for the answer again, now with the key
                    await conn.execute(
                        "update public.runs set status = 'waiting_input' "
                        "where id = %s and status = 'running'",
                        [job["run_id"]],
                    )
            elif isinstance(error, RunError):
                await queue.finish(conn, job["id"], "failed", str(error))
                await queue.fail_run(conn, job["run_id"], str(error))
            else:
                await queue.retry_or_fail(conn, job, f"{type(error).__name__}: {error}"[:500])

    async def _watch(self, job: DictRow, step: "asyncio.Future[None]") -> bool:
        """Wait for the step; meanwhile renew the lock and stop the step on a cancel job."""
        try:
            while True:
                done, _ = await asyncio.wait({step}, timeout=self.poll)
                if done:
                    return False
                async with self.db.as_service() as conn:
                    await queue.heartbeat(conn, job["id"])
                    if await queue.cancel_requested(conn, job["run_id"], job["id"]):
                        step.cancel()
                        with suppress(asyncio.CancelledError, Exception):
                            await step
                        return True
        except asyncio.CancelledError:
            step.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await step
            raise

    async def _run(self, run_id: UUID) -> DictRow:
        async with self.db.as_service() as conn:
            row = await (
                await conn.execute(
                    "update public.runs set status = case when status in "
                    "('succeeded', 'failed', 'cancelled') then status else 'running' end, "
                    "started_at = coalesce(started_at, now()) where id = %s returning *",
                    [run_id],
                )
            ).fetchone()
        if row is None:
            raise RunError("прогон не найден")
        return row

    async def _step(self, job: DictRow) -> None:
        run = await self._run(job["run_id"])
        if run["status"] in FINISHED:
            return  # cancelled or failed while the job waited
        async with self.db.as_service() as conn:
            project, _ = await store.load(conn, run["project_id"])
        settings: dict[str, Any] = {}
        if "max_turns" in run["config"]:
            settings["max_turns"] = int(run["config"]["max_turns"])
        if run["model_profile"]:
            settings["profile"] = run["model_profile"]
        keys: dict[str, str] = {}
        if run["byok"]:
            key = self.keys.get(run["id"])
            if key is None:
                raise KeyMissing(
                    "ключ OpenRouter не дошёл до исполнителя (сервер перезапускался): "
                    + (
                        "запустите прогон снова"
                        if job["kind"] == "start"
                        else "ответьте снова с ключом"
                    )
                )
            keys["openrouter"] = key
        events = PgEvents(self.db, run["id"])
        ctx = RunContext.for_project(
            project, store=None, events=events, **(settings | dict(self.options))
        )
        config: Any = {"configurable": {"thread_id": str(run["id"])}}
        try:
            with provider_keys(keys):  # only this run's task sees the key (a ContextVar)
                async with checkpointer(self.url) as saver:
                    graph = build_graph(checkpointer=saver)
                    result = await self._advance(graph, config, ctx, job, run, project.files)
        finally:
            await events.close()
            if not run["byok"]:
                await self._count(run["project_id"], events.spent)
        if "__interrupt__" in result:
            await self._ask(run["id"], result)
        else:
            await self._finish(ctx, run, project, result)

    async def _count(self, project_id: UUID, spent: Mapping[str, float]) -> None:
        """The step's tokens and dollars to the owner's demo counter of today (T-503); runs on
        the user's own key are not ours to count."""
        if not any(spent.values()):
            return
        async with self.db.as_service() as conn:
            await conn.execute(
                "insert into public.usage_daily "
                "(user_id, day, runs, tokens_in, tokens_out, cost_usd) "
                "select owner_id, (now() at time zone %(tz)s)::date, 0, %(i)s, %(o)s, %(c)s "
                "from public.projects where id = %(p)s "
                "on conflict (user_id, day) do update set "
                "tokens_in = usage_daily.tokens_in + excluded.tokens_in, "
                "tokens_out = usage_daily.tokens_out + excluded.tokens_out, "
                "cost_usd = usage_daily.cost_usd + excluded.cost_usd",
                {
                    "tz": self.tz,
                    "i": int(spent["input_tokens"]),
                    "o": int(spent["output_tokens"]),
                    "c": spent["cost_usd"],
                    "p": project_id,
                },
            )

    async def _advance(
        self,
        graph: Any,
        config: Any,
        ctx: RunContext,
        job: DictRow,
        run: DictRow,
        files: Mapping[str, str],
    ) -> dict[str, Any]:
        """One step of the graph from where the checkpoint says it is."""
        snapshot = await graph.aget_state(config)
        if job["kind"] == "resume" and snapshot.interrupts:
            payload = job["payload"]
            if payload.get("done"):
                answer: object = dict(DONE)
            else:
                answer = str(payload["answer"])
                await self._turn(run["id"], "client", str(answer), None)
            return dict(await graph.ainvoke(Command(resume=answer), config, context=ctx))
        if snapshot.next:  # a checkpoint of this run: a restart goes on from it
            return dict(await graph.ainvoke(None, config, context=ctx))
        if snapshot.values:  # the graph ended before the process stopped
            return dict(snapshot.values)
        mode: Mode = "interview" if run["kind"] == "interview" else "brief"
        brief = job["payload"].get("brief") or files.get(BRIEF_FILE)
        if mode == "brief" and not (brief and brief.strip()):
            raise RunError("нет брифа: задайте его при запуске или при создании проекта")
        state = ctx.initial_state(mode, budget=BudgetState.default(), brief=brief or None)
        return dict(await graph.ainvoke(state, config, context=ctx))

    async def _turn(self, run_id: UUID, role: str, text: str, coverage: Any) -> None:
        async with self.db.as_service() as conn:
            last = await (
                await conn.execute(
                    "select role, content from public.interview_turns where run_id = %s "
                    "order by id desc limit 1",
                    [run_id],
                )
            ).fetchone()
            if last is not None and (last["role"], last["content"]) == (role, text):
                return  # the same step taken again after a restart
            await conn.execute(
                "insert into public.interview_turns (run_id, role, content, coverage) "
                "values (%s, %s, %s, %s)",
                [run_id, role, text, None if coverage is None else Jsonb(coverage)],
            )

    async def _ask(self, run_id: UUID, result: Mapping[str, Any]) -> None:
        pending = result["__interrupt__"][0].value
        coverage = result.get("coverage")
        covered = None if coverage is None else coverage.model_dump(mode="json")
        await self._turn(run_id, "agent", str(pending["question"]), covered)
        async with self.db.as_service() as conn:
            await conn.execute(
                "update public.runs set status = 'waiting_input' "
                "where id = %s and status = 'running'",
                [run_id],
            )

    async def _finish(
        self, ctx: RunContext, run: DictRow, project: Any, result: Mapping[str, Any]
    ) -> None:
        out = RunState(**result)  # type: ignore[typeddict-item]
        report = out["ci"]
        assert report is not None  # ci_check always runs
        async with self.db.as_service() as conn:
            calls = [
                r["payload"]
                for r in await (
                    await conn.execute(
                        "select payload from public.run_events where run_id = %s "
                        "and type = 'llm_call' order by id",
                        [run["id"]],
                    )
                ).fetchall()
            ]
            started = run["started_at"].timestamp() if run["started_at"] else time.time()
            summary = summarize(ctx, out, report, calls, time.time() - started, out["budget"].usd)
            done = replace(project, graph=out["graph"], files=project.files | out["files"])
            rev = await store.save(conn, run["project_id"], done, "agent")
            ci = {**report.summary.model_dump(mode="json"), "headline": report.headline()}
            await conn.execute(
                "update public.graph_revisions set ci_summary = %s, ci_report = %s "
                "where project_id = %s and rev = %s",
                [
                    Jsonb(ci | {"stop": out["stop"], "run_id": str(run["id"])}),
                    Jsonb(report.model_dump(mode="json")),  # T-505: findings for the site
                    run["project_id"],
                    rev,
                ],
            )
            failed = out["stop"] == "budget"
            await conn.execute(
                "update public.runs set status = %s, error = %s, iteration = %s, tokens_in = %s, "
                "tokens_out = %s, cost_usd = %s, package_version = %s, finished_at = now(), "
                "config = config || %s where id = %s and status = 'running'",
                [
                    "failed" if failed else "succeeded",
                    "бюджет прогона исчерпан" if failed else None,
                    summary.iterations,
                    summary.input_tokens,
                    summary.output_tokens,
                    summary.cost_usd,
                    summary.package_version,
                    Jsonb({"summary": summary.to_dict(), "rev": rev}),
                    run["id"],
                ],
            )
