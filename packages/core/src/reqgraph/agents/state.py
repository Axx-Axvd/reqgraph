"""State of one run: what LangGraph checkpoints after every node (03_agents, T-201).

Values are Pydantic models or plain data: the checkpointer stores them and they survive a restart
of the server. Everything that is not state (project files, models, the event log) is in the run
context (runtime.py).
"""

from typing import Literal, Self, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from reqgraph.checks.base import Owner
from reqgraph.checks.report import CIReport
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.llm.config import load_roles
from reqgraph.llm.router import RunBudget

Mode = Literal["interview", "brief", "check"]
Stop = Literal["budget", "needs_human"]

# Interview coverage areas and how many facts each needs (03_agents); counted by code in T-301.
AREAS: dict[str, int] = {
    "goals": 2,
    "stakeholders": 2,
    "scenarios": 4,
    "exceptions": 3,
    "data": 3,
    "rules": 3,
    "integrations": 1,
    "nfr": 4,
    "constraints": 2,
}


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Coverage(_Model):
    got: dict[str, int] = Field(default_factory=lambda: dict.fromkeys(AREAS, 0))
    need: dict[str, int] = Field(default_factory=lambda: dict(AREAS))

    @property
    def complete(self) -> bool:
        return all(self.got.get(area, 0) >= need for area, need in self.need.items())


class RepairTask(_Model):
    """What the Reviewer asks one agent to fix (05_ci, the repair loop)."""

    owner: Owner
    node_ids: list[str]
    instruction: str = Field(min_length=1)  # in Russian
    check_ids: list[str]


class BudgetState(_Model):
    """Limits and spending of the run: kept in the state, so a resumed run counts on."""

    usd: float = Field(gt=0)
    tokens: int = Field(gt=0)
    spent_usd: float = 0.0
    spent_tokens: int = 0

    @classmethod
    def default(cls) -> Self:
        """roles.yaml budget; REQGRAPH_RUN_BUDGET_USD overrides the dollars."""
        budget = load_roles().budget
        return cls(usd=budget.run_usd, tokens=budget.run_tokens)

    @classmethod
    def of(cls, budget: RunBudget) -> Self:
        return cls(
            usd=budget.usd,
            tokens=budget.tokens,
            spent_usd=budget.spent_usd,
            spent_tokens=budget.spent_tokens,
        )

    def to_run_budget(self) -> RunBudget:
        return RunBudget(self.usd, self.tokens, self.spent_usd, self.spent_tokens)


class RunState(TypedDict):
    mode: Mode
    brief: str | None  # brief mode: the text intake turns into client turns
    graph: ArtifactGraph
    files: dict[str, str]  # model texts written in this run (the ERD of the Modeler)
    coverage: Coverage
    question: str | None  # the interviewer's question waiting for an answer
    turns: int  # answered questions
    ci: CIReport | None
    history: list[list[str]]  # error fingerprints of every CI report of the run (repeat detector)
    tasks: list[RepairTask]
    iteration: int  # repair rounds done, 0..max_iter
    budget: BudgetState
    stop: Stop | None  # why the agents stopped early; the run still ends with a report


def initial_state(
    graph: ArtifactGraph,
    mode: Mode,
    *,
    budget: BudgetState | None = None,
    need: dict[str, int] | None = None,
    brief: str | None = None,
) -> RunState:
    coverage = Coverage() if need is None else Coverage(got=dict.fromkeys(need, 0), need=need)
    return RunState(
        mode=mode,
        brief=brief,
        graph=graph,
        files={},
        coverage=coverage,
        question=None,
        turns=0,
        ci=None,
        history=[],
        tasks=[],
        iteration=0,
        budget=budget or BudgetState.default(),
        stop=None,
    )
