"""LLM layer on pydantic-ai: roles.yaml, FallbackModel, usage limits and cost (T-005, ADR-013)."""

from reqgraph.llm.config import ConfigError, load_roles
from reqgraph.llm.router import BudgetExceeded, CallStats, RunBudget, model_for, structured

__all__ = [
    "BudgetExceeded",
    "CallStats",
    "ConfigError",
    "RunBudget",
    "load_roles",
    "model_for",
    "structured",
]
