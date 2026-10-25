"""The interview loop on stub models (T-301): an answer -> the Analyst -> coverage -> a question."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from reqgraph.agents.graph import build_graph
from reqgraph.agents.nodes import DONE
from reqgraph.agents.runtime import RunContext, checkpoint_serde
from reqgraph.agents.state import AREAS, RunState, initial_state

from .conftest import BRIEF, DRAFT, QUESTION, events_of, stub_models, visited

pytestmark = pytest.mark.anyio

THREAD: Any = {"configurable": {"thread_id": "interview-1"}}
NO_NEED = dict.fromkeys(AREAS, 0)


def recording(answers: list[dict[str, Any]], prompts: list[str]) -> FunctionModel:
    """A model that records its prompts and answers the next item (the last one repeats)."""

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompts.append(str(messages[-1].parts[-1].content))  # type: ignore[union-attr]
        data = answers[min(len(prompts) - 1, len(answers) - 1)]
        return ModelResponse(parts=[TextPart(json.dumps(data, ensure_ascii=False))])

    return FunctionModel(fn)


class Interview:
    """One interview over an in-memory checkpointer, answered step by step."""

    def __init__(self, ctx: RunContext, state: RunState) -> None:
        self.ctx, self.state = ctx, state
        self.graph = build_graph(checkpointer=InMemorySaver(serde=checkpoint_serde()))

    async def start(self) -> dict[str, Any]:
        return dict(await self.graph.ainvoke(self.state, THREAD, context=self.ctx))

    async def answer(self, answer: object) -> dict[str, Any]:
        resume: Command[Any] = Command(resume=answer)
        return dict(await self.graph.ainvoke(resume, THREAD, context=self.ctx))


def interview(ctx: RunContext, **kwargs: Any) -> Interview:
    return Interview(ctx, initial_state(ctx.project.graph, "interview", **kwargs))


async def test_the_analyst_reads_the_brief_then_only_each_new_answer(
    brief_context: Callable[..., RunContext],
) -> None:
    prompts: list[str] = []
    models = stub_models() | {"analyst": recording([{"requirements": []}], prompts)}
    ctx = brief_context(models=models, max_turns=2, max_iter=0)  # no repair rounds after it
    run = interview(ctx, brief=BRIEF)
    out = await run.start()
    assert out["__interrupt__"][0].value == {"question": QUESTION, "turn": 1}
    assert "Стоматологическая клиника" in prompts[0] and "только новые реплики" not in prompts[0]
    out = await run.answer("Врачей четверо: два терапевта, хирург и ортодонт.")
    assert "Врачей четверо" in prompts[1] and "Стоматологическая клиника" not in prompts[1]
    assert "только новые реплики" in prompts[1] and QUESTION in prompts[1]
    out = await run.answer("Отменять запись можно за 2 часа.")
    assert "__interrupt__" not in out and len(prompts) == 3
    assert "Отменять запись" in prompts[2] and "Врачей четверо" not in prompts[2]
    assert out["extracted_upto"] == "TURN-0006"  # 2 brief turns + 2 questions and 2 answers
    assert out["interview_done"] and out["turns"] == 2


async def test_reached_coverage_ends_the_interview_and_the_models_follow(
    brief_context: Callable[..., RunContext],
) -> None:
    actor = {"ref": "patient", "name": "Пациент", "sources": ["TURN-0002"]}  # the first answer
    ctx = brief_context(models=stub_models(analyst=DRAFT | {"actors": [actor]}), max_iter=0)
    need = NO_NEED | {"stakeholders": 1}
    run = interview(ctx, need=need)
    out = await run.start()  # no brief: nothing known yet, the first question
    assert out["__interrupt__"][0].value["turn"] == 1
    out = await run.answer("Пациенты записываются по телефону.")
    assert "__interrupt__" not in out
    assert out["coverage"].got["stakeholders"] == 1 and out["coverage"].complete
    assert [e["reason"] for e in events_of(ctx, "interview_end")] == ["coverage"]
    steps = visited(ctx)
    after = steps[len(steps) - steps[::-1].index("coverage") :]
    assert after[:3] == ["modeler", "standards", "ci_check"] and after[-1] == "persist"


async def test_done_ends_the_interview_without_a_turn_or_an_analyst_call(
    brief_context: Callable[..., RunContext],
) -> None:
    ctx = brief_context(models=stub_models(analyst=DRAFT), max_iter=0)
    run = interview(ctx)
    await run.start()
    out = await run.answer(DONE)
    assert "__interrupt__" not in out and out["turns"] == 0
    assert [n for n in out["graph"].nodes.values() if n.kind == "TURN"] == []
    assert [e["role"] for e in events_of(ctx, "llm_call")] == [
        "interviewer",
        "modeler",
        "standards",
    ]
    assert events_of(ctx, "interview_end")[0]["reason"] == "client"
    assert {"agent": "analyst", "reason": "нет новых ответов"} in [
        {k: e[k] for k in ("agent", "reason")} for e in events_of(ctx, "skip")
    ]


async def test_without_the_tracker_the_interviewer_decides_when_to_stop(
    brief_context: Callable[..., RunContext],
) -> None:
    prompts: list[str] = []
    asks: list[dict[str, Any]] = [{"text": QUESTION}, {"text": "Спасибо, всё ясно.", "done": True}]
    models = stub_models() | {"interviewer": recording(asks, prompts)}
    ctx = brief_context(models=models, interviewer="free")
    run = interview(ctx, need=NO_NEED)  # coverage is complete from the start: free mode ignores it
    out = await run.start()
    assert out["__interrupt__"][0].value["question"] == QUESTION
    assert "Покрытие" not in prompts[0]  # M1: no coverage in the prompt
    out = await run.answer("Записываются по телефону.")
    assert "__interrupt__" not in out and out["turns"] == 1
    assert events_of(ctx, "interview_end")[0]["reason"] == "interviewer"


async def test_question_events_name_the_area_but_keep_no_texts(
    brief_context: Callable[..., RunContext],
) -> None:
    models = stub_models() | {
        "interviewer": TestModel(custom_output_args={"text": QUESTION, "area": "exceptions"})
    }
    ctx = brief_context(models=models, max_turns=1)
    run = interview(ctx)
    await run.start()
    await run.answer("Если врач заболел, регистратор обзванивает пациентов.")
    (question,) = events_of(ctx, "question")
    assert question == {"type": "question", "turn": 1, "area": "exceptions"}
    text = json.dumps(events_of(ctx, "coverage") + events_of(ctx, "answer"), ensure_ascii=False)
    assert "заболел" not in text and QUESTION not in text


async def test_a_failed_analyst_call_keeps_the_turns_for_the_next_answer(
    brief_context: Callable[..., RunContext],
) -> None:
    from pydantic_ai.exceptions import ModelHTTPError

    prompts: list[str] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompts.append(str(messages[-1].parts[-1].content))  # type: ignore[union-attr]
        if len(prompts) == 1:
            raise ModelHTTPError(503, "analyst")  # the whole ladder is down on this answer
        return ModelResponse(parts=[TextPart(json.dumps({"requirements": []}))])

    models = stub_models() | {"analyst": FunctionModel(fn)}
    ctx = brief_context(models=models, max_turns=2, max_iter=0)
    run = interview(ctx)
    await run.start()
    out = await run.answer("Записываются по телефону.")
    assert out["__interrupt__"][0].value["turn"] == 2  # the interview goes on
    assert events_of(ctx, "llm_failed")[0]["agent"] == "analyst"
    out = await run.answer("Неявок около 10%.")
    assert "Записываются по телефону" in prompts[1] and "Неявок около 10%" in prompts[1]
