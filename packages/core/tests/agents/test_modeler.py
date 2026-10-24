"""Modeler (T-203): draft -> processes and ERD with ids from code, self-check and retries."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from reqgraph.agents.analyst import AnalystDraft, to_patch
from reqgraph.agents.graph import build_graph
from reqgraph.agents.modeler import ERD_FILE, MAX_ATTEMPTS, ModelerDraft, to_models
from reqgraph.agents.runtime import RunContext
from reqgraph.dsl.readers import model_readers
from reqgraph.graph import ArtifactGraph
from reqgraph.graph.nodes import ProcessNode
from reqgraph.graph.patch import LinkOp
from reqgraph.graph.store import FileStore

from .conftest import BRIEF, DRAFT, events_of, stub_models, turns_graph

pytestmark = pytest.mark.anyio

PROCESS: dict[str, Any] = {
    "ref": "prc_remind",
    "name": "Напоминание о приёме",
    "refines": ["UR-001"],
    "lanes": ["Система"],
    "nodes": [
        {
            "id": "S",
            "type": "start",
            "name": "За сутки до приёма",
            "event": "timer",
            "timer": "visit.starts_at - PT24H",
            "lane": "Система",
        },
        {
            "id": "T01",
            "type": "service_task",
            "name": "Отправить SMS",
            "lane": "Система",
            "realizes": ["FR-001"],
        },
        {"id": "E1", "type": "end", "name": "Напоминание отправлено", "lane": "Система"},
    ],
    "flows": [{"src": "S", "dst": "T01"}, {"src": "T01", "dst": "E1"}],
}
ENTITIES: list[dict[str, Any]] = [
    {
        "ref": "ent_patient",
        "name": "Пациент",
        "table": "patient",
        "columns": [
            {"name": "id", "type": "int", "pk": True},
            {"name": "phone", "type": "varchar"},
        ],
    },
    {
        "ref": "ent_visit",
        "name": "Приём",
        "table": "visit",
        "columns": [
            {"name": "id", "type": "int", "pk": True},
            {"name": "patient_id", "type": "int", "not_null": True, "ref": "patient.id"},
            {"name": "starts_at", "type": "timestamp", "not_null": True},
        ],
        "realizes": ["FR-001"],
    },
]
MODEL: dict[str, Any] = {"processes": [PROCESS], "entities": ENTITIES}


def requirements() -> ArtifactGraph:
    graph = turns_graph()
    return graph.apply(to_patch(AnalystDraft.model_validate(DRAFT), graph).patch).graph


def broken(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(json.dumps(MODEL))
    for key, value in changes.items():
        data["processes"][0][key] = value
    return data


def scripted(*answers: dict[str, Any]) -> FunctionModel:
    calls: list[int] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(1)
        answer = answers[min(len(calls), len(answers)) - 1]
        return ModelResponse(parts=[TextPart(json.dumps(answer, ensure_ascii=False))])

    return FunctionModel(fn, model_name="scripted")


def test_ids_and_links_are_issued_by_code(tmp_path: Path) -> None:
    graph = requirements()
    update = to_models(ModelerDraft.model_validate(MODEL), graph, {})
    assert update.dropped == []
    assert update.ids == {"prc_remind": "PRC-01", "ent_patient": "ENT-01", "ent_visit": "ENT-02"}
    result = graph.apply(update.patch, actor="agent")  # predicted ids are the ones apply() issues
    new = result.graph
    process = new.nodes["PRC-01"]
    assert isinstance(process, ProcessNode) and (process.dsl or {})["id"] == "PRC-01"
    assert new.nodes["ENT-02"].name == "Приём"  # type: ignore[union-attr]
    realized = {e.dst for e in new.edges if e.src == "FR-001" and e.rel.value == "realized_by"}
    assert realized == {"PRC-01.T01", "ENT-02"}
    text = update.files[ERD_FILE]
    assert "Note: 'ENT-02 · Приём'" in text and "Ref: visit.patient_id > patient.id" in text

    # the project with the ERD file is written and read back unchanged
    (tmp_path / "reqgraph.yaml").write_text('project:\n  id: t\n  name: "t"\n', encoding="utf-8")
    store = FileStore(tmp_path, readers=model_readers())
    project = store.load()
    store.save(type(project)(project.root, project.config, new, files=project.files | update.files))
    assert store.load().graph == new


def test_dsl_errors_are_reported_with_the_drafts_ref() -> None:
    bad = broken(flows=[{"src": "S", "dst": "T99"}])
    update = to_models(ModelerDraft.model_validate(bad), requirements(), {})
    (error,) = update.dropped
    assert error.startswith("процесс prc_remind: ") and "стрелка S -> T99: шага T99 нет" in error
    assert "prc_remind" not in update.ids


def test_unknown_table_in_a_reference_is_a_dbml_error() -> None:
    data = json.loads(json.dumps(MODEL))
    data["entities"][1]["columns"][1]["ref"] = "doctor.id"
    update = to_models(ModelerDraft.model_validate(data), requirements(), {})
    assert update.files == {} and "doctor" in update.dropped[0]
    assert update.ids == {"prc_remind": "PRC-01"}  # the process still goes in
    requirements().apply(update.patch, actor="agent")
    links = [o for o in update.patch.ops if isinstance(o, LinkOp)]
    assert not any(o.dst.startswith("ENT") for o in links)


def test_unknown_requirements_are_dropped() -> None:
    bad = broken(refines=["UR-099"])
    bad["entities"][1]["realizes"] = ["FR-099"]
    update = to_models(ModelerDraft.model_validate(bad), requirements(), {})
    assert update.dropped == [
        "prc_remind: refines UR-099 — таких ПТ нет",
        "ent_visit: FR-099 — такого ФТ нет",
    ]


def test_existing_process_is_updated_and_lost_steps_unlinked() -> None:
    graph = requirements()
    graph = graph.apply(to_models(ModelerDraft.model_validate(MODEL), graph, {}).patch).graph
    changed = broken(ref="PRC-01")
    changed["processes"][0]["nodes"][1] |= {"id": "T02"}
    changed["processes"][0]["flows"] = [{"src": "S", "dst": "T02"}, {"src": "T02", "dst": "E1"}]
    changed["entities"] = []
    update = to_models(ModelerDraft.model_validate(changed), graph, {})
    new = graph.apply(update.patch, actor="agent").graph
    realized = {e.dst for e in new.edges if e.src == "FR-001"}
    assert "PRC-01.T02" in realized and "PRC-01.T01" not in realized


async def test_modeler_fixes_its_dsl_after_the_self_check(
    brief_context: Callable[..., RunContext], empty_project: Path
) -> None:
    models = stub_models(analyst=DRAFT) | {
        "modeler": scripted(broken(flows=[{"src": "S", "dst": "T99"}]), MODEL)
    }
    ctx = brief_context(models=models, max_iter=0)  # one pass, no repair rounds
    out = await build_graph().ainvoke(ctx.initial_state("brief", brief=BRIEF), context=ctx)
    checks = events_of(ctx, "self_check")
    assert [c["attempt"] for c in checks] == [1, 2]
    assert "T99" in checks[0]["problems"][0] and checks[1]["problems"] == []
    assert events_of(ctx, "agent_end")[1] | {"diff": None} == {
        "type": "agent_end",
        "agent": "modeler",
        "attempts": 2,
        "diff": None,
    }
    assert "PRC-01" in out["graph"].nodes and ERD_FILE in out["files"]
    assert (empty_project / ERD_FILE).is_file()  # persisted with the project
    assert not [f for f in out["ci"].findings if f.check_id in ("SCH-002", "TRC-002")]


async def test_after_three_failures_the_best_attempt_is_applied(
    brief_context: Callable[..., RunContext],
) -> None:
    dead_end = broken(
        nodes=[
            *PROCESS["nodes"],
            {
                "id": "T02",
                "type": "task",
                "name": "Лишний",
                "lane": "Система",
                "realizes": ["FR-001"],
            },
        ],
    )
    models = stub_models(analyst=DRAFT) | {"modeler": scripted(dead_end)}
    ctx = brief_context(models=models, max_iter=0)
    out = await build_graph().ainvoke(ctx.initial_state("brief", brief=BRIEF), context=ctx)
    assert len(events_of(ctx, "self_check")) == MAX_ATTEMPTS
    (dropped,) = [e for e in events_of(ctx, "dropped") if e["agent"] == "modeler"]
    assert any(p.startswith("SND-001") for p in dropped["reasons"])
    assert "PRC-01" in out["graph"].nodes  # the run goes on: CI and repair will see it


async def test_prompt_has_the_one_page_rule_and_the_requirements(
    brief_context: Callable[..., RunContext],
) -> None:
    seen: list[str] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(str(messages[0]))
        return ModelResponse(parts=[TextPart(json.dumps(MODEL, ensure_ascii=False))])

    models = stub_models(analyst=DRAFT) | {"modeler": FunctionModel(fn)}
    ctx = brief_context(models=models)
    await build_graph().ainvoke(ctx.initial_state("brief", brief=BRIEF), context=ctx)
    assert "одну страницу" in seen[0] and "не больше 12 шагов" in seen[0]
    assert "FR-001: Напоминание" in seen[0] and "<requirements>" in seen[0]
