"""Interview coverage (03_agents, T-301): how much of each of the 9 areas the client has told.

Counted by code from the graph, not judged by a model: a requirement counts only when it is derived
from a client turn and is not an assumption of the Analyst. The kind of a node gives its area where
it can: a BR is a goal, a CON a constraint, an actor a stakeholder, and the nfr area counts distinct
ISO 25010 characteristics (03_agents: «at least 4»). UR and FR count in the area the Analyst tagged.

An area is saturated when the client has nothing more to tell about it (T-305): an answer that
yields no new requirement closes its area.
Every area is asked at least once before any is asked again, even one the brief already covered:
the brief gives the topic, the client knows more about it.
Reached coverage ends the interview only after that (T-318): a rich brief alone does not.

An answer the client did not understand is not «nothing to tell» (T-317): the interviewer marks
it with the next question, the area stays open and is asked again a step simpler (LANGUAGE_STEPS).
Only an answer not understood at the last step closes the area.
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
NOT_UNDERSTOOD = "not_understood"  # the interviewer's mark of an answer (T-317)
LAST_STEP = 3  # language steps: 0 as is, 1 plain words, 2 his own case, 3 options to choose from
LOST_AREAS = 2  # areas not understood after which a new area starts in plain words


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


def _answered(
    graph: ArtifactGraph, asked_areas: Sequence[str | None]
) -> list[tuple[int, str | None, bool]]:
    """Every answered question: its index in asked_areas, its area, whether the answer told
    nothing new. The latest questions pair with the latest answers: areas of an earlier session
    may be missing."""
    yields = answer_yields(graph)
    n = min(len(yields), len(asked_areas))
    first = len(asked_areas) - n
    return [
        (first + i, asked_areas[first + i], count == 0)
        for i, count in enumerate(yields[len(yields) - n :])
    ]


def empty_answers(graph: ArtifactGraph, asked_areas: Sequence[str | None]) -> list[str | None]:
    """The area of every answered question whose answer told nothing new, None otherwise."""
    return [area if empty else None for _, area, empty in _answered(graph, asked_areas)]


def _step(area: str | None, before: Sequence[tuple[str | None, str | None]]) -> int:
    lost = {a for a, mark in before if mark == NOT_UNDERSTOOD and a is not None}
    start = 1 if len(lost - {area}) >= LOST_AREAS else 0
    misses = sum(1 for a, mark in before if a == area and mark == NOT_UNDERSTOOD)
    return min(LAST_STEP, start + misses)


def language_steps(asked_areas: Sequence[str | None], marks: Sequence[str | None]) -> list[int]:
    """The language step of every question asked (T-317): one step simpler for each answer in
    its area the client did not understand, from step 1 once two other areas lost him."""
    pairs = list(zip(asked_areas, marks, strict=False))
    return [_step(area, pairs[:k]) for k, area in enumerate(asked_areas)]


def language_step(asked_areas: Sequence[str | None], marks: Sequence[str | None], area: str) -> int:
    """The step of the next question about the area, given the marks known so far."""
    return _step(area, list(zip(asked_areas, marks, strict=False)))


def closed_areas(
    graph: ArtifactGraph,
    asked_areas: Sequence[str | None],
    marks: Sequence[str | None] = (),
    *,
    pending: bool = False,
) -> set[str]:
    """Areas whose answer told nothing new (T-305). An answer marked «not understood» does not
    close its area below the last step (T-317); with pending, neither does the latest answer
    whose mark has not come yet."""
    answered = _answered(graph, asked_areas)
    steps = language_steps(asked_areas, marks)
    latest = answered[-1][0] if answered else -1
    empty: Counter[str] = Counter()
    for k, area, nothing in answered:
        if area is None or not nothing:
            continue
        mark = marks[k] if k < len(marks) else None
        unknown = mark is None and pending and k == latest
        if (mark == NOT_UNDERSTOOD or unknown) and steps[k] < LAST_STEP:
            continue
        empty[area] += 1
    return {area for area, count in empty.items() if count >= CLOSE_AFTER}


def latest_told_nothing(graph: ArtifactGraph, asked_areas: Sequence[str | None]) -> bool:
    """The latest answer told nothing new: only such an answer can be «not understood» (T-317)."""
    answered = _answered(graph, asked_areas)
    return bool(answered) and answered[-1][2]


def rephrase(
    graph: ArtifactGraph, asked_areas: Sequence[str | None], marks: Sequence[str | None]
) -> tuple[str, int] | None:
    """The area of the latest answer and the step to ask it again at, if that answer told nothing,
    its mark has not come yet and a simpler step is left: the interviewer decides from the answer
    whether the client did not understand (T-317)."""
    answered = _answered(graph, asked_areas)
    if not answered:
        return None
    k, area, nothing = answered[-1]
    if area is None or not nothing or k < len(marks):
        return None
    if language_steps(asked_areas, marks)[k] >= LAST_STEP:
        return None
    return area, language_step(asked_areas[: k + 1], [*marks[:k], NOT_UNDERSTOOD], area)


def gaps(coverage: Coverage) -> list[tuple[str, int, int]]:
    """Areas below their need, the emptiest first (by the share told): (area, got, need)."""
    short = [(a, coverage.got.get(a, 0), n) for a, n in coverage.need.items() if n > 0]
    short = [g for g in short if g[1] < g[2]]
    return sorted(short, key=lambda g: (g[1] / g[2], -g[2]))


def queue(
    coverage: Coverage,
    graph: ArtifactGraph,
    asked_areas: Sequence[str | None],
    marks: Sequence[str | None] = (),
    *,
    pending: bool = False,
) -> list[tuple[str, int, int]]:
    """What to ask about, in order: gaps never asked (the emptiest first), then areas the brief
    covered but nobody asked about, then gaps asked before. Closed areas drop out."""
    closed = closed_areas(graph, asked_areas, marks, pending=pending)
    asked = {a for a in asked_areas if a is not None}
    short = [g for g in gaps(coverage) if g[0] not in closed]
    covered = [
        (a, coverage.got.get(a, 0), n)
        for a, n in coverage.need.items()
        if n > 0 and coverage.got.get(a, 0) >= n and a not in asked and a not in closed
    ]
    return [g for g in short if g[0] not in asked] + covered + [g for g in short if g[0] in asked]
