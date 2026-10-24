"""The run graph of 03_agents: interview with pauses, the pipeline, CI and the repair loop."""

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from reqgraph.agents.analyst import analyst
from reqgraph.agents.nodes import (
    await_answer,
    ci_check,
    ci_gate,
    coverage_gate,
    export,
    intake,
    interviewer,
    mode_gate,
    modeler,
    persist,
    reviewer,
    route_tasks,
    standards,
)
from reqgraph.agents.runtime import RunContext
from reqgraph.agents.state import RunState

NODES = {
    "intake": intake,
    "interviewer": interviewer,
    "await_answer": await_answer,
    "analyst": analyst,
    "modeler": modeler,
    "standards": standards,
    "ci_check": ci_check,
    "reviewer": reviewer,
    "export": export,
    "persist": persist,
}


def build_graph(
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[RunState, RunContext, RunState, RunState]:
    """Compile the graph; an interview needs a checkpointer (interrupt keeps the run there)."""
    g = StateGraph(RunState, context_schema=RunContext)
    for name, node in NODES.items():
        g.add_node(name, node)
    g.add_edge(START, "intake")
    g.add_conditional_edges(
        "intake",
        mode_gate,
        {"interviewer": "interviewer", "analyst": "analyst", "ci_check": "ci_check"},
    )
    g.add_edge("interviewer", "await_answer")
    g.add_conditional_edges(
        "await_answer", coverage_gate, {"ask": "interviewer", "done": "analyst"}
    )
    g.add_edge("analyst", "modeler")
    g.add_edge("modeler", "standards")
    g.add_edge("standards", "ci_check")
    g.add_conditional_edges("ci_check", ci_gate, {"repair": "reviewer", "done": "export"})
    g.add_conditional_edges("reviewer", route_tasks, ["analyst", "modeler", "standards"])
    g.add_edge("export", "persist")
    g.add_edge("persist", END)
    return g.compile(checkpointer=checkpointer)


__all__ = ["NODES", "build_graph", "route_tasks"]
