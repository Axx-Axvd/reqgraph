"""How much the simulated client understands of IT (T-316): a scale, not «knows / does not»."""

import pytest
from reqgraph.sim.jargon import explained, unknown_terms
from reqgraph.sim.scenario import Persona
from reqgraph.sim.stakeholder import Stakeholder, summary

from .test_stakeholder import SCENARIO, Client, reply_part

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_jargon_is_found_by_stem_and_case_and_ordinary_words_are_not() -> None:
    question = "Нужны ли Интеграции с внешними системами и доступ через API?"
    assert unknown_terms(question, 0) == ["интеграция", "внешние системы", "API"]
    assert unknown_terms(question, 2) == ["API"]
    assert unknown_terms(question, 3) == []
    plain = "Какие данные о заказе система хранит и какие отчёты нужны? Нужны ли уведомления?"
    assert unknown_terms(plain, 0) == []


def test_each_step_understands_more() -> None:
    q = "Нужен ли личный кабинет пациента, роли и права доступа и отказоустойчивость?"
    assert unknown_terms(q, 0) == ["личный кабинет", "роли и права", "отказоустойчивость"]
    assert unknown_terms(q, 1) == ["роли и права", "отказоустойчивость"]
    assert unknown_terms(q, 2) == ["отказоустойчивость"]


def test_an_example_counts_as_an_explanation() -> None:
    assert explained("Нужна ли интеграция, например чтобы заказы сами попадали в 1С?")
    assert not explained("Нужна ли интеграция с 1С?")


def test_a_persona_has_a_level_and_levels_by_area() -> None:
    p = Persona(
        name="И", role="р", facts=["ф"], style="с", it_level=1, it_by_area={"data": 2, "nfr": 0}
    )
    assert (p.it_level, p.it_by_area["nfr"]) == (1, 0)
    old = Persona(name="И", role="р", facts=["ф"], style="с")
    assert old.it_level == 3 and old.it_by_area == {}  # a persona written before T-316
    with pytest.raises(ValueError):
        Persona(name="И", role="р", facts=["ф"], style="с", it_level=4)


async def test_an_unexplained_term_above_the_level_is_not_understood() -> None:
    client = Client(["H-001"])
    sim = Stakeholder(SCENARIO, it_level=0, model=client.model())
    answer = await sim.answer("Какие правила отмены нужны в личном кабинете?")
    assert client.selects == []  # nothing is picked: the client did not understand the question
    assert answer.told == [] and sim.revealed == set()
    assert "личный кабинет" in reply_part(client.replies[0])
    assert sim.log[-1]["not_understood"] == ["личный кабинет"]
    assert summary(sim)["not_understood"] == 1


async def test_a_term_with_an_example_is_understood_in_general_words_only() -> None:
    client = Client(["H-001"], ["H-001"])
    sim = Stakeholder(SCENARIO, it_level=0, model=client.model())
    answer = await sim.answer(
        "Какие правила отмены нужны в личном кабинете, то есть на вашей странице на сайте?"
    )
    assert [(t.id, t.mode) for t in answer.told] == [("H-001", "general")]
    assert answer.revealed == [] and sim.log[-1]["partly"] == ["личный кабинет"]
    again = await sim.answer("А за сколько часов до приёма можно отменить запись?")
    assert [(t.id, t.mode) for t in again.told] == [("H-001", "detail")]  # asked again: told


async def test_the_level_of_the_area_counts_when_the_persona_has_one() -> None:
    persona = SCENARIO.persona.model_copy(update={"it_level": 0, "it_by_area": {"rules": 2}})
    scenario = SCENARIO.model_copy(update={"persona": persona})
    client = Client(["H-001"])
    sim = Stakeholder(scenario, model=client.model())
    answer = await sim.answer("Какие бизнес-правила отмены записи?")  # «бизнес-правила» is step 2
    assert answer.revealed == ["H-001"]


async def test_a_specialist_answers_as_before() -> None:
    client = Client(["H-001"])
    sim = Stakeholder(SCENARIO, it_level=3, model=client.model())
    answer = await sim.answer("Какие правила отмены нужны в личном кабинете через API?")
    assert answer.revealed == ["H-001"] and "not_understood" not in sim.log[-1]
