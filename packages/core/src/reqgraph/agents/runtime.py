"""Run context: what nodes use but the checkpointer does not store (LangGraph context_schema).

The project files (for the checks), the store to persist into, stub or pinned models, the event
log and the limits of the run. Events never carry prompts, answers or keys: only who, what model,
how many tokens and how much money (CLAUDE.md, security).
"""

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic_ai.models import Model

from reqgraph.agents.state import (
    BudgetState,
    Coverage,
    Mode,
    RepairTask,
    RunState,
    initial_state,
)
from reqgraph.checks.report import CIReport
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.store.base import ProjectStore
from reqgraph.graph.store.project import Project
from reqgraph.llm.router import structured


class EventSink(Protocol):
    def emit(self, type: str, **payload: Any) -> None: ...


@dataclass
class MemoryEvents:
    """Events in a list: tests and the CLI summary."""

    events: list[dict[str, Any]] = field(default_factory=list)

    def emit(self, type: str, **payload: Any) -> None:
        self.events.append({"type": type, **payload})


@dataclass
class JsonlEvents:
    """One JSON object per line, appended: the offline form of run_events (02_arch)."""

    path: Path

    def emit(self, type: str, **payload: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        event = {"type": type, "ts": datetime.now(UTC).isoformat(), **payload}
        with self.path.open("a", encoding="utf-8") as out:
            out.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


@dataclass
class RunContext:
    project: Project  # files of the models for the checks; the graph itself lives in the state
    store: ProjectStore | None = None  # persist saves here; None — nothing is written
    events: EventSink = field(default_factory=MemoryEvents)
    models: Mapping[str, Model] = field(default_factory=dict)  # role (or "*") -> stub model
    profile: str | None = None  # roles.yaml profile; None — the default one
    offline: bool = False  # checks without Kroki
    max_iter: int = 5  # repair rounds (05_ci)
    max_turns: int = 40  # interview questions (03_agents)

    @classmethod
    def for_project(cls, project: Project, **options: Any) -> "RunContext":
        """Limits and the model profile from reqgraph.yaml; options override them."""
        config = project.config
        settings: dict[str, Any] = {
            "profile": config.models.profile,
            "max_iter": config.checks.max_iterations,
            "max_turns": config.interview.max_turns,
        }
        return cls(project=project, **(settings | options))

    def initial_state(self, mode: Mode, *, budget: BudgetState | None = None) -> RunState:
        """The project graph and the coverage thresholds of reqgraph.yaml."""
        need = {str(area): n for area, n in self.project.config.interview.coverage_need.items()}
        return initial_state(self.project.graph, mode, budget=budget, need=need or None)

    async def ask[T](
        self, role: str, prompt: str, output_type: type[T], budget: BudgetState
    ) -> tuple[T, BudgetState]:
        """One LLM call through llm/ (ADR-013): budget checked and counted, an llm_call event."""
        run_budget = budget.to_run_budget()
        output, stats = await structured(
            role,
            prompt,
            output_type,
            profile=self.profile,
            budget=run_budget,
            model=self.models.get(role) or self.models.get("*"),
        )
        self.events.emit("llm_call", **asdict(stats))
        return output, BudgetState.of(run_budget)


STATE_TYPES: tuple[type, ...] = (ArtifactGraph, CIReport, Coverage, RepairTask, BudgetState)


def checkpoint_serde() -> JsonPlusSerializer:
    """The checkpointer may restore only our state types (LangGraph blocks unknown ones)."""
    return JsonPlusSerializer(
        allowed_msgpack_modules=[(t.__module__, t.__name__) for t in STATE_TYPES]
    )
