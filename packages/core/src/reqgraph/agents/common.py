"""What every agent node shares: its node kinds, the start event, guarded apply with one retry."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from langgraph.runtime import Runtime

from reqgraph.agents.guard import guard
from reqgraph.agents.runtime import RunContext
from reqgraph.agents.state import RepairTask
from reqgraph.checks.base import Owner
from reqgraph.graph.errors import GraphError
from reqgraph.graph.graph import ApplyResult, ArtifactGraph, GraphDiff
from reqgraph.graph.nodes import NodeKind
from reqgraph.graph.patch import GraphPatch

ALLOWED: dict[Owner, frozenset[NodeKind]] = {
    "analyst": frozenset(
        {NodeKind.BR, NodeKind.UR, NodeKind.FR, NodeKind.NFR, NodeKind.CON, NodeKind.ACT}
    ),
    "modeler": frozenset({NodeKind.PRC, NodeKind.ENT, NodeKind.UC, NodeKind.C4}),
    "standards": frozenset({NodeKind.SEC}),
}


def start(runtime: Runtime[RunContext], node: str) -> RunContext:
    runtime.context.events.emit("node_start", node=node)
    return runtime.context


def tag(name: str, value: str) -> str:
    """Data for a model goes in tags: it is data, not instructions (CLAUDE.md, security)."""
    return f"<{name}>\n{value}\n</{name}>"


def diff_summary(diff: GraphDiff) -> dict[str, Any]:
    return {
        "added": diff.added,
        "removed": diff.removed,
        "changed": sorted(diff.changed),
        "linked": len(diff.linked),
        "unlinked": len(diff.unlinked),
    }


@dataclass(frozen=True)
class Attempt:
    """One answer of a model turned into a guarded patch."""

    patch: GraphPatch
    dropped: list[str]


def guarded(
    patch: GraphPatch,
    graph: ArtifactGraph,
    owner: Owner,
    tasks: Sequence[RepairTask],
    dropped: Sequence[str] = (),
) -> Attempt:
    checked = guard(patch, graph, allowed=ALLOWED[owner], tasks=tasks)
    return Attempt(checked.patch, [*dropped, *checked.dropped])


def _apply(graph: ArtifactGraph, attempt: Attempt) -> tuple[ApplyResult | None, str | None]:
    try:
        return graph.apply(attempt.patch, actor="agent"), None
    except GraphError as exc:
        return None, str(exc)


async def apply_with_retry(
    ctx: RunContext,
    owner: Owner,
    graph: ArtifactGraph,
    first: Attempt,
    retry: Callable[[str], Awaitable[Attempt]],
) -> ApplyResult | None:
    """Apply a clean first answer. Otherwise ask once more with the reasons (dropped items or the
    error of apply()); from the second answer whatever passed the guard is applied, the rest is
    logged."""
    if not first.dropped:
        result, error = _apply(graph, first)
        if result is not None:
            return result
        reasons = [error or ""]
    else:
        reasons = first.dropped
    ctx.events.emit("patch_retry", agent=owner, reasons=reasons)
    second = await retry("\n".join(reasons))
    if second.dropped:
        ctx.events.emit("dropped", agent=owner, reasons=second.dropped)
    result, error = _apply(graph, second)
    if error is not None:
        ctx.events.emit("patch_rejected", agent=owner, error=error)
    return result
