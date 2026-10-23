"""Errors of the graph layer. Messages are Russian and name the node: the agent gets them back."""


class GraphError(ValueError):
    """Base class: the graph or a patch is invalid; the graph is left unchanged."""


class BadPatch(GraphError):
    """The patch itself is malformed (duplicate tmp_id and the like)."""


class BadFields(GraphError):
    """Field values of a node do not match its kind."""


class UnknownRef(GraphError):
    """A node, an edge or a referenced id does not exist."""


class DuplicateId(GraphError):
    """A node with this id already exists or the id has been issued before."""


class InvalidLink(GraphError):
    """The edge is not allowed between these kinds of nodes."""


class LockedNode(GraphError):
    """An agent tried to change an approved node or to approve one: only a human may."""
