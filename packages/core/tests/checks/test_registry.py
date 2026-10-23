"""Registry of checks: ids, duplicates, order (T-105)."""

from typing import ClassVar

import pytest
from reqgraph.checks.base import BaseCheck, CheckContext, Finding
from reqgraph.checks.registry import REGISTRY, Registry, all_checks
from reqgraph.graph import ArtifactGraph

from .conftest import AlwaysGreen, MustPriority, training_registry


def test_checks_come_sorted_by_id() -> None:
    assert [c.id for c in training_registry().checks()] == [
        "ISO-900",
        "SCH-900",
        "SND-900",
        "TPL-900",
        "TRC-900",
    ]


def test_duplicate_id_is_refused() -> None:
    registry = Registry()
    registry.register(MustPriority)
    with pytest.raises(ValueError, match="TRC-900"):
        registry.register(MustPriority)


def test_bad_id_is_refused() -> None:
    class Bad(BaseCheck):
        id: ClassVar[str] = "CHK-1"
        title = "плохой id"
        group = "trc"
        owner = "analyst"

        def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
            return []

    with pytest.raises(ValueError, match="CHK-1"):
        Registry().register(Bad)


def test_register_returns_the_class_for_use_as_a_decorator() -> None:
    assert Registry().register(AlwaysGreen) is AlwaysGreen


def test_global_registry_holds_only_real_checks() -> None:
    assert all(not c.id.endswith(("900",)) for c in all_checks())
    assert all_checks() == REGISTRY.checks()
