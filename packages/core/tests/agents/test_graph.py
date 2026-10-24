"""The run graph of 03_agents on stub models: brief, interview with pauses, repair (T-201)."""

from collections.abc import Callable
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from reqgraph.agents.graph import NODES, build_graph, route_tasks
from reqgraph.agents.runtime import RunContext, checkpoint_serde
from reqgraph.agents.state import BudgetState, RepairTask, RunState, initial_state
from reqgraph.graph import ArtifactGraph, GraphPatch

from .conftest import QUESTION, events_of, stub_models, visited

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
    assert out["__interrupt__"][0].value == {"question": QUESTION}

    # a new graph object over the same checkpoints: the server was restarted between the answers
    out = await run(ctx, Command(resume="Звонят по телефону."), saver=saver)
    assert out["__interrupt__"][0].value == {"question": QUESTION}
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
    assert visited(ctx)[-6:] == [*PIPELINE, "export", "persist"]


async def test_repair_loop_stops_after_max_iterations(context: Callable[..., RunContext]) -> None:
    ctx = context()
    out = await run(ctx, initial_state(with_vague_fr001(ctx.project.graph), "brief"))
    assert out["iteration"] == ctx.max_iter == 5
    assert visited(ctx).count("reviewer") == 5 and visited(ctx).count("ci_check") == 6
    assert visited(ctx)[-2:] == ["export", "persist"]
    # repair tasks go to their owner only: modeler and standards have none and skip the LLM
    assert len(events_of(ctx, "llm_call")) == 3 + 5
    assert {e["agent"] for e in events_of(ctx, "skip")} == {"modeler", "standards"}
    (task,) = events_of(ctx, "repair")[0]["tasks"]
    assert (task["owner"], task["node_ids"], task["check_ids"]) == (
        "analyst",
        ["FR-001"],
        ["ISO-001"],
    )


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
    (dropped,) = events_of(ctx, "dropped")  # after one retry with the reason
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
    (added,) = set(out["graph"].nodes) - set(ctx.project.graph.nodes)
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


async def test_agent_patch_with_foreign_node_kinds_is_rejected(
    context: Callable[..., RunContext],
) -> None:
    """Standards may not write requirements: FR belongs to the Analyst (ALLOWED)."""
    foreign = {
        "ops": [
            {"op": "add", "kind": "FR", "tmp_id": "fr", "fields": {"title": "x", "statement": "y"}},
            {"op": "link", "from": "fr", "rel": "refines", "to": "UR-001"},
            {"op": "update", "id": "FR-001", "fields": {"title": "Работа"}},
        ]
    }
    ctx = context(models=stub_models(standards=foreign))
    out = await run(ctx, ctx.initial_state("brief"))
    assert out["graph"] == ctx.project.graph
    (dropped,) = events_of(ctx, "dropped")
    assert dropped["agent"] == "standards"
    assert dropped["reasons"] == [
        "add FR: чужой тип узла",
        "link fr refines UR-001: узел fr не создаётся в этом патче",
        "update FR-001: чужой тип узла",
    ]


async def test_budget_spent_before_the_first_question_skips_the_interview(
    context: Callable[..., RunContext],
) -> None:
    ctx = context()
    out = await run(ctx, ctx.initial_state("interview", budget=BudgetState(usd=0.5, tokens=1)))
    assert "__interrupt__" not in out and out["stop"] == "budget"
    assert events_of(ctx, "stop")[0]["node"] == "interviewer"
    assert visited(ctx) == ["intake", "interviewer", "await_answer", *PIPELINE, "export", "persist"]
