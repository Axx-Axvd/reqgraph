"""C4 models in Structurizr DSL. Elements are read by the property `reqgraph.id` (REVIEW.md of
garage61, No. 3); whether the workspace compiles is decided by Kroki (dsl/kroki.py, SCH-005).
"""

from reqgraph.graph.nodes import C4Node
from reqgraph.graph.store.scan import scan_c4


def read_elements(text: str, path: str) -> list[C4Node]:
    """Reader for FileStore: software systems and containers with a C4-… id."""
    return scan_c4(text, path)
