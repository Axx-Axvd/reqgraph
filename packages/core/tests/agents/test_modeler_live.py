"""Real Analyst and Modeler answers (free profile), replayed from a cassette offline (T-203).

Re-record after a deliberate change of a prompt or of a draft schema (needs network and a key):
    uv run pytest packages/core/tests/agents/test_modeler_live.py \\
        --record-mode=rewrite --force-enable-socket
"""

from collections.abc import Callable

import pytest
from reqgraph.agents.graph import build_graph
from reqgraph.agents.runtime import RunContext

from .conftest import BRIEF, events_of, stub_models

pytestmark = [pytest.mark.anyio, pytest.mark.vcr]


async def test_live_modeler_answer_builds_clean_models(
    brief_context: Callable[..., RunContext],
) -> None:
    stubs = stub_models()
    models = {"interviewer": stubs["interviewer"], "standards": stubs["*"]}  # Analyst, Modeler real
    ctx = brief_context(models=models, max_iter=0)
    out = await build_graph().ainvoke(ctx.initial_state("brief", brief=BRIEF), context=ctx)
    (end,) = [e for e in events_of(ctx, "agent_end") if e["agent"] == "modeler"]
    assert end["attempts"] <= 3
    graph = out["graph"]
    assert graph.nodes_of("PRC") and graph.nodes_of("ENT")
    found = {f.check_id for f in out["ci"].findings if f.severity == "error"}
    assert not found & {"SCH-001", "SCH-002", "SCH-003", "SND-001", "TRC-002", "TRC-004"}
