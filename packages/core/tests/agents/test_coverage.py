"""Interview coverage counted by code (T-301): what counts, what does not."""

from typing import Any

from reqgraph.agents.analyst import AnalystDraft, to_patch
from reqgraph.agents.coverage import coverage_of, gaps
from reqgraph.agents.state import AREAS, Coverage
from reqgraph.graph import ArtifactGraph, GraphPatch

from .conftest import DRAFT, turns_graph


def graph_with(draft: dict[str, Any]) -> ArtifactGraph:
    graph = turns_graph()
    return graph.apply(to_patch(AnalystDraft.model_validate(draft), graph).patch).graph


def nfr(ref: str, iso: str, source: str = "TURN-0002") -> dict[str, Any]:
    metric = {"name": "доля", "unit": "%", "threshold": ">= 98", "method": "отчёт"}
    statement = "Доля успешных записей должна быть не ниже 98% за месяц."
    item = {"ref": ref, "kind": "NFR", "title": ref, "statement": statement, "iso25010": iso}
    return item | {"metric": metric, "area": "nfr", "sources": [source]}


def test_requirements_from_client_turns_count_in_their_area() -> None:
    draft = {
        **DRAFT,
        "requirements": [
            {**r, "area": "scenarios"} if r["kind"] in ("UR", "FR") else r
            for r in DRAFT["requirements"]
        ],
    }
    counted = coverage_of(graph_with(draft))
    assert counted.got["scenarios"] == 2  # UR and FR, both derived from TURN-0002
    assert counted.got["stakeholders"] == 1  # the actor «Пациент»
    assert counted.got["nfr"] == 1  # one ISO 25010 characteristic: reliability
    assert counted.got["constraints"] == 0  # CON is an assumption: not told by the client
    assert counted.got["goals"] == 1  # a BR is a goal whatever its area tag (it has none here)


def test_nfr_counts_distinct_characteristics_and_assumptions_do_not_count() -> None:
    items = [nfr("a", "reliability"), nfr("b", "reliability"), nfr("c", "performance_efficiency")]
    items.append({**nfr("d", "security"), "assumption": True, "sources": []})
    counted = coverage_of(graph_with({"requirements": items}))
    assert counted.got["nfr"] == 2


def test_agent_turns_are_not_the_client() -> None:
    question = {"role": "agent", "text": "Сколько у вас врачей?"}
    ops = [{"op": "add", "kind": "TURN", "tmp_id": "q", "fields": question}]
    graph = turns_graph().apply(GraphPatch.model_validate({"ops": ops})).graph
    item = {**nfr("a", "reliability"), "sources": ["TURN-0003"]}  # the agent's question
    draft = AnalystDraft.model_validate({"requirements": [item]})
    graph = graph.apply(to_patch(draft, graph).patch).graph
    assert graph.nodes_of("NFR") and coverage_of(graph).got["nfr"] == 0


def test_project_thresholds_override_the_defaults() -> None:
    counted = coverage_of(ArtifactGraph.empty(), {"goals": 5, "integrations": 0})
    assert counted.need == {**AREAS, "goals": 5, "integrations": 0}
    assert not counted.complete
    assert coverage_of(ArtifactGraph.empty(), dict.fromkeys(AREAS, 0)).complete


def test_gaps_start_with_the_emptiest_area() -> None:
    coverage = Coverage(
        got={**dict.fromkeys(AREAS, 9), "scenarios": 1, "nfr": 0, "data": 2},
        need=dict(AREAS),
    )
    assert [g[0] for g in gaps(coverage)] == ["nfr", "scenarios", "data"]
    assert gaps(Coverage(got=dict.fromkeys(AREAS, 9), need=dict(AREAS))) == []


def test_an_area_asked_twice_in_a_row_goes_last() -> None:
    from reqgraph.agents.nodes import next_gaps
    from reqgraph.agents.state import initial_state

    state = initial_state(ArtifactGraph.empty(), "interview")
    first = [g[0] for g in next_gaps(state)]
    assert first[0] == "scenarios"  # 0 of 4: the emptiest with the largest need
    state["asked_areas"] = ["scenarios", "scenarios"]
    moved = [g[0] for g in next_gaps(state)]
    assert moved[-1] == "scenarios" and moved[:-1] == first[1:]
    state["asked_areas"] = ["scenarios", "nfr"]
    assert [g[0] for g in next_gaps(state)] == first
