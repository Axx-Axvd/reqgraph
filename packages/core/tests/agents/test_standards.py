"""Standards (T-204): SRS sections from the graph by code; purpose, scope, glossary by the LLM."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from reqgraph.agents.analyst import AnalystDraft, to_patch
from reqgraph.agents.graph import build_graph
from reqgraph.agents.runtime import RunContext
from reqgraph.agents.standards import StandardsDraft, build_sections
from reqgraph.checks.base import CheckContext
from reqgraph.checks.template import SrsSections
from reqgraph.graph import GraphPatch
from reqgraph.graph.nodes import SectionNode
from reqgraph.standards import load_structure

from .conftest import BRIEF, DRAFT, SRS, events_of, stub_models, turns_graph

pytestmark = pytest.mark.anyio


def requirements() -> Any:
    graph = turns_graph()
    return graph.apply(to_patch(AnalystDraft.model_validate(DRAFT), graph).patch).graph


def section(graph: Any, section_id: str) -> SectionNode:
    node = graph.nodes[section_id]
    assert isinstance(node, SectionNode)
    return node


def test_sections_are_built_from_the_graph() -> None:
    graph = requirements()
    result = graph.apply(build_sections(graph, StandardsDraft.model_validate(SRS)), actor="agent")
    new = result.graph
    assert {s.id for s in load_structure("iso29148_srs").sections} <= set(new.nodes)
    features = section(new, "SEC-SRS-3")  # T-408: system features
    assert "- FR-001 Напоминание: За 24 часа" in features.text and "FR-001" in features.refs
    assert ("FR-001", "SEC-SRS-3") in {
        (e.src, e.dst) for e in new.edges if e.rel.value == "rendered_in"
    }
    assert section(new, "SEC-SRS-A").text == "- Запись — забронированное время у мастера"
    assert section(new, "SEC-SRS-2.1").text.startswith("Новая система")  # product perspective
    assert "SMS уходит" in section(new, "SEC-SRS-D").text  # acceptance criteria
    assert "CON-001" in section(new, "SEC-SRS-2.7").text  # the assumption


def test_rebuilding_with_the_same_graph_changes_nothing() -> None:
    graph = requirements()
    draft = StandardsDraft.model_validate(SRS)
    once = graph.apply(build_sections(graph, draft), actor="agent").graph
    assert build_sections(once, draft).ops == []


async def test_empty_answer_is_asked_again_and_tpl001_reports_what_stays_empty(
    brief_context: Callable[..., RunContext],
) -> None:
    calls: list[int] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(1)
        return ModelResponse(parts=[TextPart(json.dumps({"purpose": "Назначение."}))])

    models = stub_models(analyst=DRAFT) | {"standards": FunctionModel(fn)}
    ctx = brief_context(models=models, max_iter=0)
    out = await build_graph().ainvoke(ctx.initial_state("brief", brief=BRIEF), context=ctx)
    assert len(calls) == 2
    (retry,) = [e for e in events_of(ctx, "patch_retry") if e["agent"] == "standards"]
    assert retry["reasons"][0].startswith("scope")
    found = SrsSections().run(out["graph"], CheckContext(ctx.project.with_graph(out["graph"])))
    assert {f.node_ids[0] for f in found} == {
        "SEC-SRS-1.4",  # project scope
        "SEC-SRS-2.1",  # product perspective
        "SEC-SRS-A",  # glossary
        "SEC-SRS-B",  # analysis models: no ENT yet
    }


async def test_prompt_carries_requirements_and_client_turns(
    brief_context: Callable[..., RunContext],
) -> None:
    seen: list[str] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(str(messages[0]))
        return ModelResponse(parts=[TextPart(json.dumps(SRS, ensure_ascii=False))])

    models = stub_models(analyst=DRAFT) | {"standards": FunctionModel(fn)}
    ctx = brief_context(models=models, max_iter=0)
    await build_graph().ainvoke(ctx.initial_state("brief", brief=BRIEF), context=ctx)
    assert '<turn id="TURN-0002">Нужна онлайн-запись' in seen[0]
    assert "- FR-001 Напоминание" in seen[0] and "glossary" in seen[0]


def test_rebuild_without_a_draft_keeps_the_llm_texts_and_lists_new_nodes() -> None:
    graph = requirements()
    graph = graph.apply(
        build_sections(graph, StandardsDraft.model_validate(SRS)), actor="agent"
    ).graph
    nfr = {"op": "update", "id": "NFR-001", "fields": {"title": "Доставка всех SMS"}}
    graph = graph.apply(GraphPatch.model_validate({"ops": [nfr]}), actor="agent").graph
    patch = build_sections(graph, None)
    assert {op.id for op in patch.ops} == {"SEC-SRS-5.3"}  # type: ignore[union-attr]
    rebuilt = graph.apply(patch, actor="agent").graph
    assert "Доставка всех SMS" in section(rebuilt, "SEC-SRS-5.3").text
    assert section(rebuilt, "SEC-SRS-A").text == section(graph, "SEC-SRS-A").text
