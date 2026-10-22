"""reqgraph: requirements as a checked graph.

Layers (only downward imports): cli -> agents/graph.py -> agents -> llm, dsl, checks, exporters
-> graph (domain) -> storage. See docs/tech-design/02_arch.md.
"""

from importlib.metadata import version

__version__ = version("reqgraph")

__all__ = ["__version__"]
