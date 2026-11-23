"""T-510: the draft requirements shown under the client's answer during an interview."""

from reqgraph.graph.edges import Edge, Rel
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import BusinessReq, FunctionalReq, InterviewTurn
from reqgraph_api.worker.drafts import drafts_of

LOST = "Доля потерянных звонков снижается."
MOVE = "Система предлагает перенести записи."


def turn(n: int, role: str, text: str) -> InterviewTurn:
    return InterviewTurn(id=f"TURN-{n:04d}", role=role, text=text)  # type: ignore[arg-type]


def test_drafts_are_the_requirements_derived_from_the_last_answer() -> None:
    graph = ArtifactGraph.from_parts(
        [
            turn(1, "agent", "Как записываются?"),
            turn(2, "client", "По телефону, каждый пятый звонок теряется."),
            turn(3, "agent", "Что если врач заболел?"),
            turn(4, "client", "Переносим к другому врачу."),
            BusinessReq(id="BR-001", title="Меньше потерь", statement=LOST),
            FunctionalReq(id="FR-001", title="Перенос записей", statement=MOVE),
        ],
        [
            Edge.model_validate({"from": "BR-001", "rel": Rel.DERIVED_FROM, "to": "TURN-0002"}),
            Edge.model_validate({"from": "FR-001", "rel": Rel.DERIVED_FROM, "to": "TURN-0004"}),
        ],
    )
    assert drafts_of(graph) == {
        "turn": "TURN-0004",
        "answer": "Переносим к другому врачу.",
        "items": [
            {"id": "FR-001", "kind": "FR", "title": "Перенос записей", "statement": MOVE},
        ],
    }


def test_no_answer_yet_or_nothing_derived_gives_no_drafts() -> None:
    only_question = ArtifactGraph.from_parts([turn(1, "agent", "Как записываются?")], [])
    assert drafts_of(only_question) is None
    answered = ArtifactGraph.from_parts(
        [turn(1, "agent", "Вопрос?"), turn(2, "client", "Ответ.")], []
    )
    assert drafts_of(answered) == {"turn": "TURN-0002", "answer": "Ответ.", "items": []}
