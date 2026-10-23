"""Approved nodes: only a human changes them (CLAUDE.md, 03_agents «Нельзя»)."""

import pytest
from reqgraph.graph import ArtifactGraph
from reqgraph.graph.errors import LockedNode

from .conftest import FR, add, link, patch, remove, unlink, update


@pytest.fixture
def approved(graph: ArtifactGraph) -> ArtifactGraph:
    return graph.apply(patch(update("FR-001", status="approved")), actor="user").graph


def test_agent_cannot_update_an_approved_node(approved: ArtifactGraph) -> None:
    with pytest.raises(LockedNode, match="FR-001"):
        approved.apply(patch(update("FR-001", priority="could")), actor="agent")


def test_agent_cannot_remove_an_approved_node(approved: ArtifactGraph) -> None:
    with pytest.raises(LockedNode, match="FR-001"):
        approved.apply(patch(remove("FR-001")), actor="agent")


def test_agent_cannot_change_edges_of_an_approved_node(approved: ArtifactGraph) -> None:
    with pytest.raises(LockedNode, match="FR-001"):
        approved.apply(patch(unlink("FR-001", "realized_by", "PRC-01")), actor="agent")
    with pytest.raises(LockedNode, match="FR-001"):
        approved.apply(patch(link("FR-001", "realized_by", "PRC-01.T09")), actor="agent")


def test_agent_cannot_cascade_away_edges_of_an_approved_node(approved: ArtifactGraph) -> None:
    # removing TURN-0001 would silently delete FR-001 derived_from TURN-0001
    with pytest.raises(LockedNode, match="FR-001"):
        approved.apply(patch(remove("TURN-0001")), actor="agent")


def test_agent_cannot_approve(graph: ArtifactGraph) -> None:
    with pytest.raises(LockedNode, match="утверждает только человек"):
        graph.apply(patch(update("FR-001", status="approved")), actor="agent")
    with pytest.raises(LockedNode, match="утверждает только человек"):
        graph.apply(patch(add("FR", "f2", status="approved", **FR)), actor="agent")


def test_agent_may_link_to_an_approved_node(approved: ArtifactGraph) -> None:
    # the edge belongs to the new, unapproved node; the approved one is not changed
    result = approved.apply(
        patch(add("FR", "f2", **FR), link("f2", "refines", "UR-001")), actor="agent"
    )
    assert "FR-002" in result.graph.nodes


def test_agent_may_still_change_unapproved_nodes(approved: ArtifactGraph) -> None:
    result = approved.apply(patch(update("UR-001", priority="should")), actor="agent")
    assert result.graph.nodes["UR-001"].priority == "should"  # type: ignore[union-attr]


def test_user_may_change_approved_nodes(approved: ArtifactGraph) -> None:
    result = approved.apply(patch(update("FR-001", priority="could")), actor="user")
    assert result.graph.nodes["FR-001"].priority == "could"  # type: ignore[union-attr]
    result = approved.apply(patch(remove("FR-001")), actor="user")
    assert "FR-001" not in result.graph.nodes


def test_approved_ids(approved: ArtifactGraph) -> None:
    assert approved.approved_ids() == frozenset({"FR-001"})


def test_default_actor_is_the_agent(approved: ArtifactGraph) -> None:
    with pytest.raises(LockedNode):
        approved.apply(patch(update("FR-001", priority="could")))
