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


def interviewer(
    marks: list[str], asks: list[dict[str, Any]], prompts: list[str], mark_prompts: list[str]
) -> FunctionModel:
    """The coverage interviewer: the mark of the latest answer, then the question (T-317); each
    list answers in turn, its last item repeats."""

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompt = str(messages[-1].parts[-1].content)  # type: ignore[union-attr]
        seen, items = (mark_prompts, marks) if MARK in prompt else (prompts, asks)
        seen.append(prompt)
        item = items[min(len(seen) - 1, len(items) - 1)]
        data = {"previous": item} if isinstance(item, str) else item
        return ModelResponse(parts=[TextPart(json.dumps(data, ensure_ascii=False))])

    return FunctionModel(fn)


MARK = "# Отметка ответа"


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
    ask = {"text": QUESTION, "area": "stakeholders"}  # the only area is asked: coverage may end it
    models = stub_models(analyst=DRAFT | {"actors": [actor]}, interviewer=ask)
    ctx = brief_context(models=models, max_iter=0)
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
        "interviewer": TestModel(custom_output_args={"text": QUESTION, "area": "goals"})
    }
    ctx = brief_context(models=models, max_turns=1)
    run = interview(ctx, need=NO_NEED | {"exceptions": 1})  # the code picks the area (T-317)
    await run.start()
    await run.answer("Если врач заболел, регистратор обзванивает пациентов.")
    (question,) = events_of(ctx, "question")
    assert question == {
        "type": "question",
        "turn": 1,
        "area": "exceptions",
        "previous": None,
        "step": 0,
        "mode": "new",
    }
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


async def test_the_interview_ends_when_every_open_area_told_nothing(
    brief_context: Callable[..., RunContext],
) -> None:
    asks = [{"text": "Чего вы хотите добиться?", "area": "goals"}]
    models = stub_models(analyst={"requirements": []}) | {"interviewer": recording(asks, [])}
    ctx = brief_context(models=models, max_turns=10, max_iter=0)
    run = interview(ctx, need=NO_NEED | {"goals": 1})
    await run.start()
    out = await run.answer("Пока не думали.")  # nothing new: the only open area is closed
    assert "__interrupt__" not in out and out["turns"] == 1
    assert [e["reason"] for e in events_of(ctx, "interview_end")] == ["saturated"]


async def test_the_interviewer_sees_what_is_known_of_the_area_it_asks_about(
    brief_context: Callable[..., RunContext],
) -> None:
    prompts: list[str] = []
    asks = [{"text": "Чего вы хотите добиться?", "area": "goals"}]
    models = stub_models(analyst=DRAFT) | {"interviewer": interviewer(["ok"], asks, prompts, [])}
    ctx = brief_context(models=models, max_turns=2, max_iter=0)
    run = interview(ctx, need=NO_NEED | {"goals": 2})
    await run.start()
    assert "goals ещё не спрашивали" in prompts[0]
    await run.answer("Хотим, чтобы половина записей шла через сайт за полгода.")
    assert "goals уже спрашивали" in prompts[1]
    assert "Доля онлайн-записей должна вырасти с 0% до 50% за 6 месяцев." in prompts[1]


async def test_saturation_waits_for_every_area_to_be_asked_once(
    brief_context: Callable[..., RunContext],
) -> None:
    con = {**DRAFT["requirements"][-1], "assumption": False, "sources": ["TURN-0001"]}
    analyst = recording([{"requirements": [con]}, {"requirements": []}], [])  # the brief tells it
    asks = [{"text": "Чего вы хотите добиться?", "area": "goals"}]
    models = stub_models() | {"analyst": analyst, "interviewer": recording(asks, [])}
    ctx = brief_context(models=models, max_turns=10, max_iter=0)
    run = interview(ctx, brief=BRIEF, need=NO_NEED | {"goals": 1, "constraints": 1})
    await run.start()
    out = await run.answer(
        "Пока не думали."
    )  # goals is closed; constraints are covered, never asked
    assert out["__interrupt__"][0].value["turn"] == 2


async def test_coverage_from_the_brief_ends_the_interview_only_after_every_area_is_asked(
    brief_context: Callable[..., RunContext],
) -> None:
    """T-318: a rich brief fills every area at once; the interview still asks about each one
    (the rule of T-305), and only then ends by coverage."""
    actor = {"ref": "patient", "name": "Пациент", "sources": ["TURN-0001"]}
    con = {**DRAFT["requirements"][-1], "assumption": False, "sources": ["TURN-0001"]}
    analyst = recording([{"actors": [actor], "requirements": [con]}, {"requirements": []}], [])
    asks = [
        {"text": "Кто ещё работает с записью?", "area": "stakeholders"},
        {"text": "Есть ли сроки или бюджет?", "area": "constraints"},
    ]
    models = stub_models() | {"analyst": analyst, "interviewer": recording(asks, [])}
    ctx = brief_context(models=models, max_turns=10, max_iter=0)
    run = interview(ctx, brief=BRIEF, need=NO_NEED | {"stakeholders": 1, "constraints": 1})
    out = await run.start()  # the brief covers both areas, neither has been asked
    assert out["__interrupt__"][0].value["turn"] == 1
    out = await run.answer("Только администратор.")
    assert out["__interrupt__"][0].value["turn"] == 2  # constraints: covered, never asked
    out = await run.answer("Запуститься к весне.")
    assert "__interrupt__" not in out and out["turns"] == 2
    assert [e["reason"] for e in events_of(ctx, "interview_end")] == ["coverage"]


async def test_the_questionnaire_asks_its_fixed_questions_without_an_llm(
    brief_context: Callable[..., RunContext],
) -> None:
    """T-405, B3: the questions come one by one from interviewer/questionnaire.md, no model asks;
    the interview ends when they run out."""
    from reqgraph.agents.nodes import questionnaire

    questions = questionnaire()
    assert 10 <= len(questions) <= 15
    ctx = brief_context(interviewer="questionnaire")
    run = interview(ctx, need=NO_NEED)
    out = await run.start()
    asked = [out["__interrupt__"][0].value["question"]]
    for _ in range(len(questions)):
        out = await run.answer("Не знаю.")
        if "__interrupt__" in out:
            asked.append(out["__interrupt__"][0].value["question"])
    assert asked == questions
    assert "interviewer" not in [e["role"] for e in events_of(ctx, "llm_call")]
    assert events_of(ctx, "interview_end")[0]["reason"] == "questionnaire"


async def test_a_client_who_did_not_understand_is_asked_again_in_simpler_words(
    brief_context: Callable[..., RunContext],
) -> None:
    prompts: list[str] = []
    marks: list[str] = []
    asks = [
        {"text": "Нужна ли интеграция с 1С?", "area": "integrations"},
        {"text": "Нужно, чтобы записи сами попадали в 1С?", "area": "goals"},  # the code decides
        {"text": "Чего вы хотите добиться?", "area": "goals"},
    ]
    model = interviewer(["not_understood", "ok", "ok"], asks, prompts, marks)
    models = stub_models(analyst={"requirements": []}) | {"interviewer": model}
    ctx = brief_context(models=models, max_turns=10, max_iter=0)
    run = interview(ctx, need=NO_NEED | {"integrations": 2, "goals": 1})
    out = await run.start()
    assert not marks  # nothing to mark before the first question
    out = await run.answer("Не понимаю, что такое интеграция.")
    assert out["__interrupt__"][0].value["turn"] == 2  # the area is not closed: asked again
    assert "Не понимаю, что такое интеграция." in marks[0]
    assert "integrations" in prompts[1] and "ступени 1" in prompts[1]
    out = await run.answer("Да, хорошо бы.")  # understood, nothing new: integrations closes
    assert out["__interrupt__"][0].value["turn"] == 3
    out = await run.answer("Пока не думали.")  # understood again: nothing is left to ask
    assert "__interrupt__" not in out and out["turns"] == 3
    asked = [(e["area"], e["previous"], e["step"], e["mode"]) for e in events_of(ctx, "question")]
    assert asked == [
        ("integrations", None, 0, "new"),
        ("integrations", "not_understood", 1, "rephrase"),
        ("goals", "ok", 0, "new"),
    ]
    assert out["answer_marks"] == ["not_understood", "ok", "ok"]
    assert [e["reason"] for e in events_of(ctx, "interview_end")] == ["saturated"]
    assert (len(prompts), len(marks)) == (3, 3)  # the last answer was only marked


async def test_an_area_the_brief_covered_is_asked_again_when_not_understood(
    brief_context: Callable[..., RunContext],
) -> None:
    con = {**DRAFT["requirements"][-1], "assumption": False, "sources": ["TURN-0001"]}
    analyst = recording([{"requirements": [con]}, {"requirements": []}], [])  # the brief tells it
    asks = [{"text": "Есть ли сроки или бюджет?", "area": "constraints"}]
    model = interviewer(["not_understood", "ok"], asks, [], [])
    models = stub_models() | {"analyst": analyst, "interviewer": model}
    ctx = brief_context(models=models, max_turns=10, max_iter=0)
    run = interview(ctx, brief=BRIEF, need=NO_NEED | {"constraints": 1})
    await run.start()
    out = await run.answer("А что значит «ограничения»?")
    assert out["__interrupt__"][0].value["turn"] == 2  # covered, but not understood: asked again
    out = await run.answer("Нет, ничего такого.")
    assert "__interrupt__" not in out
    assert [e["area"] for e in events_of(ctx, "question")] == ["constraints", "constraints"]
    assert [e["reason"] for e in events_of(ctx, "interview_end")] == ["coverage"]


async def test_a_vague_answer_is_clarified_once_then_the_queue_goes_on(
    brief_context: Callable[..., RunContext],
) -> None:
    analyst = recording([{"requirements": []}], [])
    asks = [{"text": "Какие требования к скорости?", "area": "goals"}]  # the area is ignored
    model = interviewer(["vague", "vague", "ok"], asks, [], [])
    models = stub_models() | {"analyst": analyst, "interviewer": model}
    ctx = brief_context(models=models, max_turns=4, max_iter=0)
    run = interview(ctx, need=NO_NEED | {"nfr": 2, "data": 1})
    await run.start()
    await run.answer("Быстро.")
    await run.answer("Ну, очень быстро.")
    asked = [(e["area"], e["mode"]) for e in events_of(ctx, "question")]
    assert asked[:3] == [("nfr", "new"), ("nfr", "clarify"), ("data", "new")]


async def test_an_interview_saved_before_the_answer_marks_goes_on(
    brief_context: Callable[..., RunContext],
) -> None:
    ctx = brief_context(max_turns=2, max_iter=0)
    state = initial_state(ctx.project.graph, "interview")
    del state["answer_marks"]  # type: ignore[misc]  # a checkpoint written before T-317
    run = Interview(ctx, state)
    await run.start()
    out = await run.answer("Записываются по телефону.")
    assert out["__interrupt__"][0].value["turn"] == 2


async def test_an_answer_that_told_something_counts_as_understood_whatever_the_mark(
    brief_context: Callable[..., RunContext],
) -> None:
    actor = {"ref": "admin", "name": "Администратор", "sources": ["TURN-0002"]}
    analyst = recording([{"actors": [actor]}, {"requirements": []}], [])
    asks = [{"text": "Кто работает с записью?", "area": "stakeholders"}]
    model = interviewer(["not_understood"], asks, [], [])
    models = stub_models() | {"analyst": analyst, "interviewer": model}
    ctx = brief_context(models=models, max_turns=2, max_iter=0)
    run = interview(ctx, need=NO_NEED | {"stakeholders": 2, "goals": 1})
    await run.start()
    out = await run.answer("Администратор и врачи.")
    second = events_of(ctx, "question")[1]
    assert (second["previous"], second["marked"], second["step"]) == ("ok", "not_understood", 0)
    assert out["answer_marks"] == ["ok"]


async def test_the_free_interviewer_marks_nothing(
    brief_context: Callable[..., RunContext],
) -> None:
    marks: list[str] = []
    model = interviewer(["ok"], [{"text": QUESTION}], [], marks)
    ctx = brief_context(models=stub_models() | {"interviewer": model}, interviewer="free")
    run = interview(ctx, need=NO_NEED | {"goals": 1})
    await run.start()
    await run.answer("Записываются по телефону.")
    assert not marks
