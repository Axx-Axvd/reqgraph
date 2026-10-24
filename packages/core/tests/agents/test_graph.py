"""The run graph of 03_agents on stub models: brief, interview with pauses, repair (T-201)."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from reqgraph.agents.graph import NODES, build_graph, route_tasks
from reqgraph.agents.runtime import RunContext, checkpoint_serde
from reqgraph.agents.state import BudgetState, RepairTask, RunState, initial_state
from reqgraph.graph import ArtifactGraph, GraphPatch
from reqgraph.graph.store import FileStore

from .conftest import GARAGE61, QUESTION, events_of, stub_models, visited

pytestmark = pytest.mark.anyio

PIPELINE = ["analyst", "modeler", "standards", "ci_check"]
THREAD = {"configurable": {"thread_id": "run-1"}}


async def run(ctx: RunContext, state: RunState | Command[Any], **kwargs: Any) -> dict[str, Any]:
    graph = build_graph(checkpointer=kwargs.pop("saver", None))
    return await graph.ainvoke(state, kwargs.pop("config", THREAD), context=ctx)


def with_vague_fr001(graph: ArtifactGraph) -> ArtifactGraph:
    """An error the stub agents never fix: ISO-001 on FR-001 (owner — analyst)."""
    fields = {"statement": "Система должна быстро показывать клиенту список услуг."}
    patch = GraphPatch.model_validate({"ops": [{"op": "update", "id": "FR-001", "fields": fields}]})
    return graph.apply(patch, actor="user").graph


def test_graph_compiles_with_every_node_of_the_design() -> None:
    nodes = set(build_graph().get_graph().nodes)
    assert set(NODES) <= nodes
    assert set(NODES) == {
        "intake",
        "coverage",
        "interviewer",
        "await_answer",
        "analyst",
        "modeler",
        "standards",
        "ci_check",
        "reviewer",
        "export",
        "persist",
    }


async def test_brief_goes_through_the_pipeline_to_a_clean_report(
    context: Callable[..., RunContext],
) -> None:
    ctx = context()
    out = await run(ctx, initial_state(ctx.project.graph, "brief"))
    assert visited(ctx) == ["intake", *PIPELINE, "export", "persist"]
    assert [e["role"] for e in events_of(ctx, "llm_call")] == ["analyst", "modeler", "standards"]
    assert out["ci"].ok and out["iteration"] == 0 and out["stop"] is None
    assert events_of(ctx, "run_end")[0]["errors"] == 0


async def test_check_mode_runs_only_the_checks(context: Callable[..., RunContext]) -> None:
    ctx = context()
    await run(ctx, initial_state(ctx.project.graph, "check"))
    assert visited(ctx) == ["intake", "ci_check", "export", "persist"]
    assert events_of(ctx, "llm_call") == []


async def test_interview_pauses_for_answers_and_survives_a_restart(
    context: Callable[..., RunContext],
) -> None:
    saver = InMemorySaver(serde=checkpoint_serde())
    ctx = context(max_turns=2)
    out = await run(ctx, initial_state(ctx.project.graph, "interview"), saver=saver)
    assert out["__interrupt__"][0].value == {"question": QUESTION, "turn": 1}

    # a new graph object over the same checkpoints: the server was restarted between the answers
    out = await run(ctx, Command(resume="Звонят по телефону."), saver=saver)
    assert out["__interrupt__"][0].value == {"question": QUESTION, "turn": 2}
    out = await run(ctx, Command(resume="Хватит, остальное в брифе."), saver=saver)

    assert "__interrupt__" not in out
    assert isinstance(out["graph"], ArtifactGraph)  # checkpoints keep our types (allow list)
    before = set(ctx.project.graph.nodes)
    turns = [n for i, n in out["graph"].nodes.items() if i not in before and n.kind == "TURN"]
    assert [(t.role, t.text) for t in turns] == [
        ("agent", QUESTION),
        ("client", "Звонят по телефону."),
        ("agent", QUESTION),
        ("client", "Хватит, остальное в брифе."),
    ]
    # every answer goes to the Analyst and the coverage is counted again; then the models
    assert visited(ctx).count("analyst") == 2 and visited(ctx).count("coverage") == 3
    assert visited(ctx)[-5:] == ["modeler", "standards", "ci_check", "export", "persist"]
    assert [e["reason"] for e in events_of(ctx, "interview_end")] == ["limit"]


async def test_repair_without_progress_stops_with_needs_human(
    context: Callable[..., RunContext],
) -> None:
    """The stub agents never fix FR-001: the same errors after two rounds -> needs_human (T-205)."""
    ctx = context()
    out = await run(ctx, initial_state(with_vague_fr001(ctx.project.graph), "brief"))
    assert out["stop"] == "needs_human" and out["iteration"] == 2
    assert visited(ctx).count("reviewer") == 3 and visited(ctx).count("ci_check") == 3
    assert visited(ctx)[-2:] == ["export", "persist"]  # the report is exported anyway
    (human,) = events_of(ctx, "needs_human")
    assert human["reason"] == "stuck" and human["errors"] == out["history"][-1]
    assert len(out["history"]) == 3
    # repair tasks go to their owner only: modeler and standards have none and skip the LLM
    assert {e["agent"] for e in events_of(ctx, "skip")} == {"modeler", "standards"}
    (task,) = events_of(ctx, "repair")[0]["tasks"]
    assert (task["owner"], task["node_ids"], task["check_ids"]) == (
        "analyst",
        ["FR-001"],
        ["ISO-001"],
    )


async def test_repair_with_progress_each_round_runs_to_max_iterations(
    context: Callable[..., RunContext],
) -> None:
    """Every round the Analyst fixes one FR and breaks the next: new errors, no needs_human."""
    rounds: list[int] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        rounds.append(1)
        n = len(rounds)
        fix = [] if n == 1 else [_vague(f"FR-{n - 1:03d}", vague=False)]
        return ModelResponse(
            parts=[TextPart(json.dumps({"requirements": [*fix, _vague(f"FR-{n:03d}")]}))]
        )

    ctx = context(models=stub_models() | {"analyst": FunctionModel(fn)})
    out = await run(ctx, initial_state(with_vague_fr001(ctx.project.graph), "brief"))
    assert out["iteration"] == ctx.max_iter == 5  # never stuck: every round has new errors
    assert out["stop"] == "needs_human"  # but errors are left after the last round
    (human,) = events_of(ctx, "needs_human")
    assert human["reason"] == "limit"


async def test_repair_that_fixes_the_error_converges(context: Callable[..., RunContext]) -> None:
    calls: list[int] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(1)
        fix = [] if len(calls) == 1 else [_vague("FR-001", vague=False)]
        return ModelResponse(parts=[TextPart(json.dumps({"requirements": fix}))])

    ctx = context(models=stub_models() | {"analyst": FunctionModel(fn)})
    out = await run(ctx, initial_state(with_vague_fr001(ctx.project.graph), "brief"))
    assert out["ci"].ok and out["stop"] is None and out["iteration"] == 1


def _vague(fr: str, vague: bool = True) -> dict[str, Any]:
    """An Analyst edit of an existing FR of garage61: its statement with or without «быстро»."""
    garage = FileStore(GARAGE61).load().graph.nodes[fr]
    statement = garage.statement  # type: ignore[union-attr]
    if vague:
        statement = statement.replace("истема должна", "истема должна быстро", 1)  # С or с
    return {"ref": fr, "kind": "FR", "title": garage.title, "statement": statement}  # type: ignore[union-attr]


async def test_exhausted_budget_stops_the_agents_but_not_the_report(
    context: Callable[..., RunContext],
) -> None:
    ctx = context()
    state = initial_state(ctx.project.graph, "brief", budget=BudgetState(usd=0.5, tokens=1))
    out = await run(ctx, state)
    assert out["stop"] == "budget"
    assert events_of(ctx, "stop")[0]["reason"] == "budget"
    assert events_of(ctx, "llm_call") == []
    assert visited(ctx) == ["intake", *PIPELINE, "export", "persist"]
    assert out["ci"] is not None  # the checks need no LLM: the run still ends with a report


async def test_agents_cannot_change_approved_nodes(context: Callable[..., RunContext]) -> None:
    ctx = context()
    approve = GraphPatch.model_validate(
        {"ops": [{"op": "update", "id": "BR-001", "fields": {"status": "approved"}}]}
    )
    graph = ctx.project.graph.apply(approve, actor="user").graph
    br = graph.nodes["BR-001"]
    sneaky = {
        "requirements": [
            {"ref": "BR-001", "kind": "BR", "title": "Другое", "statement": br.statement}  # type: ignore[union-attr]
        ]
    }
    ctx = context(models=stub_models(analyst=sneaky))
    out = await run(ctx, initial_state(graph, "brief"))
    assert out["graph"].nodes["BR-001"] == br
    (dropped,) = [e for e in events_of(ctx, "dropped") if e["agent"] == "analyst"]  # after a retry
    assert dropped["reasons"] == ["update BR-001: узел утверждён человеком"]


async def test_agent_patch_gets_ids_from_code(context: Callable[..., RunContext]) -> None:
    add = {
        "requirements": [
            {
                "ref": "con_law",
                "kind": "CON",
                "constraint_type": "legal",
                "title": "152-ФЗ",
                "statement": "Данные клиентов хранятся в РФ.",
                "assumption": True,
            }
        ]
    }
    ctx = context(models=stub_models(analyst=add))
    out = await run(ctx, initial_state(ctx.project.graph, "brief"))
    (added,) = {i for i in out["graph"].nodes if not i.startswith("SEC-")} - set(
        ctx.project.graph.nodes
    )
    assert added.startswith("CON-")
    assert events_of(ctx, "agent_end")[0]["diff"]["added"] == [added]


def test_route_tasks_starts_with_the_first_owner_of_the_pipeline() -> None:
    def tasks(*owners: str) -> RunState:
        state = initial_state(ArtifactGraph.empty(), "brief")
        state["tasks"] = [
            RepairTask(owner=o, node_ids=["X"], instruction="…", check_ids=["ISO-001"])  # type: ignore[arg-type]
            for o in owners
        ]
        return state

    assert route_tasks(tasks("standards", "modeler")) == "modeler"
    assert route_tasks(tasks("standards", "analyst")) == "analyst"
    assert route_tasks(tasks("standards")) == "standards"


async def test_budget_spent_before_the_first_question_skips_the_interview(
    context: Callable[..., RunContext],
) -> None:
    ctx = context()
    out = await run(ctx, ctx.initial_state("interview", budget=BudgetState(usd=0.5, tokens=1)))
    assert "__interrupt__" not in out and out["stop"] == "budget"
    assert events_of(ctx, "stop")[0]["node"] == "interviewer"
    assert visited(ctx) == [
        "intake",
        "coverage",
        "interviewer",
        "await_answer",
        *PIPELINE,
        "export",
        "persist",
    ]
