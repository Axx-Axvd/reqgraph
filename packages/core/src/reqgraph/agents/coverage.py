"""Interview coverage (03_agents, T-301): how much of each of the 9 areas the client has told.

Counted by code from the graph, not judged by a model: a requirement counts only when it is derived
from a client turn and is not an assumption of the Analyst. The kind of a node gives its area where
it can: a BR is a goal, a CON a constraint, an actor a stakeholder, and the nfr area counts distinct
ISO 25010 characteristics (03_agents: «at least 4»). UR and FR count in the area the Analyst tagged.

An area is saturated when the client has nothing more to tell about it (T-305): an answer that
yields no new requirement closes its area.
Every area is asked at least once before any is asked again, even one the brief already covered:
the brief gives the topic, the client knows more about it.
"""

from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from itertools import pairwise

from reqgraph.agents.state import AREAS, Coverage
from reqgraph.graph.edges import Rel
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import ActorNode, InterviewTurn, Node, NonFunctionalReq

REQUIREMENT_KINDS = ("BR", "UR", "FR", "NFR", "CON")
KIND_AREA = {"BR": "goals", "CON": "constraints", "ACT": "stakeholders", "NFR": "nfr"}
CLOSE_AFTER = 1  # answers about an area that told nothing new: the area is closed


def told_by_client(graph: ArtifactGraph) -> set[str]:
    """Nodes derived from at least one client turn."""
    clients = {
        n.id for n in graph.nodes_of("TURN") if isinstance(n, InterviewTurn) and n.role == "client"
    }
    return {e.src for e in graph.edges if e.rel is Rel.DERIVED_FROM and e.dst in clients}


def _client_turns(graph: ArtifactGraph) -> list[InterviewTurn]:
    turns = [n for n in graph.nodes_of("TURN") if isinstance(n, InterviewTurn)]
    return sorted((t for t in turns if t.role == "client"), key=lambda t: t.id)


def _told(graph: ArtifactGraph) -> Iterator[tuple[str | None, Node]]:
    """Requirements and actors the client told (not assumptions of the Analyst), with their area."""
    told = told_by_client(graph)
    for kind in (*REQUIREMENT_KINDS, "ACT"):
        for node in graph.nodes_of(kind):
            if node.id in told and not getattr(node, "assumption", False):
                yield KIND_AREA.get(node.kind, getattr(node, "area", None)), node


def coverage_of(graph: ArtifactGraph, need: Mapping[str, int] | None = None) -> Coverage:
    need = {**AREAS, **(need or {})}  # reqgraph.yaml overrides the defaults; 0 turns an area off
    got: Counter[str] = Counter()
    characteristics: set[str] = set()
    for area, node in _told(graph):  # live runs: BR came without an area, KIND_AREA gives it
        if isinstance(node, NonFunctionalReq):
            characteristics.add(node.iso25010)
        elif area is not None and area in need:
            got[area] += 1
    got["nfr"] = len(characteristics)
    return Coverage(got={area: got.get(area, 0) for area in need}, need=need)


def facts_by_area(graph: ArtifactGraph, areas: Sequence[str]) -> dict[str, list[str]]:
    """What the client has told about each area: statements of requirements, names of actors."""
    facts: dict[str, list[str]] = {area: [] for area in areas}
    for area, node in _told(graph):
        if area in facts:
            text = node.name if isinstance(node, ActorNode) else getattr(node, "statement", "")
            facts[area].append(str(text))
    return facts


def answer_yields(graph: ArtifactGraph) -> list[int]:
    """For every answered question, in order: how many told requirements and actors came first
    from its answer. A fact repeated from the brief or an earlier answer is not new."""
    turns = sorted(
        (n for n in graph.nodes_of("TURN") if isinstance(n, InterviewTurn)), key=lambda t: t.id
    )
    answers = [b.id for a, b in pairwise(turns) if (a.role, b.role) == ("agent", "client")]
    clients = {t.id for t in _client_turns(graph)}
    first: dict[str, str] = {}
    for e in graph.edges:
        if e.rel is Rel.DERIVED_FROM and e.dst in clients:
            first[e.src] = min(first.get(e.src, e.dst), e.dst)
    new = Counter(first[node.id] for _, node in _told(graph))
    return [new.get(answer, 0) for answer in answers]


def empty_answers(graph: ArtifactGraph, asked_areas: Sequence[str | None]) -> list[str | None]:
    """The area of every answered question whose answer told nothing new, None otherwise. The
    latest questions pair with the latest answers: areas of an earlier session may be missing."""
    yields = answer_yields(graph)
    n = min(len(yields), len(asked_areas))
    pairs = zip(asked_areas[len(asked_areas) - n :], yields[len(yields) - n :], strict=True)
    return [area if count == 0 else None for area, count in pairs]


def closed_areas(graph: ArtifactGraph, asked_areas: Sequence[str | None]) -> set[str]:
    empty = Counter(a for a in empty_answers(graph, asked_areas) if a is not None)
    return {area for area, count in empty.items() if count >= CLOSE_AFTER}


def gaps(coverage: Coverage) -> list[tuple[str, int, int]]:
    """Areas below their need, the emptiest first (by the share told): (area, got, need)."""
    short = [(a, coverage.got.get(a, 0), n) for a, n in coverage.need.items() if n > 0]
    short = [g for g in short if g[1] < g[2]]
    return sorted(short, key=lambda g: (g[1] / g[2], -g[2]))


def queue(
    coverage: Coverage, graph: ArtifactGraph, asked_areas: Sequence[str | None]
) -> list[tuple[str, int, int]]:
    """What to ask about, in order: gaps never asked (the emptiest first), then areas the brief
    covered but nobody asked about, then gaps asked before. Closed areas drop out."""
    closed = closed_areas(graph, asked_areas)
    asked = {a for a in asked_areas if a is not None}
    short = [g for g in gaps(coverage) if g[0] not in closed]
    covered = [
        (a, coverage.got.get(a, 0), n)
        for a, n in coverage.need.items()
        if n > 0 and coverage.got.get(a, 0) >= n and a not in asked and a not in closed
    ]
    return [g for g in short if g[0] not in asked] + covered + [g for g in short if g[0] in asked]
