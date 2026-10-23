"""Model readers of dsl/ for FileStore: `FileStore(root, readers=model_readers())`.

The graph layer cannot import dsl/, so entry points (CLI, checks) pass these readers in;
without them FileStore falls back to its own simple scanner.
"""

from collections.abc import Callable, Sequence

from reqgraph.dsl.c4 import read_elements
from reqgraph.dsl.dbml import read_entities
from reqgraph.dsl.plantuml import read_use_cases
from reqgraph.graph.nodes import Node

Reader = Callable[[str, str], Sequence[Node]]


def model_readers() -> dict[str, Reader]:
    return {".dbml": read_entities, ".puml": read_use_cases, ".dsl": read_elements}
