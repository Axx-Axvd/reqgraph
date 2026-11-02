"""Requirements as ReqIF 1.2 (T-403): the exchange format of DOORS, Polarion, Jama and StrictDoc.

Built with the `reqif` library by the StrictDoc authors (Apache-2.0), imported lazily: only the
export needs it. The layout follows StrictDoc's own ReqIF profile, so StrictDoc imports the file
with its fields: SECTION objects (`ReqIF.ChapterName`) hold REQUIREMENT objects (`ReqIF.ForeignID`
= the node id, `ReqIF.Name`, `ReqIF.Text`) and refines is the Parent relation, from the refining
requirement to the refined one. Identifiers come from node ids and the creation time is a
parameter: the same graph gives the same file.

Text (names, statements, criteria) is XHTML, as DOORS writes ReqIF.Text too: StrictDoc 0.30.4 runs
string values through `unicode_escape`, which breaks UTF-8 Cyrillic, and takes XHTML as it is.
Codes (ids, status, priority) stay plain strings.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from reqgraph.graph.edges import Rel
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import (
    BusinessReq,
    Constraint,
    FunctionalReq,
    Node,
    NonFunctionalReq,
    UserReq,
)
from reqgraph.graph.store.project import Project

FILE = "req.reqif"
CHAPTERS = (
    ("BR", "Бизнес-требования"),
    ("UR", "Пользовательские требования"),
    ("FR", "Функциональные требования"),
    ("NFR", "Нефункциональные требования"),
    ("CON", "Ограничения"),
)
LINE, TEXT = "DT-LINE", "DT-TEXT"  # a code (plain string) and text (XHTML)
SECTION, REQUIREMENT, SPECIFICATION_TYPE = "SOT-SECTION", "SOT-REQUIREMENT", "ST-DOCUMENT"
PARENT = "SRT-PARENT"
REQUIREMENT_FIELDS = (
    ("ReqIF.ForeignID", LINE),
    ("ReqIF.Name", TEXT),
    ("ReqIF.Text", TEXT),
    ("STATUS", LINE),
    ("PRIORITY", LINE),
    ("ACCEPTANCE", TEXT),
    ("METRIC", TEXT),
    ("QUALITY", LINE),
    ("SCENARIO", TEXT),
    ("GOAL", TEXT),
    ("CONSTRAINT_TYPE", LINE),
    ("ASSUMPTION", LINE),
    ("REALIZED_BY", LINE),
    ("DEPENDS_ON", LINE),  # StrictDoc knows only Parent, Child and File relations
    ("CONFLICTS_WITH", LINE),
)
SECTION_FIELDS = (("ReqIF.ChapterName", TEXT),)


def _definition(spec_type: str, name: str) -> str:
    return f"{spec_type}-{name}"


def _xhtml(text: str) -> str:
    """Text as an XHTML fragment: one paragraph per line."""
    lines = [escape(line, quote=False) for line in text.splitlines() if line.strip()]
    return "<xhtml:div>" + "".join(f"<xhtml:p>{line}</xhtml:p>" for line in lines) + "</xhtml:div>"


def _targets(graph: ArtifactGraph, src: str, rel: Rel) -> list[str]:
    return sorted(e.dst for e in graph.edges if e.src == src and e.rel is rel)


def _fields(node: Node, graph: ArtifactGraph) -> dict[str, str]:
    """The values of one requirement, empty ones left out."""
    values: dict[str, str] = {
        "ReqIF.ForeignID": node.id,
        "ReqIF.Name": getattr(node, "title", ""),
        "ReqIF.Text": getattr(node, "statement", ""),
        "STATUS": node.status,
        "PRIORITY": getattr(node, "priority", None) or "",
        "ASSUMPTION": "true" if node.assumption else "",
    }
    if isinstance(node, FunctionalReq):
        values["ACCEPTANCE"] = "\n".join(node.acceptance)
    if isinstance(node, NonFunctionalReq):
        metric = node.metric
        values["METRIC"] = " ".join(
            str(p) for p in (metric.name, metric.threshold, metric.unit) if p
        )
        values["QUALITY"] = node.iso25010
    if isinstance(node, UserReq):
        values["SCENARIO"] = "\n".join(f"{i}. {s}" for i, s in enumerate(node.scenario, 1))
    if isinstance(node, BusinessReq) and node.goal_metric is not None:
        goal = node.goal_metric
        values["GOAL"] = " ".join(str(p) for p in (goal.name, goal.target, goal.unit) if p)
    if isinstance(node, Constraint):
        values["CONSTRAINT_TYPE"] = node.type
    values["REALIZED_BY"] = ", ".join(_targets(graph, node.id, Rel.REALIZED_BY))
    values["DEPENDS_ON"] = ", ".join(_targets(graph, node.id, Rel.DEPENDS_ON))
    conflicts = {e.dst for e in graph.edges if e.src == node.id and e.rel is Rel.CONFLICTS_WITH}
    conflicts |= {e.src for e in graph.edges if e.dst == node.id and e.rel is Rel.CONFLICTS_WITH}
    values["CONFLICTS_WITH"] = ", ".join(sorted(conflicts))
    return {k: v for k, v in values.items() if v}


def build_bundle(project: Project, *, created: str) -> Any:
    """The project's requirements as a ReqIFBundle of the reqif library."""
    from reqif.models.reqif_core_content import ReqIFCoreContent
    from reqif.models.reqif_data_type import (
        ReqIFDataTypeDefinitionString,
        ReqIFDataTypeDefinitionXHTML,
    )
    from reqif.models.reqif_namespace_info import ReqIFNamespaceInfo
    from reqif.models.reqif_req_if_content import ReqIFReqIFContent
    from reqif.models.reqif_reqif_header import ReqIFReqIFHeader
    from reqif.models.reqif_spec_hierarchy import ReqIFSpecHierarchy
    from reqif.models.reqif_spec_object import ReqIFSpecObject, SpecObjectAttribute
    from reqif.models.reqif_spec_object_type import ReqIFSpecObjectType, SpecAttributeDefinition
    from reqif.models.reqif_spec_relation import ReqIFSpecRelation
    from reqif.models.reqif_spec_relation_type import ReqIFSpecRelationType
    from reqif.models.reqif_specification import ReqIFSpecification
    from reqif.models.reqif_specification_type import ReqIFSpecificationType
    from reqif.models.reqif_types import SpecObjectAttributeType
    from reqif.object_lookup import ReqIFObjectLookup
    from reqif.reqif_bundle import ReqIFBundle

    graph, info = project.graph, project.config.project
    kinds = {LINE: SpecObjectAttributeType.STRING, TEXT: SpecObjectAttributeType.XHTML}
    datatypes = {
        f"{t}-{name}": datatype
        for t, fs in ((SECTION, SECTION_FIELDS), (REQUIREMENT, REQUIREMENT_FIELDS))
        for name, datatype in fs
    }

    def object_type(identifier: str, name: str, fields: Sequence[tuple[str, str]]) -> Any:
        return ReqIFSpecObjectType(
            identifier=identifier,
            last_change=created,
            long_name=name,
            attribute_definitions=[
                SpecAttributeDefinition(
                    attribute_type=kinds[datatype],
                    identifier=_definition(identifier, field),
                    datatype_definition=datatype,
                    last_change=created,
                    long_name=field,
                )
                for field, datatype in fields
            ],
        )

    def spec_object(identifier: str, spec_type: str, values: dict[str, str]) -> Any:
        return ReqIFSpecObject(
            identifier=identifier,
            attributes=[
                SpecObjectAttribute(
                    attribute_type=kinds[datatypes[_definition(spec_type, field)]],
                    definition_ref=_definition(spec_type, field),
                    value=(
                        _xhtml(value)
                        if datatypes[_definition(spec_type, field)] == TEXT
                        else escape(value, quote=True)
                    ),
                )
                for field, value in values.items()
            ],
            spec_object_type=spec_type,
            last_change=created,
        )

    objects, hierarchy = [], []
    for kind, chapter in CHAPTERS:
        section_id = f"SEC-{kind}"
        objects.append(spec_object(section_id, SECTION, {"ReqIF.ChapterName": chapter}))
        children = []
        for node in graph.nodes_of(kind):
            objects.append(spec_object(f"REQ-{node.id}", REQUIREMENT, _fields(node, graph)))
            children.append(
                ReqIFSpecHierarchy(
                    xml_node=None,
                    is_self_closed=False,
                    identifier=f"H-{node.id}",
                    last_change=created,
                    spec_object=f"REQ-{node.id}",
                    level=2,
                )
            )
        hierarchy.append(
            ReqIFSpecHierarchy(
                xml_node=None,
                is_self_closed=False,
                identifier=f"H-{section_id}",
                last_change=created,
                spec_object=section_id,
                children=children or None,
                level=1,
            )
        )
    requirement_ids = {n.id for kind, _ in CHAPTERS for n in graph.nodes_of(kind)}
    relations = [
        ReqIFSpecRelation(
            identifier=f"REL-{e.src}-{e.dst}",
            relation_type_ref=PARENT,
            source=f"REQ-{e.src}",
            target=f"REQ-{e.dst}",
            last_change=created,
        )
        for e in sorted(graph.edges, key=lambda e: (e.src, e.dst))
        if e.rel is Rel.REFINES and e.src in requirement_ids and e.dst in requirement_ids
    ]
    content = ReqIFReqIFContent(
        data_types=[
            ReqIFDataTypeDefinitionString(
                identifier=LINE, last_change=created, long_name="Код", max_length="10000"
            ),
            ReqIFDataTypeDefinitionXHTML(
                identifier=TEXT, last_change=created, long_name="Текст", is_self_closed=True
            ),
        ],
        spec_types=[
            ReqIFSpecificationType(
                identifier=SPECIFICATION_TYPE,
                last_change=created,
                long_name="Документ",
                is_self_closed=True,
            ),
            object_type(SECTION, "SECTION", SECTION_FIELDS),
            object_type(REQUIREMENT, "REQUIREMENT", REQUIREMENT_FIELDS),
            ReqIFSpecRelationType(identifier=PARENT, last_change=created, long_name="Parent"),
        ],
        spec_objects=objects,
        spec_relations=relations,
        specifications=[
            ReqIFSpecification(
                identifier=f"SPEC-{info.id}",
                last_change=created,
                long_name=info.name,
                specification_type=SPECIFICATION_TYPE,
                children=hierarchy,
            )
        ],
    )
    header = ReqIFReqIFHeader(
        identifier=f"HEADER-{info.id}",
        creation_time=created,
        req_if_tool_id="reqgraph",
        req_if_version="1.0",
        source_tool_id="reqgraph",
        title=f"{info.name}: требования",
    )
    namespace = ReqIFNamespaceInfo.create_default()
    return ReqIFBundle(
        namespace_info=namespace,
        req_if_header=header,
        core_content=ReqIFCoreContent(req_if_content=content),
        tool_extensions_tag_exists=False,
        lookup=ReqIFObjectLookup.empty(),
        exceptions=[],
    )


def write_reqif(project: Project, out: Path, *, created: str | None = None) -> Path:
    """Write out/req.reqif; `created` (ISO 8601) fixes the time for a stable file."""
    from reqif.unparser import ReqIFUnparser

    stamp = created or datetime.now(UTC).replace(microsecond=0).isoformat()
    out.mkdir(parents=True, exist_ok=True)
    path = out / FILE
    text = ReqIFUnparser.unparse(build_bundle(project, created=stamp))
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def schema_errors(path: Path) -> list[str]:
    """Errors of the file against the ReqIF 1.2 schema shipped with the reqif library (offline)."""
    from importlib.resources import files

    import xmlschema

    xsd = files("reqif").joinpath("reqif_schema", "reqif.xsd")
    schema = xmlschema.XMLSchema(str(xsd))
    return [str(e.reason or e) for e in schema.iter_errors(str(path))]
