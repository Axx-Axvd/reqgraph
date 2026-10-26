"""The simulated client on stub models (T-302): it tells only what the question is about."""

import json
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from reqgraph.sim.scenario import Hidden, HiddenRequirement, Persona, Scenario, ScenarioInfo
from reqgraph.sim.stakeholder import MAX_ITEMS, Stakeholder, summary

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def item(n: int, statement: str, reveal: str, **extra: Any) -> HiddenRequirement:
    return HiddenRequirement(
        id=f"H-{n:03d}", kind="FR", area="rules", statement=statement, reveal=reveal, **extra
    )


SCENARIO = Scenario(
    info=ScenarioInfo(id="dev-09", title="Т", domain="тест", size="S", split="dev"),
    brief="Хотим онлайн-запись.",
    persona=Persona(name="Ирина", role="главный врач", facts=["3 кресла"], style="коротко"),
    hidden=Hidden(
        requirements=[
            item(1, "Отменить запись можно не позднее чем за 3 часа.", "сроки отмены"),
            item(2, "SMS-напоминание уходит за 24 часа до приёма.", "напоминания"),
            item(3, "Врач видит только своё расписание.", "что видит врач"),
            item(4, "Запись открыта на 30 дней вперёд.", "на сколько вперёд записаться"),
            item(5, "Пациент записывается сам на сайте.", "запись", in_brief=True),
        ]
    ),
)


class Client:
    """A stub model for both steps: picks the given ids, replies with a fixed text."""

    def __init__(self, *picks: list[str], details: bool = False, mistakes: bool = True) -> None:
        self.picks = list(picks)
        self.details = details
        self.mistakes = mistakes  # does the model name the wrong number it is asked for
        self.replies: list[str] = []  # the reply prompts

    def model(self) -> FunctionModel:
        def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            prompt = str(messages[-1].parts[-1].content)  # type: ignore[union-attr]
            if "только выбрать" in prompt:
                ids = self.picks.pop(0) if self.picks else []
                data: dict[str, Any] = {"ids": ids, "details": self.details}
            else:
                self.replies.append(prompt)
                wrong = "неправильно" in reply_part(prompt) and self.mistakes
                data = {"text": "Ну, за 99 часов." if wrong else "Ну, как-то так."}
            return ModelResponse(parts=[TextPart(json.dumps(data, ensure_ascii=False))])

        return FunctionModel(fn)


def reply_part(prompt: str) -> str:
    """The «what to tell» part of a reply prompt (the dialog below may repeat old answers)."""
    return prompt.split("# Что сказать в этом ответе")[1].split("# Правила")[0]


async def test_the_reply_sees_only_the_picked_requirements() -> None:
    client = Client(["H-001"])
    sim = Stakeholder(SCENARIO, model=client.model())
    answer = await sim.answer("Когда пациент может отменить запись?")
    told = reply_part(client.replies[0])
    assert "за 3 часа" in told
    assert all(other not in told for other in ("24 часа", "своё расписание", "30 дней"))
    assert answer.revealed == ["H-001"] and sim.revealed == {"H-001"}
    assert len(answer.stats) == 2 and all(s.role == "stakeholder" for s in answer.stats)


async def test_unknown_ids_are_dropped_and_at_most_three_are_told() -> None:
    client = Client(["H-404", "H-001", "H-002", "H-003", "H-004", "H-001"])
    sim = Stakeholder(SCENARIO, model=client.model())
    answer = await sim.answer("Расскажите всё про запись.")
    assert [t.id for t in answer.told] == ["H-001", "H-002", "H-003"][:MAX_ITEMS]


async def test_nothing_picked_means_nothing_told() -> None:
    client = Client([])
    sim = Stakeholder(SCENARIO, model=client.model())
    answer = await sim.answer("Какого цвета у вас стены?")
    assert answer.told == [] and "нечего сказать" in reply_part(client.replies[0])


async def test_a_vague_client_needs_a_second_question_for_details() -> None:
    client = Client(["H-001"], ["H-001"])
    sim = Stakeholder(SCENARIO, character="vague", model=client.model())
    first = await sim.answer("Как с отменой записи?")
    told = reply_part(client.replies[0])
    assert [t.mode for t in first.told] == ["general"] and first.revealed == []
    assert "сроки отмены" in told and "3 часа" not in told  # only the topic, no details
    second = await sim.answer("А до какого времени можно отменить?", [("Как с отменой?", "Ну.")])
    assert [t.mode for t in second.told] == ["detail"] and "3 часа" in reply_part(client.replies[1])
    assert summary(sim) == {"hidden": 4, "revealed": 1, "mentioned_only": 0, "wrong_left": 0}


async def test_a_vague_client_tells_details_when_the_question_asks_for_them() -> None:
    client = Client(["H-002"], details=True)
    sim = Stakeholder(SCENARIO, character="vague", model=client.model())
    answer = await sim.answer("За сколько часов до приёма напоминать?")
    assert [t.mode for t in answer.told] == ["tell"]


async def modes(seed: int) -> list[list[str]]:
    picks = [["H-001"], ["H-002"], ["H-004"], ["H-003"], ["H-001"], ["H-002"], ["H-004"]]
    sim = Stakeholder(SCENARIO, character="contradictory", seed=seed, model=Client(*picks).model())
    return [[f"{t.id}:{t.mode}" for t in (await sim.answer("?")).told] for _ in picks]


async def test_contradictions_repeat_with_the_seed_and_get_corrected() -> None:
    runs = {seed: await modes(seed) for seed in range(12)}
    seed = next(s for s, run in runs.items() if any(":wrong" in m for a in run for m in a))
    first, again = runs[seed], await modes(seed)
    assert first == again  # the same seed, the same mistakes in the same answers
    flat = [m for answer in first for m in answer]
    wrong = [m.split(":")[0] for m in flat if m.endswith(":wrong")]
    assert wrong, flat  # a contradictory client does make mistakes
    for item_id in wrong:  # and every one is corrected later in this dialog
        assert f"{item_id}:correct" in flat[flat.index(f"{item_id}:wrong") + 1 :]
    assert all(not m.startswith("H-003:wrong") for m in flat)  # no number, nothing to get wrong


async def test_asked_again_the_client_repeats_instead_of_forgetting() -> None:
    client = Client(["H-001"], ["H-001"])
    sim = Stakeholder(SCENARIO, model=client.model())
    await sim.answer("Когда можно отменить запись?")
    again = await sim.answer("Ещё раз: до какого времени отмена?")
    assert [t.mode for t in again.told] == ["repeat"] and again.revealed == []
    told = reply_part(client.replies[1])
    assert "уже шла речь" in told and "3 часа" in told


def test_a_law_number_is_not_a_quantity_to_get_wrong() -> None:
    from reqgraph.sim.stakeholder import _has_number

    law = item(9, "Данные хранятся в России по 152-ФЗ.", "закон")
    assert not _has_number(law) and _has_number(item(8, "Не больше 4 заказов в час.", "лимиты"))


async def test_a_correction_waits_for_the_same_area() -> None:
    other = item(6, "Логотип клиники — синий.", "оформление").model_copy(update={"area": "data"})
    scenario = SCENARIO.model_copy(
        update={"hidden": Hidden(requirements=[*SCENARIO.hidden.requirements, other])}
    )
    sim = Stakeholder(scenario, character="contradictory", model=Client(["H-006"]).model())
    sim.wrong.append("H-001")  # a wrong number about the cancel rules was said before
    sim.rng.random = lambda: 0.0  # type: ignore[method-assign]  # always ready to correct
    answer = await sim.answer("Какой у вас логотип?")
    assert [t.mode for t in answer.told] == ["tell"] and sim.wrong == ["H-001"]


async def test_a_wrong_number_counts_only_when_the_reply_names_one() -> None:
    for mistakes, mode in ((True, "wrong"), (False, "tell")):
        sim = Stakeholder(
            SCENARIO, character="contradictory", model=Client(["H-001"], mistakes=mistakes).model()
        )
        sim.rng.random = lambda: 0.0  # type: ignore[method-assign]  # always ready to err
        answer = await sim.answer("Когда можно отменить запись?")
        assert [t.mode for t in answer.told] == [mode]
        assert (sim.wrong == ["H-001"]) is mistakes and ("H-001" in sim.revealed) is not mistakes
        assert sim.log[-1]["told"] == [{"id": "H-001", "mode": mode}]
