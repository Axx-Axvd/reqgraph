"""guard(): drop what an agent may not do before ArtifactGraph.apply() sees the patch (03_agents).

Not the whole answer for one bad line: each forbidden op is dropped with a reason in Russian, the
rest goes on. Dropped: other agents' node kinds, approved nodes and the approved status, unknown
ids and tmp_ids, links the graph does not allow, removals without a repair task on that node.
apply() still checks everything (all-or-nothing); guard only keeps one bad op from sinking it.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from reqgraph.agents.state import RepairTask
from reqgraph.graph.edges import REFINES_PAIRS, RULES, Rel, kind_of, split_ref
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import NodeKind
from reqgraph.graph.patch import AddOp, GraphPatch, LinkOp, Op, RemoveOp, UnlinkOp, UpdateOp


@dataclass(frozen=True)
class GuardResult:
    patch: GraphPatch
    dropped: list[str]  # «update BR-001: узел утверждён человеком»


class _Drop(Exception):
    pass


def guard(
    patch: GraphPatch,
    graph: ArtifactGraph,
    *,
    allowed: frozenset[NodeKind],
    tasks: Sequence[RepairTask] = (),
) -> GuardResult:
    removable = {node for task in tasks for node in task.node_ids}
    approved = graph.approved_ids()
    kept: list[Op] = []
    dropped: list[str] = []
    new: dict[str, NodeKind] = {}  # tmp_id of a kept add -> its kind

    def check_add(op: AddOp) -> None:
        if NodeKind(op.kind) not in allowed:
            raise _Drop("чужой тип узла")
        if op.fields.get("status") == "approved":
            raise _Drop("статус approved ставит только человек")

    def check_node(op: UpdateOp | RemoveOp) -> None:
        node = graph.get(op.id)
        if node is None:
            raise _Drop("такого узла нет")
        if NodeKind(node.kind) not in allowed:
            raise _Drop("чужой тип узла")
        if op.id in approved:
            raise _Drop("узел утверждён человеком")
        if isinstance(op, UpdateOp) and op.fields.get("status") == "approved":
            raise _Drop("статус approved ставит только человек")
        if isinstance(op, RemoveOp) and op.id not in removable:
            raise _Drop("удалять можно только по задаче ремонта")

    def kind(ref: str) -> NodeKind:
        if ref in new:
            return new[ref]
        try:
            parent, _ = split_ref(ref)
            node_kind = kind_of(parent)
        except ValueError:
            raise _Drop(f"узел {ref} не создаётся в этом патче") from None
        if graph.get(parent) is None:
            raise _Drop(f"нет узла {parent}")
        return node_kind

    def check_edge(op: LinkOp | UnlinkOp) -> None:
        src, dst = kind(op.src), kind(op.dst)
        sources, targets = RULES[op.rel]
        refines_ok = op.rel is not Rel.REFINES or dst in REFINES_PAIRS.get(src, frozenset())
        if src not in sources or dst not in targets or not refines_ok:
            raise _Drop("такая связь недопустима")
        owners = [op.src] + ([op.dst] if op.rel is Rel.CONFLICTS_WITH else [])
        if any(split_ref(o)[0] in approved for o in owners if o not in new):
            raise _Drop("узел утверждён человеком")
        if isinstance(op, UnlinkOp) and not any(
            e.src == op.src and e.rel is op.rel and e.dst == op.dst for e in graph.edges
        ):
            raise _Drop("такой связи нет")

    for add in (op for op in patch.ops if isinstance(op, AddOp)):
        try:  # adds first: links may name tmp_ids declared later in the patch
            check_add(add)
            new[add.tmp_id] = NodeKind(add.kind)
        except _Drop as reason:
            dropped.append(f"add {add.kind}: {reason}")
    for op in patch.ops:
        try:
            match op:
                case AddOp():
                    if op.tmp_id not in new:
                        continue
                case UpdateOp() | RemoveOp():
                    check_node(op)
                case LinkOp() | UnlinkOp():
                    check_edge(op)
        except _Drop as reason:
            dropped.append(f"{_label(op)}: {reason}")
            continue
        kept.append(op)
    if not dropped:
        return GuardResult(patch, [])
    return GuardResult(patch.model_copy(update={"ops": kept}), dropped)


def _label(op: Op) -> str:
    match op:
        case UpdateOp() | RemoveOp():
            return f"{op.op} {op.id}"
        case LinkOp() | UnlinkOp():
            return f"{op.op} {op.src} {op.rel.value} {op.dst}"
        case AddOp():
            return f"add {op.kind}"
