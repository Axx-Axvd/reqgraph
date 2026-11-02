"""The judge again on the author's labels (T-310), on a stub judge: no network."""

import pytest
from reqgraph.llm.router import CallStats
from reqgraph_evals import judgeprobe, simprobe
from reqgraph_evals.metrics.recall import Verdict

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_the_labelled_sets_are_the_authors() -> None:
    sizes = [len(judgeprobe.labelled(p)) for p in judgeprobe.SETS]
    assert sizes == [28, 15]
    ref = judgeprobe.labelled(judgeprobe.SETS[0])[0]
    assert ref["human"] in ("full", "partial", "none") and ref["candidates"]


async def test_a_judge_that_copies_the_person_agrees_fully() -> None:
    refs = judgeprobe.labelled(judgeprobe.SETS[0])
    by_text = {r["hidden"]: r["human"] for r in refs}
    stats = CallStats("judge", "m", "p", 10, 3, 1, 0.001, None, 5, "ok")

    async def judge(reference: str, candidates: list[str]) -> tuple[Verdict, CallStats | None]:
        level = by_text[reference]
        return Verdict(matches=[] if level == "none" else [1], level=level), stats

    rows = await judgeprobe.rejudge(refs, judge)
    got = judgeprobe.scores(rows)
    assert got["references"] == 28 and got["agreement"] == 1.0 and got["kappa"] == 1.0
    assert got["output_tokens"] == 3 * 28 and got["cost_usd"] == pytest.approx(0.028)


def test_the_reasoning_mode_goes_into_roles_for_the_model_only() -> None:
    from reqgraph.llm import router
    from reqgraph.llm.config import Step

    cfg = router._config()
    before = dict(cfg.model_settings)
    try:
        simprobe.set_reasoning(["openrouter/qwen/qwen3.8-27b"], "off")
        assert cfg.extra_body(Step.parse("openrouter/qwen/qwen3.8-27b")) == {
            "reasoning": {"enabled": False}
        }
        simprobe.set_reasoning(["openrouter/qwen/qwen3.8-27b"], "on")
        assert cfg.extra_body(Step.parse("openrouter/qwen/qwen3.8-27b")) is None
    finally:
        cfg.model_settings = before
