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
from reqgraph.graph.store import FileStore

GARAGE61 = Path(__file__).resolve().parents[4] / "examples" / "garage61"
QUESTION = "Как клиенты записываются на обслуживание сейчас?"


def stub_models(**patches: dict[str, Any]) -> dict[str, Model]:
    """Every agent answers an empty patch, the interviewer asks QUESTION; overrides by role."""
    models: dict[str, Model] = {
        "*": TestModel(custom_output_args={"ops": []}),
        "interviewer": TestModel(custom_output_args={"text": QUESTION}),
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
