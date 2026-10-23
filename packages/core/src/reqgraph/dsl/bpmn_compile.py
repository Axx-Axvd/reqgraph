"""Compiler: process DSL v1 -> BPMN 2.0 XML with lanes and diagram (DI). The LLM never writes XML.

Element ids are graph references: step T05 of PRC-01 is `PRC-01.T05` (the same string as in
`realized_by`), flows are `PRC-01.F01`, so a finding on the BPMN points straight at the graph.
"""

from lxml import etree

from reqgraph.dsl.layout import Bounds, layout
from reqgraph.dsl.process import ProcessDSL, ProcessElement, ref

MODEL = "http://www.omg.org/spec/BPMN/20100524/MODEL"
NS = {
    "bpmn": MODEL,
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}
TAG = {
    "start": "startEvent",
    "end": "endEvent",
    "task": "task",
    "user_task": "userTask",
    "service_task": "serviceTask",
    "timer": "intermediateCatchEvent",
    "message": "intermediateCatchEvent",
    "xor": "exclusiveGateway",
    "and": "parallelGateway",
    "event_based": "eventBasedGateway",
}


def _q(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


def _sub(parent: etree._Element, prefix: str, tag: str, **attrs: str) -> etree._Element:
    """Child element; empty attributes (a step without a name) are left out."""
    return etree.SubElement(parent, _q(prefix, tag), {k: v for k, v in attrs.items() if v})


def _bounds(parent: etree._Element, box: Bounds) -> None:
    _sub(parent, "dc", "Bounds", x=str(box.x), y=str(box.y), width=str(box.w), height=str(box.h))


def _event_definition(node: etree._Element, element: ProcessElement, dsl: ProcessDSL) -> None:
    kind = element.event or (element.type if element.type in ("timer", "message") else None)
    if kind == "message":
        _sub(node, "bpmn", "messageEventDefinition", id=f"{ref(dsl, element.id)}.def")
    elif kind == "timer":
        definition = _sub(node, "bpmn", "timerEventDefinition", id=f"{ref(dsl, element.id)}.def")
        when = _sub(definition, "bpmn", "timeDate")
        when.set(_q("xsi", "type"), "bpmn:tFormalExpression")
        when.text = element.timer


def compile_bpmn(dsl: ProcessDSL) -> str:
    """BPMN 2.0 XML text: deterministic (same DSL -> same bytes), UTF-8, LF line ends."""
    geometry = layout(dsl)
    flows = dsl.flow_list()
    root = etree.Element(
        _q("bpmn", "definitions"),
        {
            "id": f"{dsl.id}.definitions",
            "targetNamespace": f"urn:reqgraph:process:{dsl.id}",
            "exporter": "reqgraph",
        },
        nsmap=NS,
    )
    pool_id = f"{dsl.id}.pool"
    if dsl.lanes:
        collaboration = _sub(root, "bpmn", "collaboration", id=f"{dsl.id}.collaboration")
        _sub(collaboration, "bpmn", "participant", id=pool_id, name=dsl.name, processRef=dsl.id)
    process = _sub(root, "bpmn", "process", id=dsl.id, name=dsl.name, isExecutable="false")

    lane_ids: dict[str, str] = {}
    if dsl.lanes:
        lane_set = _sub(process, "bpmn", "laneSet", id=f"{dsl.id}.lanes")
        for index, lane in enumerate(dsl.lanes, 1):
            lane_ids[lane] = f"{dsl.id}.L{index}"
            node = _sub(lane_set, "bpmn", "lane", id=lane_ids[lane], name=lane)
            for element in dsl.nodes:
                if geometry.lane_of[element.id] == lane:
                    _sub(node, "bpmn", "flowNodeRef").text = ref(dsl, element.id)

    for element in dsl.nodes:
        node = _sub(process, "bpmn", TAG[element.type], id=ref(dsl, element.id), name=element.name)
        for flow in flows:
            if flow.dst == element.id:
                _sub(node, "bpmn", "incoming").text = ref(dsl, flow.id)
        for flow in flows:
            if flow.src == element.id:
                _sub(node, "bpmn", "outgoing").text = ref(dsl, flow.id)
        _event_definition(node, element, dsl)
    for flow in flows:
        _sub(
            process,
            "bpmn",
            "sequenceFlow",
            id=ref(dsl, flow.id),
            name=flow.label,
            sourceRef=ref(dsl, flow.src),
            targetRef=ref(dsl, flow.dst),
        )

    diagram = _sub(root, "bpmndi", "BPMNDiagram", id=f"{dsl.id}.diagram")
    plane = _sub(
        diagram,
        "bpmndi",
        "BPMNPlane",
        id=f"{dsl.id}.plane",
        bpmnElement=f"{dsl.id}.collaboration" if dsl.lanes else dsl.id,
    )
    if geometry.pool is not None:
        shape = _sub(plane, "bpmndi", "BPMNShape", id=f"{pool_id}.di", bpmnElement=pool_id)
        shape.set("isHorizontal", "true")
        _bounds(shape, geometry.pool)
        for lane, box in geometry.lanes.items():
            shape = _sub(
                plane, "bpmndi", "BPMNShape", id=f"{lane_ids[lane]}.di", bpmnElement=lane_ids[lane]
            )
            shape.set("isHorizontal", "true")
            _bounds(shape, box)
    for element in dsl.nodes:
        element_ref = ref(dsl, element.id)
        shape = _sub(plane, "bpmndi", "BPMNShape", id=f"{element_ref}.di", bpmnElement=element_ref)
        if element.type == "xor":
            shape.set("isMarkerVisible", "true")
        _bounds(shape, geometry.shapes[element.id])
    for flow in flows:
        flow_ref = ref(dsl, flow.id)
        edge = _sub(plane, "bpmndi", "BPMNEdge", id=f"{flow_ref}.di", bpmnElement=flow_ref)
        points = geometry.waypoints[flow.id]
        for point in points:
            _sub(edge, "di", "waypoint", x=str(point.x), y=str(point.y))
        if flow.label:
            label = _sub(edge, "bpmndi", "BPMNLabel")
            before, end = points[-2], points[-1]  # near the target: labels of one gateway differ
            _bounds(
                label, Bounds((before.x + end.x) // 2 - 15, (before.y + end.y) // 2 - 20, 30, 14)
            )

    text: bytes = etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8")
    return text.decode("utf-8")
