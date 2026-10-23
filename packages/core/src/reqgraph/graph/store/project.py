"""Project: what a store loads and saves — settings, the graph and the texts kept as they are."""

from dataclasses import dataclass, field, replace
from pathlib import Path

from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.store.config import ProjectConfig


@dataclass(frozen=True)
class Project:
    root: Path
    config: ProjectConfig
    graph: ArtifactGraph
    # relative POSIX path -> text as read: written back unchanged while its content is unchanged
    files: dict[str, str] = field(default_factory=dict)
    # node id -> relative path of the file it was read from (processes, diagram elements)
    layout: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def with_graph(self, graph: ArtifactGraph) -> "Project":
        """The same project with a new graph (after apply()); load warnings no longer apply."""
        return replace(self, graph=graph, warnings=[])
