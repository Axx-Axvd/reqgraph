"""The run graph of 03_agents: interview with pauses, the pipeline, CI and the repair loop.

In an interview the Analyst runs after every answer and the coverage is counted again from the
graph (T-301); the next question goes to the emptiest area until coverage, the turn limit or the
client ends it. Then the same pipeline as for a brief: Modeler, Standards, checks, repair.
"""

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from reqgraph.agents.analyst import analyst
from reqgraph.agents.modeler import modeler
from reqgraph.agents.nodes import (
    after_analyst,
    await_answer,
    ci_check,
    ci_gate,
    coverage,
    coverage_gate,
    export,
    intake,
    interviewer,
    mode_gate,
    persist,
    route_tasks,
)
from reqgraph.agents.reviewer import reviewer
from reqgraph.agents.runtime import RunContext
from reqgraph.agents.standards import standards
from reqgraph.agents.state import RunState

NODES = {
    "intake": intake,
    "coverage": coverage,
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
    g.add_conditional_edges("intake", mode_gate, ["coverage", "analyst", "ci_check"])
    # the interview: question -> answer -> Analyst -> coverage -> the next question or the models
    g.add_conditional_edges("coverage", coverage_gate, {"ask": "interviewer", "done": "modeler"})
    g.add_edge("interviewer", "await_answer")
    g.add_edge("await_answer", "analyst")
    g.add_conditional_edges("analyst", after_analyst, ["coverage", "modeler"])
    g.add_edge("modeler", "standards")
    g.add_edge("standards", "ci_check")
    g.add_conditional_edges("ci_check", ci_gate, {"repair": "reviewer", "done": "export"})
    g.add_conditional_edges("reviewer", route_tasks, ["analyst", "modeler", "standards", "export"])
    g.add_edge("export", "persist")
    g.add_edge("persist", END)
    return g.compile(checkpointer=checkpointer)


__all__ = ["NODES", "build_graph", "route_tasks"]
