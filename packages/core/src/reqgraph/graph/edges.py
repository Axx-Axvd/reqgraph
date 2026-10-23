"""Edges of the artifact graph and the rules of which node kinds a relation may join."""

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from reqgraph.graph.nodes import NodeKind


class Rel(StrEnum):
    REFINES = "refines"  # UR->BR, FR/NFR->UR
    REALIZED_BY = "realized_by"  # FR -> process task, UC, entity, C4 element
    DERIVED_FROM = "derived_from"  # requirement or actor -> interview turn
    RENDERED_IN = "rendered_in"  # node -> document section
    CONFLICTS_WITH = "conflicts_with"  # requirement <-> requirement (symmetric)
    DEPENDS_ON = "depends_on"  # FR -> FR


_REQUIREMENTS = frozenset({NodeKind.BR, NodeKind.UR, NodeKind.FR, NodeKind.NFR, NodeKind.CON})
_MODEL_ELEMENTS = frozenset({NodeKind.PRC, NodeKind.UC, NodeKind.ENT, NodeKind.C4})

# relation -> (allowed kinds at the source, allowed kinds at the target)
RULES: dict[Rel, tuple[frozenset[NodeKind], frozenset[NodeKind]]] = {
    Rel.REFINES: (
        frozenset({NodeKind.UR, NodeKind.FR, NodeKind.NFR}),
        frozenset({NodeKind.BR, NodeKind.UR}),
    ),
    Rel.REALIZED_BY: (frozenset({NodeKind.FR}), _MODEL_ELEMENTS),
    Rel.DERIVED_FROM: (_REQUIREMENTS | {NodeKind.ACT}, frozenset({NodeKind.TURN})),
    Rel.RENDERED_IN: (
        frozenset(NodeKind) - {NodeKind.SEC, NodeKind.TURN},
        frozenset({NodeKind.SEC}),
    ),
    Rel.CONFLICTS_WITH: (_REQUIREMENTS, _REQUIREMENTS),
    Rel.DEPENDS_ON: (frozenset({NodeKind.FR}), frozenset({NodeKind.FR})),
}
# `refines` is directional per source kind: UR -> BR, FR/NFR -> UR (not FR -> BR, not UR -> UR).
REFINES_PAIRS = {
    NodeKind.UR: frozenset({NodeKind.BR}),
    NodeKind.FR: frozenset({NodeKind.UR}),
    NodeKind.NFR: frozenset({NodeKind.UR}),
}
# Kinds whose elements may be referenced inside: PRC-01.T05 (task), ENT-01.status (attribute).
SUBELEMENT_KINDS = frozenset({NodeKind.PRC, NodeKind.ENT})
_PREFIX = re.compile(r"^(C4|[A-Z]+)-")


def kind_of(ref: str) -> NodeKind:
    """Kind of a node id or of a reference to a sub-element (`PRC-01.T05` -> PRC)."""
    match = _PREFIX.match(ref)
    if match is None:
        raise ValueError(f"не похоже на id узла: «{ref}»")
    try:
        return NodeKind(match.group(1))
    except ValueError:
        raise ValueError(f"неизвестный вид узла в «{ref}»") from None


def split_ref(ref: str) -> tuple[str, str | None]:
    """`PRC-01.T05` -> (`PRC-01`, `T05`); other kinds are never split (SEC-SRS-3.2)."""
    parent, dot, sub = ref.partition(".")
    if dot and kind_of(parent) in SUBELEMENT_KINDS:
        return parent, sub
    return ref, None


def allowed(src: str, rel: Rel, dst: str) -> bool:
    """May `src` be joined to `dst` by `rel`? Existence of the nodes is checked elsewhere."""
    try:
        (src_parent, src_sub), (dst_parent, _) = split_ref(src), split_ref(dst)
        src_kind, dst_kind = kind_of(src_parent), kind_of(dst_parent)
    except ValueError:
        return False
    if src_sub is not None:  # edges start at nodes, not at their elements
        return False
    sources, targets = RULES[rel]
    if src_kind not in sources or dst_kind not in targets:
        return False
    if rel is Rel.REFINES:
        return dst_kind in REFINES_PAIRS[src_kind]
    return True


class Edge(BaseModel):
    """Immutable, hashable edge. JSON uses `from` and `to`, like trace/edges.yaml."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    src: str = Field(alias="from")
    rel: Rel
    dst: str = Field(alias="to")

    @model_validator(mode="before")
    @classmethod
    def _order_symmetric(cls, data: Any) -> Any:
        """conflicts_with has no direction: store it once, smaller id first."""
        if isinstance(data, dict):
            src_key = "from" if "from" in data else "src"
            dst_key = "to" if "to" in data else "dst"
            swap = (
                data.get("rel") == Rel.CONFLICTS_WITH
                and src_key in data
                and dst_key in data
                and data[src_key] > data[dst_key]
            )
            if swap:
                return {**data, src_key: data[dst_key], dst_key: data[src_key]}
        return data

    @classmethod
    def of(cls, src: str, rel: Rel | str, dst: str) -> "Edge":
        return cls.model_validate({"from": src, "rel": rel, "to": dst})

    def sort_key(self) -> tuple[str, str, str]:
        return (self.src, self.rel.value, self.dst)
