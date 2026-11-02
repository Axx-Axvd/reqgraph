"""Modeler, second step (T-207): a form -> use case diagram and C4 workspace, ids and links by code,
self-check and retries, repair tasks on UC and C4 go to this step."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from reqgraph.agents.graph import build_graph
from reqgraph.agents.modeler_views import (
    C4_FILE,
    UML_FILE,
    ViewsDraft,
    to_views,
    view_problems,
)
from reqgraph.agents.runtime import RunContext
from reqgraph.agents.state import RepairTask
from reqgraph.dsl.c4 import parse_workspace
from reqgraph.dsl.plantuml import parse_use_cases
from reqgraph.graph import ArtifactGraph
from reqgraph.graph.store import FileStore

from .conftest import BRIEF, DRAFT, events_of, stub_models
from .test_modeler import MODEL, requirements, scripted

pytestmark = pytest.mark.anyio

C4: dict[str, Any] = {
    "system_name": "Улыбка: запись к стоматологу",
    "system_description": "Запись пациентов и напоминания",
    "containers": [
        {
            "ref": "cnt_api",
            "name": "API",
            "description": "Запись и напоминания",
            "technology": "Python",
            "realizes": ["FR-001"],
        },
        {"ref": "cnt_db", "name": "База данных", "database": True, "realizes": ["FR-001"]},
    ],
    "externals": [{"ref": "ext_sms", "name": "SMS-шлюз", "realizes": ["FR-001"]}],
    "links": [
        {"src": "ACT-01", "dst": "cnt_api", "label": "Записывается", "technology": "HTTPS"},
        {"src": "cnt_api", "dst": "cnt_db", "label": "Хранит записи"},
        {"src": "cnt_api", "dst": "ext_sms", "label": "Отправляет SMS"},
    ],
}
VIEWS: dict[str, Any] = {
    "use_cases": [
        {
            "ref": "uc_book",
            "name": "Записаться на приём",
            "actor": "ACT-01",
            "realizes": ["FR-001"],
        },
        {
            "ref": "uc_cancel",
            "name": "Отменить запись",
            "actor": "ACT-01",
            "realizes": ["FR-001"],
            "extends": "uc_book",
        },
    ],
    "c4": C4,
}


def draft(data: dict[str, Any] = VIEWS) -> ViewsDraft:
    return ViewsDraft.model_validate(data)


def applied(data: dict[str, Any] = VIEWS) -> tuple[ArtifactGraph, dict[str, str]]:
    graph = requirements()
    update = to_views(draft(data), graph, {}, project_name="Улыбка")
    assert update.dropped == []
    return graph.apply(update.patch, actor="agent").graph, update.files


def test_ids_texts_and_links_are_issued_by_code() -> None:
    graph, files = applied()
    assert {n.id for n in graph.nodes_of("UC")} == {"UC-01", "UC-02"}
    assert {n.id for n in graph.nodes_of("C4")} == {"C4-SYS", "C4-CNT-01", "C4-CNT-02", "C4-EXT-01"}
    realized = {e.dst for e in graph.edges if e.src == "FR-001" and e.rel.value == "realized_by"}
    assert {"UC-01", "UC-02", "C4-CNT-01", "C4-CNT-02", "C4-EXT-01"} <= realized
    uml = parse_use_cases(files[UML_FILE])
    assert ("UC-02", "UC-01", "extend") in uml.relations and uml.actors == (("ACT-01", "Пациент"),)
    c4 = parse_workspace(files[C4_FILE])
    assert c4.system is not None and c4.system.name == "Улыбка: запись к стоматологу"
    assert [p.id for p in c4.people] == ["ACT-01"] and c4.containers[1].database
    assert (c4.relations[0].src, c4.relations[0].dst) == ("ACT-01", "C4-CNT-01")


def test_the_graph_matches_the_files_it_is_saved_with(empty_project: Path) -> None:
    from reqgraph.dsl.readers import model_readers

    graph, files = applied()
    store = FileStore(empty_project, readers=model_readers())
    project = store.load()
    base = requirements()
    project = project.with_graph(graph)
    project = type(project)(project.root, project.config, graph, project.files | files)
    store.save(project)  # refuses a UC or C4 node that differs from its file
    loaded = store.load().graph
    assert {n.id for n in loaded.nodes_of("UC")} == {"UC-01", "UC-02"}
    assert loaded.nodes["UC-01"] == graph.nodes["UC-01"] and len(base.nodes_of("UC")) == 0


def test_unknown_requirements_actors_and_links_are_dropped() -> None:
    data = json.loads(json.dumps(VIEWS))
    data["use_cases"][0]["realizes"] = ["FR-099"]
    data["use_cases"][1]["actor"] = "ACT-09"
    data["c4"]["links"].append({"src": "cnt_web", "dst": "cnt_api", "label": "Вызывает"})
    update = to_views(draft(data), requirements(), {}, project_name="Улыбка")
    assert any("FR-099" in d for d in update.dropped)
    assert any("ACT-09" in d for d in update.dropped)  # the use case is not added
    assert any("cnt_web" in d for d in update.dropped)
    assert "Отменить запись" not in update.files[UML_FILE]


def test_one_use_case_is_changed_and_the_rest_stay() -> None:
    graph, files = applied()
    change = {"use_cases": [{"ref": "UC-02", "name": "Отменить приём", "actor": "ACT-01"}]}
    update = to_views(draft(change), graph, files, project_name="Улыбка")
    uml = parse_use_cases(update.files[UML_FILE])
    assert [u.name for u in uml.use_cases] == ["Записаться на приём", "Отменить приём"]
    assert ("UC-02", "UC-01", "extend") not in uml.relations  # the answer dropped extends
    assert C4_FILE not in update.files  # C4 untouched without a c4 answer
    after = graph.apply(update.patch, actor="agent").graph
    assert after.nodes["UC-02"].name == "Отменить приём"  # type: ignore[union-attr]


def test_problems_name_actors_without_use_cases_and_missing_c4() -> None:
    graph = requirements()
    assert view_problems(graph, {}) == [
        "ACT-01 Пациент: у роли нет ни одного сценария использования",
        "нет схемы C4: опишите систему, контейнеры и внешние системы (поле c4)",
    ]
    graph, files = applied()
    assert view_problems(graph, files) == []


async def test_the_views_step_retries_after_its_self_check(
    brief_context: Callable[..., RunContext],
) -> None:
    no_c4 = {"use_cases": VIEWS["use_cases"]}
    models = stub_models(analyst=DRAFT) | {
        "modeler": scripted(MODEL),
        "modeler_views": scripted(no_c4, VIEWS),
    }
    ctx = brief_context(models=models, max_iter=0)
    out = await build_graph().ainvoke(ctx.initial_state("brief", brief=BRIEF), context=ctx)
    checks = events_of(ctx, "views_check")
    assert [c["attempt"] for c in checks] == [1, 2]
    assert "нет схемы C4" in checks[0]["problems"][-1] and checks[1]["problems"] == []
    assert "C4-CNT-01" in out["graph"].nodes and C4_FILE in out["files"]
    assert not [f for f in out["ci"].findings if f.check_id == "TRC-003" and "UC" in f.node_ids[0]]


async def test_repair_tasks_on_use_cases_go_to_the_views_step(
    brief_context: Callable[..., RunContext],
) -> None:
    prompts: dict[str, list[str]] = {"modeler": [], "modeler_views": []}

    def answer(role: str, data: dict[str, Any]) -> FunctionModel:
        def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            prompts[role].append(str(messages[0]))
            return ModelResponse(parts=[TextPart(json.dumps(data, ensure_ascii=False))])

        return FunctionModel(fn)

    models = stub_models(analyst=DRAFT) | {
        "modeler": answer("modeler", MODEL),
        "modeler_views": answer("modeler_views", VIEWS),
    }
    ctx = brief_context(models=models, max_iter=0)
    state = ctx.initial_state("brief", brief=BRIEF)
    out = await build_graph().ainvoke(state, context=ctx)
    assert (
        "<use_cases>" in prompts["modeler_views"][0]
        and "integrations" in prompts["modeler_views"][0]
    )
    from reqgraph.agents.modeler import split_tasks

    tasks = [
        RepairTask(owner="modeler", node_ids=["UC-01"], check_ids=["TRC-003"], instruction="x"),
        RepairTask(owner="modeler", node_ids=["PRC-01"], check_ids=["SND-001"], instruction="y"),
    ]
    models_tasks, views_tasks = split_tasks(tasks)
    assert [t.node_ids for t in views_tasks] == [["UC-01"]]
    assert [t.node_ids for t in models_tasks] == [["PRC-01"]]
    assert "UC-01" in out["graph"].nodes
