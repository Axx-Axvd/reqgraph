"""A real Standards answer (free profile), replayed from a cassette without network (T-204).

Re-record after a deliberate change of the prompt or of StandardsDraft (needs network and a key):
    uv run pytest packages/core/tests/agents/test_standards_live.py \\
        --record-mode=rewrite --force-enable-socket
"""

from collections.abc import Callable

import pytest
from reqgraph.agents.graph import build_graph
from reqgraph.agents.runtime import RunContext
from reqgraph.graph.nodes import SectionNode

from .conftest import BRIEF, DRAFT, events_of, stub_models
from .test_modeler import MODEL

pytestmark = [pytest.mark.anyio, pytest.mark.vcr]


async def test_live_standards_answer_fills_the_srs(
    brief_context: Callable[..., RunContext],
) -> None:
    stubs = stub_models(analyst=DRAFT, modeler=MODEL)
    models = {k: v for k, v in stubs.items() if k not in ("standards", "*")}  # Standards is real
    ctx = brief_context(models=models, max_iter=0)
    out = await build_graph().ainvoke(ctx.initial_state("brief", brief=BRIEF), context=ctx)
    (call,) = [e for e in events_of(ctx, "llm_call") if e["role"] == "standards"][:1]
    assert call["prompt"] == "standards/srs"
    empty = {f.node_ids[0] for f in out["ci"].findings if f.check_id == "TPL-001"}
    assert empty <= {"SEC-SRS-1.3"}  # the stub Analyst has an actor; the LLM fills the rest
    glossary = out["graph"].nodes["SEC-SRS-1.4"]
    assert isinstance(glossary, SectionNode) and glossary.text.count("\n") >= 2
