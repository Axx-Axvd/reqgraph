"""The draft requirements of an interview step (T-510): what the analyst derived from the client's
last answer, shown under that answer in the chat. The graph itself is saved only when the run ends,
so the worker writes these as a run event while the run waits for the next answer."""

from typing import Any

from reqgraph.graph.edges import Rel
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import InterviewTurn

REQUIREMENT_KINDS = ("BR", "UR", "FR", "NFR", "CON")


def drafts_of(graph: ArtifactGraph) -> dict[str, Any] | None:
    """The requirements derived from the latest client turn, or None before the first answer."""
    answers = sorted(
        (n for n in graph.nodes_of("TURN") if isinstance(n, InterviewTurn) and n.role == "client"),
        key=lambda n: n.id,
    )
    if not answers:
        return None
    turn, answer = answers[-1].id, answers[-1].text
    derived = sorted({e.src for e in graph.edges if e.rel == Rel.DERIVED_FROM and e.dst == turn})
    items = []
    for node_id in derived:
        node = graph.get(node_id)
        if node is None or node.kind not in REQUIREMENT_KINDS:
            continue
        items.append(
            {
                "id": node.id,
                "kind": node.kind,
                "title": getattr(node, "title", ""),
                "statement": getattr(node, "statement", ""),
            }
        )
    # the answer's text puts the drafts under the right bubble (interview_turns.content)
    return {"turn": turn, "answer": answer, "items": items}
