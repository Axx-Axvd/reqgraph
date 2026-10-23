"""Domain layer: artifact graph, nodes, edges, GraphPatch, IdAllocator (T-101).

Imports nothing from agents, llm, checks, dsl or exporters.
"""

from reqgraph.graph.edges import Edge, Rel
from reqgraph.graph.graph import ApplyResult, ArtifactGraph, GraphDiff
from reqgraph.graph.ids import IdAllocator
from reqgraph.graph.nodes import NodeKind
from reqgraph.graph.patch import GraphPatch

__all__ = [
    "ApplyResult",
    "ArtifactGraph",
    "Edge",
    "GraphDiff",
    "GraphPatch",
    "IdAllocator",
    "NodeKind",
    "Rel",
]
