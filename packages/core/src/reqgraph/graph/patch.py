"""GraphPatch: the only way to change the graph (public schema v1, graph-patch.schema.json)."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from reqgraph.graph.edges import Rel
from reqgraph.graph.nodes import NodeKind

SCHEMA_VERSION: Literal[1] = 1
TMP_ID = r"^[a-z][a-z0-9_]{0,31}$"  # never looks like a real id (those contain a dash)


class _Op(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class AddOp(_Op):
    """Create a node. The id is issued by code; `tmp_id` names the node inside this patch."""

    op: Literal["add"]
    kind: NodeKind
    tmp_id: str = Field(pattern=TMP_ID)
    fields: dict[str, Any] = Field(default_factory=dict)


class LinkOp(_Op):
    """Add an edge. `from`/`to`: real ids, sub-element refs (PRC-01.T05) or tmp_ids of the patch."""

    op: Literal["link"]
    src: str = Field(alias="from", min_length=1)
    rel: Rel
    dst: str = Field(alias="to", min_length=1)


class UnlinkOp(_Op):
    op: Literal["unlink"]
    src: str = Field(alias="from", min_length=1)
    rel: Rel
    dst: str = Field(alias="to", min_length=1)


class UpdateOp(_Op):
    """Change fields of an existing node; `id` and `kind` cannot be changed."""

    op: Literal["update"]
    id: str = Field(min_length=1)
    fields: dict[str, Any]


class RemoveOp(_Op):
    """Delete a node and the edges that touch it. The reason is recorded in the history."""

    op: Literal["remove"]
    id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


Op = Annotated[AddOp | LinkOp | UnlinkOp | UpdateOp | RemoveOp, Field(discriminator="op")]


class GraphPatch(BaseModel):
    """Output of any agent. Applied all-or-nothing by ArtifactGraph.apply()."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = SCHEMA_VERSION
    ops: list[Op]
    rationale: str = ""

    def stats(self) -> dict[str, int]:
        counts = {"add": 0, "link": 0, "unlink": 0, "update": 0, "remove": 0}
        for op in self.ops:
            counts[op.op] += 1
        return counts
