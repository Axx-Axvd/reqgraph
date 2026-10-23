"""Finding and the base class of checks (T-105)."""

import pytest
from pydantic import ValidationError
from reqgraph.checks.base import Finding

from .conftest import MustPriority


def test_finding_of_a_check() -> None:
    found = MustPriority().finding("error", ["FR-002", "FR-001"], "текст", hint="как")
    assert (found.check_id, found.owner, found.hint) == ("TRC-900", "analyst", "как")


def test_fingerprint_ignores_the_order_of_nodes_and_the_text() -> None:
    a = Finding(
        check_id="TRC-002",
        severity="error",
        node_ids=["FR-2", "FR-1"],
        message="a",
        owner="modeler",
    )
    b = Finding(
        check_id="TRC-002",
        severity="error",
        node_ids=["FR-1", "FR-2"],
        message="b",
        owner="modeler",
    )
    c = Finding(
        check_id="TRC-003",
        severity="error",
        node_ids=["FR-1", "FR-2"],
        message="a",
        owner="modeler",
    )
    assert a.fingerprint == b.fingerprint != c.fingerprint
    assert len(a.fingerprint) == 40


@pytest.mark.parametrize(
    "fields",
    [
        {"check_id": "XYZ-001"},
        {"severity": "fatal"},
        {"owner": "tester"},
        {"message": ""},
        {"colour": "red"},
    ],
)
def test_invalid_findings(fields: dict[str, str]) -> None:
    data = {"check_id": "TRC-002", "severity": "error", "message": "x", "owner": "modeler"}
    with pytest.raises(ValidationError):
        Finding.model_validate(data | fields)
