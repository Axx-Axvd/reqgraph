"""The jargon dictionary moved to reqgraph.checks.jargon (T-320): the simulator and the
interviewer's question check read the same words."""

from reqgraph.checks.jargon import Term, explained_terms, unknown_terms

__all__ = ["Term", "explained_terms", "unknown_terms"]
