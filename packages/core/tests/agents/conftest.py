"""Runs of the agent graph on stub models (pydantic-ai TestModel): no network, no money."""

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.models import Model
from pydantic_ai.models.test import TestModel
from reqgraph.agents.runtime import MemoryEvents, RunContext
from reqgraph.dsl.readers import model_readers
from reqgraph.graph import ArtifactGraph, GraphPatch
from reqgraph.graph.store import FileStore

GARAGE61 = Path(__file__).resolve().parents[4] / "examples" / "garage61"
QUESTION = "Как клиенты записываются на обслуживание сейчас?"
SRS = {
    "purpose": "Система онлайн-записи для клиентов и сотрудников.",
    "scope": "Запись, напоминания и отмена; оплата — вне системы.",
    "glossary": [{"term": "Запись", "definition": "забронированное время у мастера"}],
}


def stub_models(**patches: dict[str, Any]) -> dict[str, Model]:
    """Every agent answers an empty patch, the interviewer asks QUESTION; overrides by role."""
    models: dict[str, Model] = {
        "*": TestModel(custom_output_args={"ops": []}),
        "interviewer": TestModel(custom_output_args={"text": QUESTION}),
        "standards": TestModel(custom_output_args=SRS),
    }
    for role, patch in patches.items():
        models[role] = TestModel(custom_output_args=patch)
    return models


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def garage61(tmp_path: Path) -> Path:
    """A copy that agents may work on: persist writes it back, the reference stays untouched."""
    folder = Path(shutil.copytree(GARAGE61, tmp_path / "garage61"))
    config = folder / "reqgraph.yaml"
    text = config.read_text(encoding="utf-8")
    config.write_text(text.replace("reference: true", "reference: false", 1), encoding="utf-8")
    return folder


@pytest.fixture
def context(garage61: Path) -> Callable[..., RunContext]:
    def make(**overrides: Any) -> RunContext:
        store = FileStore(garage61, readers=model_readers())
        options: dict[str, Any] = {
            "store": store,
            "events": MemoryEvents(),
            "models": stub_models(),
            "offline": True,
        }
        return RunContext.for_project(store.load(), **(options | overrides))

    return make


def visited(ctx: RunContext) -> list[str]:
    assert isinstance(ctx.events, MemoryEvents)
    return [e["node"] for e in ctx.events.events if e["type"] == "node_start"]


def events_of(ctx: RunContext, kind: str) -> list[dict[str, Any]]:
    assert isinstance(ctx.events, MemoryEvents)
    return [e for e in ctx.events.events if e["type"] == kind]


# --- a fresh project from a brief (T-202, T-203) -------------------------------------------

BRIEF = """# Бриф: «Улыбка»

Стоматологическая клиника, 3 кресла. Пациенты записываются по телефону.

Нужна онлайн-запись и напоминание за сутки до приёма.
"""

DRAFT: dict[str, Any] = {
    "actors": [{"ref": "patient", "name": "Пациент", "sources": ["TURN-0001"]}],
    "requirements": [
        {
            "ref": "br_online",
            "kind": "BR",
            "title": "Онлайн-запись",
            "statement": "Доля онлайн-записей должна вырасти с 0% до 50% за 6 месяцев.",
            "goal_metric": {"name": "доля онлайн-записей", "unit": "%", "target": ">= 50"},
            "sources": ["TURN-0002"],
        },
        {
            "ref": "ur_book",
            "kind": "UR",
            "title": "Запись на приём",
            "statement": "Пациент записывается на приём через сайт.",
            "actor": "patient",
            "scenario": ["выбирает врача", "выбирает время"],
            "refines": ["br_online"],
            "sources": ["TURN-0002"],
        },
        {
            "ref": "fr_remind",
            "kind": "FR",
            "title": "Напоминание",
            "statement": "За 24 часа до приёма система должна отправить пациенту SMS-напоминание.",
            "acceptance": ["SMS уходит за 24 ± 1 час до приёма"],
            "refines": ["ur_book"],
            "sources": ["TURN-0002"],
        },
        {
            "ref": "nfr_sms",
            "kind": "NFR",
            "title": "Доставка SMS",
            "statement": "Доля доставленных SMS должна быть не ниже 98% за месяц.",
            "iso25010": "reliability",
            "metric": {
                "name": "доля доставленных SMS",
                "unit": "%",
                "threshold": ">= 98",
                "method": "отчёт SMS-шлюза за месяц",
            },
            "refines": ["ur_book"],
            "sources": ["TURN-0002"],
        },
        {
            "ref": "con_pd",
            "kind": "CON",
            "constraint_type": "legal",
            "title": "Персональные данные",
            "statement": "Данные пациентов хранятся на территории РФ (152-ФЗ).",
            "assumption": True,
        },
    ],
}


def turns_graph() -> ArtifactGraph:
    texts = BRIEF.split("\n\n")[1:]
    ops = [
        {"op": "add", "kind": "TURN", "tmp_id": f"t{i}", "fields": {"role": "client", "text": t}}
        for i, t in enumerate(texts)
    ]
    return ArtifactGraph.empty().apply(GraphPatch.model_validate({"ops": ops})).graph


@pytest.fixture
def empty_project(tmp_path: Path) -> Path:
    folder = tmp_path / "dev"
    folder.mkdir()
    text = 'project:\n  id: dev-test\n  name: "Улыбка"\nmodels:\n  profile: free\n'
    (folder / "reqgraph.yaml").write_text(text, encoding="utf-8")
    return folder


@pytest.fixture
def brief_context(empty_project: Path) -> Callable[..., RunContext]:
    def make(**overrides: Any) -> RunContext:
        store = FileStore(empty_project, readers=model_readers())
        options: dict[str, Any] = {"store": store, "events": MemoryEvents(), "offline": True}
        options["models"] = stub_models(analyst=DRAFT)
        return RunContext.for_project(store.load(), **(options | overrides))

    return make
