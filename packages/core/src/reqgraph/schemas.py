"""Public JSON Schemas generated from Pydantic: `uv run reqgraph schemas` writes schemas/*.json."""

import json

from pydantic import BaseModel

from reqgraph.dsl.process import ProcessDSL
from reqgraph.graph import ArtifactGraph, GraphPatch
from reqgraph.graph.store import ProjectConfig

SCHEMAS: dict[str, type[BaseModel]] = {
    "graph-patch": GraphPatch,
    "artifact-graph": ArtifactGraph,
    "project-config": ProjectConfig,
    "process-dsl": ProcessDSL,
}


def render(name: str) -> str:
    """Schema text with a stable key order and a trailing newline (same bytes on every OS)."""
    schema = SCHEMAS[name].model_json_schema(by_alias=True)
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
