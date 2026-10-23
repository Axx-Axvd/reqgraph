"""Errors of the project store: Russian messages that name the file and the node."""

from reqgraph.graph.errors import GraphError


class StoreError(GraphError):
    """The project folder cannot be read or written; nothing is changed."""
