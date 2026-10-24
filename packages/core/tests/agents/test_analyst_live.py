"""One real Analyst answer (free profile, Gemini), replayed from a cassette without network (T-202).

Re-record after a deliberate change of the prompt or of AnalystDraft (needs network and a key;
in a cloud session the proxy injects it):
    uv run pytest packages/core/tests/agents/test_analyst_live.py \\
        --record-mode=rewrite --force-enable-socket
"""

from collections.abc import Callable

import pytest
from reqgraph.agents.graph import build_graph
from reqgraph.agents.runtime import RunContext
from reqgraph.checks.runner import run_checks

from .conftest import events_of, stub_models
from .test_analyst import BRIEF, brief_context, empty_project  # noqa: F401 - fixtures

pytestmark = [pytest.mark.anyio, pytest.mark.vcr]


async def test_live_analyst_answer_makes_a_valid_traceable_patch(
    brief_context: Callable[..., RunContext],  # noqa: F811
) -> None:
    models = {k: v for k, v in stub_models().items() if k != "*"}  # the Analyst is real
    models["modeler"] = models["standards"] = stub_models()["*"]
    ctx = brief_context(models=models)
    out = await build_graph().ainvoke(ctx.initial_state("brief", brief=BRIEF), context=ctx)
    (call,) = [e for e in events_of(ctx, "llm_call") if e["role"] == "analyst"][:1]
    assert call["provider"] == "gemini"
    assert events_of(ctx, "agent_end")[0]["agent"] == "analyst"
    graph = out["graph"]
    requirements = [n for n in graph.nodes.values() if n.kind in ("BR", "UR", "FR", "NFR", "CON")]
    assert len(requirements) >= 5
    report = await run_checks(ctx.project.with_graph(graph), offline=True)
    assert [f for f in report.findings if f.check_id in ("TRC-001", "TRC-006")] == []
    violating = {
        n for f in report.findings if f.check_id in ("ISO-001", "ISO-003") for n in f.node_ids
    }
    assert len(violating) <= 0.15 * len(requirements)
