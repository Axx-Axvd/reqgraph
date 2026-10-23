"""Deterministic probe scoring on hand-made answers (T-006)."""

from reqgraph_evals.schemas import (
    ExtractedRequirement,
    Extraction,
    Flow,
    Node,
    ProcessSketch,
    Question,
    Rewrite,
)
from reqgraph_evals.scoring import (
    score_extract,
    score_process,
    score_question,
    score_rewrite,
    vague_terms,
)

EXPECTED = [
    {"kind": "FR", "text": "клиент записывается на занятие в приложении"},
    {"kind": "NFR", "text": "приложение выдерживает 200 одновременных пользователей"},
]


def test_extract_perfect_match() -> None:
    out = Extraction(
        requirements=[
            ExtractedRequirement(kind="FR", text="Клиент записывается на занятие через приложение"),
            ExtractedRequirement(
                kind="NFR", text="Приложение выдерживает 200 одновременных пользователей"
            ),
        ]
    )
    s = score_extract(out, EXPECTED)
    assert s["recall"] == 1.0 and s["precision"] == 1.0 and s["f1"] == 1.0
    assert s["kind_accuracy"] == 1.0


def test_extract_missing_and_extra() -> None:
    out = Extraction(
        requirements=[
            ExtractedRequirement(kind="FR", text="клиент записывается на занятие в приложении"),
            ExtractedRequirement(kind="FR", text="система печатает чеки на принтере"),
        ]
    )
    s = score_extract(out, EXPECTED)
    assert s["recall"] == 0.5 and s["precision"] == 0.5


def test_extract_wrong_kind_counts_as_found_but_lowers_kind_accuracy() -> None:
    out = Extraction(
        requirements=[
            ExtractedRequirement(kind="NFR", text="клиент записывается на занятие в приложении"),
            ExtractedRequirement(
                kind="NFR", text="приложение выдерживает 200 одновременных пользователей"
            ),
        ]
    )
    s = score_extract(out, EXPECTED)
    assert s["recall"] == 1.0
    assert s["kind_accuracy"] == 0.5


def good_process() -> ProcessSketch:
    return ProcessSketch(
        nodes=[
            Node(id="s", kind="start", name="Заявка получена"),
            Node(id="t1", kind="task", name="Проверить заявку"),
            Node(id="g1", kind="xor", name="Заявка корректна?"),
            Node(id="t2", kind="task", name="Отправить отказ"),
            Node(id="t3", kind="task", name="Продлить абонемент"),
            Node(id="e", kind="end", name="Готово"),
        ],
        flows=[
            Flow(source="s", target="t1"),
            Flow(source="t1", target="g1"),
            Flow(source="g1", target="t2", condition="нет"),
            Flow(source="g1", target="t3", condition="да"),
            Flow(source="t2", target="e"),
            Flow(source="t3", target="e"),
        ],
    )


def test_process_valid_structure() -> None:
    s = score_process(good_process(), {"tasks": ["провер", "отказ", "продл"], "min_gateways": 1})
    assert s["structure"] == 1.0
    assert s["task_recall"] == 1.0


def test_process_dead_end_and_dangling_flow() -> None:
    p = good_process()
    p.flows = [f for f in p.flows if f.source != "t2"]  # t2 can no longer reach the end
    p.flows.append(Flow(source="t3", target="nowhere"))
    s = score_process(p, {"tasks": ["провер"], "min_gateways": 1})
    assert s["structure"] < 1.0
    assert s["no_dead_ends"] == 0.0
    assert s["refs_ok"] == 0.0


def test_process_gateway_with_single_branch() -> None:
    p = good_process()
    p.flows = [f for f in p.flows if not (f.source == "g1" and f.target == "t2")]
    s = score_process(p, {"tasks": [], "min_gateways": 1})
    assert s["gateways_ok"] == 0.0


def test_vague_terms_found() -> None:
    assert vague_terms("Поиск должен работать быстро и удобно и т. д.") == [
        "быстро",
        "удобно",
        "и т. д.",
    ]
    assert vague_terms("Система должна вернуть результат не дольше 2 секунд") == []


def test_rewrite_good_and_bad() -> None:
    good = Rewrite(
        statement="Система должна возвращать результаты поиска экспонатов не дольше 2 секунд",
        acceptance=["Поиск по названию из 10 000 экспонатов отвечает за 2 с"],
    )
    bad = Rewrite(statement="Поиск экспонатов будет быстрым", acceptance=["быстро"])
    keep = ["поиск", "экспонат"]
    assert score_rewrite(good, keep)["score"] == 1.0
    sb = score_rewrite(bad, keep)
    assert sb["has_shall"] == 0.0 and sb["no_vague"] == 0.0


def test_question_rules() -> None:
    case = {"area": ["рол", "прав"], "hidden": ["смотритель", "экскурсовод"]}
    good = Question(
        question="Какие сотрудники будут работать в системе и что каждый из них может делать?",
        area="роли сотрудников",
    )
    leading = Question(
        question="Нужны ли роли смотритель и экскурсовод? А бухгалтер?", area="права"
    )
    assert score_question(good, case)["score"] == 1.0
    s = score_question(leading, case)
    assert s["no_hint"] == 0.0 and s["single"] == 0.0
    off = Question(question="Как клиенты будут покупать билеты?", area="билеты")
    assert score_question(off, case)["on_topic"] == 0.0


def test_extract_matches_across_inflections() -> None:
    expected = [{"kind": "FR", "text": "резидент бронирует переговорную комнату на время"}]
    out = Extraction(
        requirements=[
            ExtractedRequirement(kind="FR", text="Бронировать переговорки на час или два")
        ]
    )
    assert score_extract(out, expected)["recall"] == 1.0
    other = Extraction(requirements=[ExtractedRequirement(kind="FR", text="Платить картой онлайн")])
    assert score_extract(other, expected)["recall"] == 0.0
