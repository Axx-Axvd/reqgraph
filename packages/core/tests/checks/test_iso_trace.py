"""Details of ISO-* and TRC-*: forms of words, no false alarms, EARS, TRC-005 (T-107)."""

import pytest
from reqgraph.checks.base import CheckContext, CheckSkipped
from reqgraph.checks.iso import EarsForm, _joined_infinitives
from reqgraph.checks.text import vague_terms
from reqgraph.checks.trace import EntitiesInErd
from reqgraph.dsl.readers import model_readers
from reqgraph.graph import GraphPatch
from reqgraph.graph.store import FileStore

from .conftest import GARAGE61


@pytest.mark.parametrize(
    ("text", "terms"),
    [
        ("Поиск должен работать быстро и удобно.", ["быстро", "удобно"]),
        ("Нужен быстрого и удобного поиска", ["быстрого", "удобного"]),  # any form
        ("Отчёты: продажи, остатки и т. д.", ["и т. д."]),
        (
            "Желательно, чтобы менеджер мог менять туры при необходимости.",
            ["при необходимости", "Желательно"],
        ),
        ("The UI shall be user-friendly and fast.", ["user-friendly", "fast"]),
    ],
)
def test_vague_terms_are_found(text: str, terms: list[str]) -> None:
    assert set(terms) <= set(vague_terms(text))


@pytest.mark.parametrize(
    "text",
    [
        "Все заказы корпоративных клиентов учитываются в системе.",
        "Время простоя сервиса не более 1 часа в месяц.",
        "Показ слотов занимает не более 2 секунд для 95% запросов.",
    ],
)
def test_no_false_alarms(text: str) -> None:
    assert vague_terms(text) == []


def test_two_actions_versus_a_list_of_objects() -> None:
    assert _joined_infinitives("Система должна создать запись и отправить SMS.") == (
        "создать",
        "отправить",
    )
    assert _joined_infinitives("Система должна показать слоты с длительностью и ценой.") is None
    assert _joined_infinitives("Система должна позволять клиенту отменить запись.") is None


@pytest.mark.parametrize(
    ("statement", "ears"),
    [
        ("Система должна показывать список услуг.", True),
        ("Когда клиент выбрал услугу, система должна показать слоты.", True),
        ("Если слот занят, система должна сообщить об этом.", True),
        ("За 24 часа до визита система должна отправить SMS.", True),
        ("В первый день месяца система должна сформировать счёт.", True),
        ("Нужно показывать список услуг.", False),
    ],
)
def test_ears_patterns(statement: str, ears: bool) -> None:
    project = FileStore(GARAGE61).load()
    patch = GraphPatch.model_validate(
        {"ops": [{"op": "update", "id": "FR-001", "fields": {"statement": statement}}]}
    )
    graph = project.graph.apply(patch, actor="user").graph
    found = EarsForm().run(graph, CheckContext(project.with_graph(graph)))
    assert ("FR-001" in {f.node_ids[0] for f in found}) is not ears


def test_trc005_is_skipped_without_russian_entity_names() -> None:
    project = FileStore(GARAGE61, readers=model_readers()).load()
    with pytest.raises(CheckSkipped, match="русских названий"):
        EntitiesInErd().run(project.graph, CheckContext(project))


def test_trc005_with_russian_entity_names() -> None:
    project = FileStore(GARAGE61).load()
    ops = [
        {"op": "update", "id": "ENT-05", "fields": {"name": "запись"}},  # FR-003: «создать запись»
        {"op": "update", "id": "ENT-02", "fields": {"name": "автомобиль"}},  # FR-001: не названа
    ]
    graph = project.graph.apply(GraphPatch.model_validate({"ops": ops}), actor="user").graph
    found = EntitiesInErd().run(graph, CheckContext(project.with_graph(graph)))
    assert [f.node_ids for f in found] == [["FR-001", "ENT-02"]]
