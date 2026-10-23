"""Edge rules: allowed kind pairs per relation (T-101, 04_data «Рёбра»)."""

import pytest
from reqgraph.graph.edges import Edge, Rel, allowed, split_ref

OK = [
    ("UR-001", "refines", "BR-001"),
    ("FR-001", "refines", "UR-001"),
    ("NFR-001", "refines", "UR-001"),
    ("FR-001", "realized_by", "PRC-01"),
    ("FR-001", "realized_by", "PRC-01.T05"),
    ("FR-001", "realized_by", "UC-01"),
    ("FR-001", "realized_by", "ENT-01"),
    ("FR-001", "realized_by", "ENT-01.status"),
    ("FR-001", "realized_by", "C4-CNT-01"),
    ("FR-001", "realized_by", "C4-EXT-01"),
    ("BR-001", "derived_from", "TURN-0001"),
    ("UR-001", "derived_from", "TURN-0001"),
    ("FR-001", "derived_from", "TURN-0001"),
    ("NFR-001", "derived_from", "TURN-0001"),
    ("CON-001", "derived_from", "TURN-0001"),
    ("ACT-01", "derived_from", "TURN-0001"),
    ("FR-001", "rendered_in", "SEC-SRS-3.2"),
    ("PRC-01", "rendered_in", "SEC-SRS-3.2"),
    ("FR-001", "conflicts_with", "FR-002"),
    ("UR-001", "conflicts_with", "NFR-001"),
    ("FR-002", "depends_on", "FR-001"),
]
BAD = [
    ("BR-001", "refines", "UR-001"),  # wrong direction
    ("FR-001", "refines", "BR-001"),  # FR refines UR, not BR
    ("FR-001", "refines", "FR-002"),
    ("UR-001", "realized_by", "PRC-01"),  # only FR is realized by model elements
    ("FR-001", "realized_by", "TURN-0001"),
    ("FR-001", "realized_by", "UR-001"),
    ("PRC-01", "derived_from", "TURN-0001"),  # models are not derived from turns
    ("FR-001", "derived_from", "FR-002"),
    ("FR-001", "rendered_in", "FR-002"),
    ("SEC-SRS-3.2", "rendered_in", "SEC-SRS-3.3"),
    ("FR-001", "conflicts_with", "ENT-01"),
    ("FR-001", "depends_on", "UR-001"),
    ("UR-001", "depends_on", "UR-002"),
]


@pytest.mark.parametrize(("src", "rel", "dst"), OK)
def test_allowed_pairs(src: str, rel: str, dst: str) -> None:
    assert allowed(src, Rel(rel), dst)


@pytest.mark.parametrize(("src", "rel", "dst"), BAD)
def test_forbidden_pairs(src: str, rel: str, dst: str) -> None:
    assert not allowed(src, Rel(rel), dst)


def test_split_ref() -> None:
    assert split_ref("PRC-01.T05") == ("PRC-01", "T05")
    assert split_ref("FR-001") == ("FR-001", None)
    assert split_ref("SEC-SRS-3.2") == (
        "SEC-SRS-3.2",
        None,
    )  # a dot inside a section id is not a sub-element


def test_conflicts_with_is_symmetric_and_stored_once() -> None:
    assert Edge.of("FR-002", Rel.CONFLICTS_WITH, "FR-001") == Edge.of(
        "FR-001", Rel.CONFLICTS_WITH, "FR-002"
    )


def test_other_relations_keep_direction() -> None:
    assert Edge.of("FR-002", Rel.DEPENDS_ON, "FR-001") != Edge.of(
        "FR-001", Rel.DEPENDS_ON, "FR-002"
    )


def test_edge_json_uses_from_and_to() -> None:
    edge = Edge.of("FR-001", Rel.REFINES, "UR-001")
    assert edge.model_dump(by_alias=True, mode="json") == {
        "from": "FR-001",
        "rel": "refines",
        "to": "UR-001",
    }
    assert Edge.model_validate({"from": "FR-001", "rel": "refines", "to": "UR-001"}) == edge


def test_edge_is_hashable() -> None:
    assert (
        len({Edge.of("FR-001", Rel.REFINES, "UR-001")} | {Edge.of("FR-001", Rel.REFINES, "UR-001")})
        == 1
    )
