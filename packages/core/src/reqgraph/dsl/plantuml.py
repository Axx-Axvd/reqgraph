"""PlantUML use case diagrams. Use cases are read by the conventions of garage61 (REVIEW.md,
No. 3: alias without the dash, `UC01` = UC-01); whether the file compiles is decided by Kroki
(dsl/kroki.py, check SCH-004). No PlantUML parser exists for Python and Java is not shipped.
"""

from reqgraph.graph.nodes import UseCaseNode
from reqgraph.graph.store.scan import scan_puml


def read_use_cases(text: str, path: str) -> list[UseCaseNode]:
    """Reader for FileStore: `usecase "name" as UCnn`, actor from the first `ACTnn --> UCnn`."""
    return scan_puml(text, path)
