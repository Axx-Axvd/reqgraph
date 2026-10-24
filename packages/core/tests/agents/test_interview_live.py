"""One real interview (free profile): the interviewer and the Analyst are real models, the answers
are scripted; replayed from a cassette without network (T-301).

Re-record after a deliberate change of the interviewer or Analyst prompts (needs network and keys;
in a cloud session the proxy injects them):
    uv run pytest packages/core/tests/agents/test_interview_live.py \\
        --record-mode=rewrite --force-enable-socket
"""

import json
from pathlib import Path

import pytest
from reqgraph.agents.coverage import coverage_of
from reqgraph.agents.interview import Reply, interview_project
from reqgraph.agents.nodes import DONE
from reqgraph.agents.run import init_project
from reqgraph.graph.store import FileStore

from .conftest import BRIEF, stub_models

pytestmark = [pytest.mark.anyio, pytest.mark.vcr]

ANSWERS: list[Reply] = [
    "Хотим, чтобы неявок стало вдвое меньше: с 10% до 5% записей за полгода.",
    "Если врач заболел, регистратор переносит его записи к другому врачу или на другой день "
    "и сообщает пациенту по SMS.",
    DONE,
]


async def test_live_interview_asks_by_coverage_and_counts_the_answers(tmp_path: Path) -> None:
    root = init_project(tmp_path / "ulybka", name="Улыбка", brief=BRIEF)
    asked: list[str] = []

    async def answer(question: str, turn: int) -> Reply:
        asked.append(question)
        return ANSWERS[turn - 1]

    stubs = stub_models()
    models = {"modeler": stubs["*"], "standards": stubs["standards"]}  # interviewer, Analyst real
    outcome = await interview_project(root, answer, models=models, offline=True, max_iter=0)
    assert not outcome.paused and outcome.turns == 2 and len(asked) == 3
    assert all(0 < len(q) <= 300 for q in asked), asked  # one short question, not a list
    assert len(set(asked)) == 3  # no question is asked twice
    events = [
        json.loads(line)
        for line in (root / "reports" / "interview-events.jsonl").read_text("utf-8").splitlines()
    ]
    calls = [e for e in events if e["type"] == "llm_call"]
    assert [c["role"] for c in calls if c["role"] in ("interviewer", "analyst")][:2] == [
        "analyst",  # the brief first
        "interviewer",
    ]
    assert {c["provider"] for c in calls if c["role"] == "analyst"} == {"gemini"}
    graph = FileStore(root).load().graph
    counted = coverage_of(graph)
    assert counted.got["goals"] + counted.got["exceptions"] >= 1  # the answers were counted
    coverage = [e for e in events if e["type"] == "coverage"]
    assert sum(coverage[-1]["got"].values()) > sum(coverage[0]["got"].values())
