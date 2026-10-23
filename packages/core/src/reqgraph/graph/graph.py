"""ArtifactGraph: immutable graph of requirement artifacts, changed only by apply(GraphPatch)."""

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from reqgraph.graph.edges import Edge, Rel, allowed, split_ref
from reqgraph.graph.errors import (
    BadFields,
    BadPatch,
    DuplicateId,
    GraphError,
    InvalidLink,
    LockedNode,
    UnknownRef,
)
from reqgraph.graph.ids import IdAllocator
from reqgraph.graph.nodes import REF_FIELDS, Node, NodeKind, node_from_dict
from reqgraph.graph.patch import (
    SCHEMA_VERSION,
    TMP_ID,
    AddOp,
    GraphPatch,
    LinkOp,
    RemoveOp,
    UnlinkOp,
    UpdateOp,
)

Actor = Literal["agent", "user"]
_TMP = re.compile(TMP_ID)


@dataclass(frozen=True)
class GraphDiff:
    """What a patch changed: the base of the history entry and of the UI «что изменилось»."""

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: dict[str, dict[str, tuple[Any, Any]]] = field(default_factory=dict)
    linked: list[Edge] = field(default_factory=list)
    unlinked: list[Edge] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed or self.linked or self.unlinked)

    def summary(self) -> str:
        """Short Russian text, one line per kind of change."""
        lines = []
        if self.added:
            lines.append(f"добавлено: {', '.join(self.added)}")
        for node_id, fields in self.changed.items():
            what = ", ".join(f"{k}: {a!r} → {b!r}" for k, (a, b) in fields.items())
            lines.append(f"изменено: {node_id} ({what})")
        if self.removed:
            lines.append(f"удалено: {', '.join(self.removed)}")
        lines += [f"связь добавлена: {_edge_text(e)}" for e in self.linked]
        lines += [f"связь убрана: {_edge_text(e)}" for e in self.unlinked]
        return "\n".join(lines) if lines else "без изменений"


@dataclass(frozen=True)
class ApplyResult:
    graph: "ArtifactGraph"
    id_map: dict[str, str]  # tmp_id of the patch -> id issued by code
    diff: GraphDiff


def _edge_text(edge: Edge) -> str:
    return f"{edge.src} -{edge.rel.value}-> {edge.dst}"


def _parent(ref: str) -> str:
    """`PRC-01.T05` -> `PRC-01`; other ids as they are."""
    return split_ref(ref)[0]


def _require(ref: str, nodes: dict[str, Node]) -> None:
    try:
        parent = _parent(ref)
    except ValueError:
        raise UnknownRef(f"«{ref}» не похоже на id узла") from None
    if parent not in nodes:
        suffix = f" (ссылка {ref})" if parent != ref else ""
        raise UnknownRef(f"узла {parent} нет в графе{suffix}")


def _check_integrity(nodes: dict[str, Node], edges: Iterable[Edge]) -> None:
    """Edges join existing nodes of allowed kinds; reference fields point to the right kind."""
    for edge in edges:
        _require(edge.src, nodes)
        _require(edge.dst, nodes)
        if not allowed(edge.src, edge.rel, edge.dst):
            raise InvalidLink(_not_allowed(edge.src, edge.rel, edge.dst))
    for node in nodes.values():
        for name, expected in REF_FIELDS.get(NodeKind(node.kind), {}).items():
            value = getattr(node, name, None)
            if value is None:
                continue
            if value not in nodes:
                raise UnknownRef(
                    f"{node.id}: поле {name} ссылается на {value}, которого нет в графе"
                )
            if nodes[value].kind != expected:
                raise InvalidLink(
                    f"{node.id}: поле {name} должно указывать на узел вида {expected}, "
                    f"а указывает на {value} ({nodes[value].kind})"
                )


def _not_allowed(src: str, rel: Rel, dst: str) -> str:
    return (
        f"связь {src} -{rel.value}-> {dst} недопустима: "
        f"{rel.value} не соединяет эти виды узлов (таблица допустимых пар — 04_data)"
    )


class ArtifactGraph(BaseModel):
    """Nodes, edges and the high-water marks of the id counters (ids are never reused)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = SCHEMA_VERSION
    nodes: dict[str, Node] = {}
    edges: tuple[Edge, ...] = ()
    high_water: dict[str, int] = {}

    @field_validator("nodes")
    @classmethod
    def _sort_nodes(cls, value: dict[str, Node]) -> dict[str, Node]:
        return dict(sorted(value.items()))

    @field_validator("edges")
    @classmethod
    def _sort_edges(cls, value: tuple[Edge, ...]) -> tuple[Edge, ...]:
        return tuple(sorted(set(value), key=Edge.sort_key))

    @field_validator("high_water")
    @classmethod
    def _sort_high_water(cls, value: dict[str, int]) -> dict[str, int]:
        return dict(sorted(value.items()))

    # --- reading ---------------------------------------------------------------------------

    @classmethod
    def empty(cls) -> "ArtifactGraph":
        return cls()

    @classmethod
    def from_parts(
        cls,
        nodes: Iterable[Node],
        edges: Iterable[Edge],
        high_water: Mapping[str, int] | None = None,
    ) -> "ArtifactGraph":
        """Graph from nodes with ids already issued (a project folder): checks integrity.

        Counters start after the largest id present, or after `high_water` if it is higher.
        """
        by_id: dict[str, Node] = {}
        for node in nodes:
            if node.id in by_id:
                raise DuplicateId(f"узел {node.id} встречается дважды")
            by_id[node.id] = node
        edge_list = list(edges)
        _check_integrity(by_id, edge_list)
        counters = IdAllocator.from_graph(cls(nodes=by_id, high_water=dict(high_water or {})))
        return cls(nodes=by_id, edges=tuple(edge_list), high_water=counters.snapshot())

    def get(self, node_id: str) -> Node | None:
        return self.nodes.get(node_id)

    def nodes_of(self, kind: NodeKind | str) -> list[Node]:
        return [n for n in self.nodes.values() if n.kind == kind]

    def edges_of(self, node_id: str) -> list[Edge]:
        """Edges that start or end at the node or at one of its sub-elements."""
        return [e for e in self.edges if node_id in (_parent(e.src), _parent(e.dst))]

    def approved_ids(self) -> frozenset[str]:
        return frozenset(n.id for n in self.nodes.values() if n.status == "approved")

    def view(self, kinds: Iterable[NodeKind | str]) -> "ArtifactGraph":
        """Sub-graph of the given kinds: their nodes and the edges between them."""
        wanted = {NodeKind(k) for k in kinds}
        nodes = {i: n for i, n in self.nodes.items() if NodeKind(n.kind) in wanted}
        edges = tuple(e for e in self.edges if _parent(e.src) in nodes and _parent(e.dst) in nodes)
        return ArtifactGraph(nodes=nodes, edges=edges, high_water=self.high_water)

    # --- serialization ---------------------------------------------------------------------

    def to_json(self) -> str:
        """Stable text: keys sorted by id, edges sorted, UTF-8 not escaped (diff-friendly)."""
        data = self.model_dump(mode="json", by_alias=True, exclude_none=True)
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "ArtifactGraph":
        try:
            graph = cls.model_validate_json(text)
        except ValidationError as exc:
            raise GraphError(f"граф не загружен: {exc}") from None
        for key, node in graph.nodes.items():
            if key != node.id:
                raise GraphError(f"ключ «{key}» не совпадает с id узла «{node.id}»")
        _check_integrity(graph.nodes, graph.edges)
        return graph

    # --- the only way to change the graph --------------------------------------------------

    def apply(
        self, patch: GraphPatch, ids: IdAllocator | None = None, actor: Actor = "agent"
    ) -> ApplyResult:
        """Apply the whole patch or none of it. `actor="agent"` may not touch approved nodes."""
        return _Apply(self, patch, ids, actor).run()


class _Apply:
    """One run of ArtifactGraph.apply(): works on copies, so a failure leaves nothing behind."""

    def __init__(
        self, graph: ArtifactGraph, patch: GraphPatch, ids: IdAllocator | None, actor: Actor
    ) -> None:
        self.base = graph
        self.patch = patch
        self.user_ids = ids
        self.agent = actor == "agent"
        self.allocator = IdAllocator.from_graph(graph)
        if ids is not None:
            self.allocator = self.allocator.merged(ids)
        self.locked = graph.approved_ids() if self.agent else frozenset[str]()
        self.nodes: dict[str, Node] = dict(graph.nodes)
        self.edges: set[Edge] = set(graph.edges)
        self.id_map: dict[str, str] = {}

    def run(self) -> ApplyResult:
        adds = [op for op in self.patch.ops if isinstance(op, AddOp)]
        self._issue_ids(adds)
        for add in adds:
            self._add(add)
        for op in self.patch.ops:
            match op:
                case LinkOp():
                    self._link(op)
                case UnlinkOp():
                    self._unlink(op)
                case UpdateOp():
                    self._update(op)
                case RemoveOp():
                    self._remove(op)
                case AddOp():
                    pass
        _check_integrity(self.nodes, self.edges)
        graph = ArtifactGraph(
            nodes=self.nodes, edges=tuple(self.edges), high_water=self.allocator.snapshot()
        )
        if self.user_ids is not None:
            self.user_ids.commit(self.allocator)
        return ApplyResult(graph=graph, id_map=self.id_map, diff=self._diff(graph))

    # --- helpers ---------------------------------------------------------------------------

    def _resolve(self, ref: str) -> str:
        if ref in self.id_map:
            return self.id_map[ref]
        if _TMP.fullmatch(ref):
            raise UnknownRef(f"tmp_id «{ref}» не объявлен ни одной операцией add в этом патче")
        return ref

    def _resolve_refs(self, kind: NodeKind, fields: dict[str, Any]) -> dict[str, Any]:
        out = dict(fields)
        for name in REF_FIELDS.get(kind, {}):
            if isinstance(out.get(name), str):
                out[name] = self._resolve(out[name])
        return out

    def _forbid_approval(self, who: str, fields: dict[str, Any]) -> None:
        if self.agent and fields.get("status") == "approved":
            raise LockedNode(
                f"{who}: статус approved агент ставить не может, утверждает только человек"
            )

    def _guard(self, node_id: str, action: str) -> None:
        if node_id in self.locked:
            raise LockedNode(f"{node_id} утверждён человеком: {action} его может только человек")

    # --- add -------------------------------------------------------------------------------

    def _issue_ids(self, adds: list[AddOp]) -> None:
        for op in adds:
            if op.tmp_id in self.id_map:
                raise BadPatch(
                    f"tmp_id «{op.tmp_id}» повторяется: в одном патче он должен быть уникальным"
                )
            self.id_map[op.tmp_id] = self._new_id(op)

    def _new_id(self, op: AddOp) -> str:
        if op.kind is NodeKind.SEC:
            node_id = op.fields.get("id")
            if not isinstance(node_id, str):
                raise BadFields(
                    f"{op.tmp_id}: для узла SEC нужно поле id, id раздела задаёт шаблон документа"
                )
            if node_id in self.nodes or node_id in self.id_map.values():
                raise DuplicateId(f"раздел {node_id} уже есть в графе")
            return node_id
        for forbidden in ("id", "kind"):
            if forbidden in op.fields:
                raise BadFields(
                    f"{op.tmp_id}: поле {forbidden} в add указывать нельзя — id выдаёт код, "
                    "вид задаёт поле kind операции"
                )
        c4_kind = op.fields.get("c4_kind") if op.kind is NodeKind.C4 else None
        try:
            return self.allocator.allocate(op.kind, c4_kind=c4_kind)
        except GraphError:
            raise
        except ValueError as exc:
            raise BadFields(f"{op.tmp_id}: {exc}") from None

    def _add(self, op: AddOp) -> None:
        node_id = self.id_map[op.tmp_id]
        self._forbid_approval(node_id, op.fields)
        data = {**self._resolve_refs(op.kind, op.fields), "id": node_id, "kind": op.kind.value}
        self.nodes[node_id] = node_from_dict(data, f"{node_id} (tmp_id {op.tmp_id})")

    # --- link / unlink ---------------------------------------------------------------------

    def _owners(self, edge: Edge) -> list[str]:
        """Nodes whose description the edge is part of: the source; both ends if symmetric."""
        owners = [_parent(edge.src)]
        if edge.rel is Rel.CONFLICTS_WITH:
            owners.append(_parent(edge.dst))
        return owners

    def _edge(self, op: LinkOp | UnlinkOp) -> Edge:
        return Edge.of(self._resolve(op.src), op.rel, self._resolve(op.dst))

    def _link(self, op: LinkOp) -> None:
        edge = self._edge(op)
        _require(edge.src, self.nodes)
        _require(edge.dst, self.nodes)
        if not allowed(edge.src, edge.rel, edge.dst):
            raise InvalidLink(_not_allowed(edge.src, edge.rel, edge.dst))
        for owner in self._owners(edge):
            self._guard(owner, "менять связи")
        self.edges.add(edge)

    def _unlink(self, op: UnlinkOp) -> None:
        edge = self._edge(op)
        if edge not in self.edges:
            raise UnknownRef(f"связи {_edge_text(edge)} нет в графе")
        for owner in self._owners(edge):
            self._guard(owner, "менять связи")
        self.edges.remove(edge)

    # --- update / remove -------------------------------------------------------------------

    def _existing(self, ref: str) -> str:
        node_id = self._resolve(ref)
        if node_id not in self.nodes:
            raise UnknownRef(f"узла {node_id} нет в графе")
        return node_id

    def _update(self, op: UpdateOp) -> None:
        node_id = self._existing(op.id)
        self._guard(node_id, "менять")
        self._forbid_approval(node_id, op.fields)
        for forbidden in ("id", "kind"):
            if forbidden in op.fields:
                raise BadFields(
                    f"{node_id}: поле {forbidden} нельзя менять, удалите узел и создайте новый"
                )
        old = self.nodes[node_id]
        data = old.model_dump()
        data.update(self._resolve_refs(NodeKind(old.kind), op.fields))
        self.nodes[node_id] = node_from_dict(data, node_id)

    def _remove(self, op: RemoveOp) -> None:
        node_id = self._existing(op.id)
        self._guard(node_id, "удалять")
        cascade = {e for e in self.edges if node_id in (_parent(e.src), _parent(e.dst))}
        for edge in cascade:
            for owner in self._owners(edge):
                if owner != node_id:
                    self._guard(owner, f"убирать связь с удаляемым {node_id}:")
        self.edges -= cascade
        del self.nodes[node_id]

    # --- diff ------------------------------------------------------------------------------

    def _diff(self, graph: ArtifactGraph) -> GraphDiff:
        before, after = self.base, graph
        changed: dict[str, dict[str, tuple[Any, Any]]] = {}
        for node_id, old in before.nodes.items():
            new = after.nodes.get(node_id)
            if new is None or new == old:
                continue
            fields = {
                name: (getattr(old, name), getattr(new, name))
                for name in type(old).model_fields
                if getattr(old, name) != getattr(new, name)
            }
            if fields:
                changed[node_id] = fields
        old_edges, new_edges = set(before.edges), set(after.edges)
        return GraphDiff(
            added=[i for i in self.id_map.values() if i in after.nodes],
            removed=sorted(set(before.nodes) - set(after.nodes)),
            changed=changed,
            linked=sorted(new_edges - old_edges, key=Edge.sort_key),
            unlinked=sorted(old_edges - new_edges, key=Edge.sort_key),
        )
