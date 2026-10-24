"""Analyst (T-202): brief -> client turns -> AnalystDraft -> GraphPatch -> guard -> apply."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from reqgraph.agents.analyst import AnalystDraft, to_patch
from reqgraph.agents.graph import build_graph
from reqgraph.agents.runtime import RunContext
from reqgraph.checks.runner import run_checks
from reqgraph.checks.trace import HasSource
from reqgraph.graph import GraphPatch

from .conftest import BRIEF, DRAFT, events_of, stub_models, turns_graph, visited

pytestmark = pytest.mark.anyio


def scripted(*answers: dict[str, Any]) -> FunctionModel:
    """Answers in turn: the first call gets the first draft, a retry the next; then the last one."""
    calls: list[int] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(1)
        return ModelResponse(
            parts=[
                TextPart(json.dumps(answers[min(len(calls), len(answers)) - 1], ensure_ascii=False))
            ]
        )

    return FunctionModel(fn, model_name="scripted")


def test_draft_becomes_a_patch_with_ids_links_and_sources() -> None:
    graph = turns_graph()
    conversion = to_patch(AnalystDraft.model_validate(DRAFT), graph)
    assert conversion.dropped == []
    result = graph.apply(conversion.patch, actor="agent")
    new = result.graph
    assert {n.kind for n in new.nodes.values()} >= {"ACT", "BR", "UR", "FR", "NFR", "CON"}
    ur = new.nodes[result.id_map[conversion.refs["ur_book"]]]
    assert ur.actor == result.id_map[conversion.refs["patient"]]  # type: ignore[union-attr]
    fr = result.id_map[conversion.refs["fr_remind"]]
    assert {(e.rel.value, e.dst) for e in new.edges if e.src == fr} == {
        ("refines", result.id_map[conversion.refs["ur_book"]]),
        ("derived_from", "TURN-0002"),
    }


def test_invalid_items_are_dropped_with_a_reason_and_the_rest_stays() -> None:
    draft = json.loads(json.dumps(DRAFT))
    del draft["requirements"][3]["metric"]  # NFR without a metric is not an NFR
    draft["requirements"][2]["refines"] = ["ur_book", "nfr_sms"]  # link to the dropped one
    conversion = to_patch(AnalystDraft.model_validate(draft), turns_graph())
    assert conversion.dropped[0].startswith("nfr_sms: ")
    assert "metric" in conversion.dropped[0]
    assert any("nfr_sms" in d for d in conversion.dropped[1:])
    turns_graph().apply(conversion.patch, actor="agent")


def test_existing_requirement_is_updated_only_where_it_changed() -> None:
    graph = turns_graph()
    first = to_patch(AnalystDraft.model_validate(DRAFT), graph)
    result = graph.apply(first.patch, actor="agent")
    fr_id = result.id_map[first.refs["fr_remind"]]
    edit = {
        "requirements": [
            {
                **DRAFT["requirements"][2],
                "ref": fr_id,
                "title": "SMS-напоминание",
                "refines": [],
                "sources": [],
            },
            {**DRAFT["requirements"][0], "ref": fr_id.replace("FR", "BR"), "kind": "UR"},
        ]
    }
    conversion = to_patch(AnalystDraft.model_validate(edit), result.graph)
    (op,) = conversion.patch.ops
    assert op.op == "update" and op.fields == {"title": "SMS-напоминание"}
    assert conversion.dropped == [f"{fr_id.replace('FR', 'BR')}: вид узла BR нельзя сменить на UR"]


async def test_brief_run_writes_requirements_with_their_sources(
    brief_context: Callable[..., RunContext], empty_project: Path
) -> None:
    ctx = brief_context()
    out = await build_graph().ainvoke(ctx.initial_state("brief", brief=BRIEF), context=ctx)
    graph = out["graph"]
    turns = [n for n in graph.nodes.values() if n.kind == "TURN"]
    assert [t.role for t in turns] == ["client", "client"]
    assert "Бриф" not in turns[0].text  # the heading is not a turn
    assert HasSource().run(graph, None) == []  # type: ignore[arg-type]
    (call,) = [e for e in events_of(ctx, "llm_call") if e["role"] == "analyst"]
    assert call["prompt"] == "analyst/extract" and len(call["prompt_hash"]) == 12
    assert (empty_project / "requirements" / "functional.yaml").is_file()  # persisted


async def test_dropped_items_are_retried_once_with_the_reasons(
    brief_context: Callable[..., RunContext],
) -> None:
    broken = json.loads(json.dumps(DRAFT))
    del broken["requirements"][3]["metric"]  # an NFR without a metric
    model = scripted(broken, DRAFT, broken)
    ctx = brief_context(models=stub_models() | {"analyst": model})
    out = await build_graph().ainvoke(ctx.initial_state("brief", brief=BRIEF), context=ctx)
    assert [e["role"] for e in events_of(ctx, "llm_call")].count("analyst") == 2  # once, not twice
    (retry,) = events_of(ctx, "patch_retry")
    assert retry["agent"] == "analyst" and "metric" in retry["reasons"][0]
    assert any(n.kind == "NFR" for n in out["graph"].nodes.values())


async def test_still_dropped_after_the_retry_is_logged_and_the_rest_applied(
    brief_context: Callable[..., RunContext],
) -> None:
    broken = json.loads(json.dumps(DRAFT))
    del broken["requirements"][3]["metric"]
    ctx = brief_context(models=stub_models() | {"analyst": scripted(broken, broken)}, max_iter=0)
    out = await build_graph().ainvoke(ctx.initial_state("brief", brief=BRIEF), context=ctx)
    (dropped,) = [e for e in events_of(ctx, "dropped") if e["agent"] == "analyst"]
    assert dropped["reasons"][0].startswith("nfr_sms: ")
    kinds = [n.kind for n in out["graph"].nodes.values()]
    assert "NFR" not in kinds and "FR" in kinds


async def test_prompt_carries_turns_as_data_and_the_rules(
    brief_context: Callable[..., RunContext],
) -> None:
    seen: list[str] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(str(messages[0]))
        return ModelResponse(parts=[TextPart(json.dumps({"requirements": []}))])

    ctx = brief_context(models=stub_models() | {"analyst": FunctionModel(fn)})
    await build_graph().ainvoke(ctx.initial_state("brief", brief=BRIEF), context=ctx)
    prompt = seen[0]
    assert '<turn id="TURN-0002" role="client">' in prompt
    assert "Нужна онлайн-запись" in prompt
    assert "быстро" in prompt  # vague words come from checks/vague_words.yaml
    assert "performance_efficiency" in prompt


async def test_repair_round_shows_only_the_analysts_tasks(
    context: Callable[..., RunContext],
) -> None:
    """On garage61 with a vague FR-001 the Analyst gets one task per round (5 rounds)."""
    seen: list[str] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(str(messages[0]))
        return ModelResponse(parts=[TextPart(json.dumps({"requirements": []}))])

    ctx = context(models=stub_models() | {"analyst": FunctionModel(fn)})
    fields = {"statement": "Система должна быстро показывать клиенту список услуг."}
    patch = GraphPatch.model_validate({"ops": [{"op": "update", "id": "FR-001", "fields": fields}]})
    state = ctx.initial_state("brief")
    state["graph"] = state["graph"].apply(patch, actor="user").graph
    await build_graph().ainvoke(state, context=ctx)
    # the stub never fixes FR-001: two rounds without progress, then needs_human (T-205)
    assert len(seen) == 1 + 2 and "ISO-001" not in seen[0] and "ISO-001" in seen[1]
    assert visited(ctx).count("analyst") == 3


async def test_reference_checks_still_pass_on_the_brief_result(
    brief_context: Callable[..., RunContext],
) -> None:
    ctx = brief_context()
    out = await build_graph().ainvoke(ctx.initial_state("brief", brief=BRIEF), context=ctx)
    report = await run_checks(ctx.project.with_graph(out["graph"]), offline=True)
    iso = [f for f in report.findings if f.check_id in ("ISO-001", "ISO-003", "TRC-006")]
    assert iso == []


def test_an_edit_keeps_the_fields_the_model_did_not_send() -> None:
    graph = turns_graph()
    first = to_patch(AnalystDraft.model_validate(DRAFT), graph)
    result = graph.apply(first.patch, actor="agent")
    fr_id = result.id_map[first.refs["fr_remind"]]
    edit = {"requirements": [{"ref": fr_id, "kind": "FR", "title": "SMS", "statement": "x"}]}
    (op,) = to_patch(AnalystDraft.model_validate(edit), result.graph).patch.ops
    assert op.fields == {"title": "SMS", "statement": "x"}  # type: ignore[union-attr]
