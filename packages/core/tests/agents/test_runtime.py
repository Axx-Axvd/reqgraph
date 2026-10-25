"""Run context: events (memory, JSONL), budget in the state, checkpoint serializer (T-201)."""

import json
import logging
from collections.abc import Callable
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from reqgraph.agents.graph import build_graph
from reqgraph.agents.runtime import JsonlEvents, RunContext, checkpoint_serde
from reqgraph.agents.state import BudgetState, Coverage, initial_state
from reqgraph.llm.config import load_roles

pytestmark = pytest.mark.anyio


def test_budget_state_defaults_to_roles_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQGRAPH_RUN_BUDGET_USD", "0.25")
    budget = BudgetState.default()
    assert (budget.usd, budget.tokens) == (0.25, load_roles().budget.run_tokens)
    assert (budget.spent_usd, budget.spent_tokens) == (0.0, 0)


def test_budget_state_round_trips_through_the_run_budget() -> None:
    run_budget = BudgetState(usd=1.0, tokens=100, spent_tokens=7).to_run_budget()
    run_budget.spent_tokens += 5
    assert BudgetState.of(run_budget).spent_tokens == 12


def test_coverage_areas_and_thresholds_of_the_design() -> None:
    coverage = Coverage()
    assert coverage.need["scenarios"] == 4 and len(coverage.need) == 9
    assert not coverage.complete
    assert Coverage(got=dict(coverage.need)).complete


def test_jsonl_events_are_one_json_object_per_line(tmp_path: Path) -> None:
    sink = JsonlEvents(tmp_path / "run" / "events.jsonl")
    sink.emit("node_start", node="intake")
    sink.emit("llm_call", role="analyst", model="m", input_tokens=10)
    lines = (tmp_path / "run" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    first, second = (json.loads(line) for line in lines)
    assert first["type"] == "node_start" and first["node"] == "intake" and "ts" in first
    assert second["role"] == "analyst"


async def test_run_writes_events_without_prompts_or_keys(
    context: Callable[..., RunContext], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key-value")
    path = tmp_path / "events.jsonl"
    ctx = context(events=JsonlEvents(path))
    await build_graph().ainvoke(
        initial_state(ctx.project.graph, "brief"),
        {"configurable": {"thread_id": "t"}},
        context=ctx,
    )
    text = path.read_text(encoding="utf-8")
    assert "secret-key-value" not in text
    assert "Записаться на обслуживание" not in text  # graph texts go to the model, not to the log
    calls = [e for e in map(json.loads, text.splitlines()) if e["type"] == "llm_call"]
    assert {"role", "model", "provider", "input_tokens", "output_tokens", "cost_usd"} <= set(
        calls[0]
    )


async def test_checkpoints_keep_our_types_without_warnings(
    context: Callable[..., RunContext], caplog: pytest.LogCaptureFixture
) -> None:
    saver = InMemorySaver(serde=checkpoint_serde())
    ctx = context(max_turns=1)
    config: RunnableConfig = {"configurable": {"thread_id": "t"}}
    await build_graph(saver).ainvoke(
        initial_state(ctx.project.graph, "interview"), config, context=ctx
    )
    with caplog.at_level(logging.WARNING):
        out = await build_graph(saver).ainvoke(Command(resume="Да."), config, context=ctx)
    assert "unregistered" not in caplog.text and "Blocked" not in caplog.text
    assert isinstance(out["coverage"], Coverage) and isinstance(out["budget"], BudgetState)
    # restored by validation, not by model_construct: nodes and edges are models again
    model_edges = tuple(e for e in out["graph"].edges if e.rel.value != "rendered_in")
    assert model_edges == ctx.project.graph.edges
    assert all(out["graph"].nodes[i] == n for i, n in ctx.project.graph.nodes.items())


def test_limits_and_profile_come_from_reqgraph_yaml(context: Callable[..., RunContext]) -> None:
    ctx = context()
    config = ctx.project.config
    assert (ctx.profile, ctx.max_iter, ctx.max_turns) == (
        config.models.profile,
        config.checks.max_iterations,
        config.interview.max_turns,
    )
    assert ctx.initial_state("interview")["coverage"].need == config.interview.coverage_need
    assert context(max_turns=3).max_turns == 3


async def test_agents_are_not_run_on_the_reference_project() -> None:
    from reqgraph.agents.nodes import ReferenceProject
    from reqgraph.dsl.readers import model_readers
    from reqgraph.graph.store import FileStore

    from .conftest import GARAGE61, stub_models

    ctx = RunContext.for_project(FileStore(GARAGE61, readers=model_readers()).load())
    ctx.models = stub_models()
    with pytest.raises(ReferenceProject, match="эталонный проект"):
        await build_graph().ainvoke(ctx.initial_state("brief"), context=ctx)
