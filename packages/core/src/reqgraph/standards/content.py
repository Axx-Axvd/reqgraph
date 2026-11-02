"""Sections built by code from the graph (T-204, T-401): lists of nodes with their ids, the
acceptance criteria, the assumptions. The Standards agent, TPL-001 and the exporters share it, so
a section reads the same in the run, in the check and in the document."""

from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import FunctionalReq, Node
from reqgraph.standards import Section


def line(node: Node) -> str:
    title = getattr(node, "title", None) or getattr(node, "name", "")
    text = getattr(node, "statement", None) or getattr(node, "description", None) or ""
    return f"- {node.id} {title}" + (f": {text}" if text else "")


def code_content(section: Section, graph: ArtifactGraph) -> tuple[str, list[str]] | None:
    """Text and node refs of a section the code builds; None for a heading or an LLM section."""
    if section.fill == "none" or section.llm_field is not None:
        return None
    if section.fill == "acceptance":
        checked = [n for n in graph.nodes_of("FR") if isinstance(n, FunctionalReq) and n.acceptance]
        lines = [f"- {n.id}: " + "; ".join(n.acceptance) for n in checked]
        return "\n".join(lines), [n.id for n in checked]
    if section.fill == "assumptions":
        nodes: list[Node] = [n for n in graph.nodes.values() if n.assumption]
    else:
        nodes = [n for kind in section.node_kinds for n in graph.nodes_of(kind)]
    return "\n".join(line(n) for n in nodes), [n.id for n in nodes]
