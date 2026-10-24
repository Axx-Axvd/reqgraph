"""Interview coverage (03_agents, T-301): how much of each of the 9 areas the client has told.

Counted by code from the graph, not judged by a model: a requirement counts in its area only when
it is derived from a client turn and is not an assumption of the Analyst. Actors count as
stakeholders; the nfr area counts distinct ISO 25010 characteristics (03_agents: «at least 4»).
"""

from collections import Counter
from collections.abc import Mapping

from reqgraph.agents.state import AREAS, Coverage
from reqgraph.graph.edges import Rel
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import InterviewTurn, NonFunctionalReq

REQUIREMENT_KINDS = ("BR", "UR", "FR", "NFR", "CON")


def told_by_client(graph: ArtifactGraph) -> set[str]:
    """Nodes derived from at least one client turn."""
    clients = {
        n.id for n in graph.nodes_of("TURN") if isinstance(n, InterviewTurn) and n.role == "client"
    }
    return {e.src for e in graph.edges if e.rel is Rel.DERIVED_FROM and e.dst in clients}


def coverage_of(graph: ArtifactGraph, need: Mapping[str, int] | None = None) -> Coverage:
    need = {**AREAS, **(need or {})}  # reqgraph.yaml overrides the defaults; 0 turns an area off
    told = told_by_client(graph)
    got: Counter[str] = Counter()
    characteristics: set[str] = set()
    for kind in REQUIREMENT_KINDS:
        for node in graph.nodes_of(kind):
            if node.id not in told or node.assumption:
                continue
            if isinstance(node, NonFunctionalReq):
                characteristics.add(node.iso25010)
            elif node.area is not None and node.area in need and node.area != "nfr":
                got[node.area] += 1
    got["stakeholders"] += sum(1 for n in graph.nodes_of("ACT") if n.id in told)
    got["nfr"] = len(characteristics)
    return Coverage(got={area: got.get(area, 0) for area in need}, need=need)


def gaps(coverage: Coverage) -> list[tuple[str, int, int]]:
    """Areas below their need, the emptiest first (by the share told): (area, got, need)."""
    short = [(a, coverage.got.get(a, 0), n) for a, n in coverage.need.items() if n > 0]
    short = [g for g in short if g[1] < g[2]]
    return sorted(short, key=lambda g: (g[1] / g[2], -g[2]))
