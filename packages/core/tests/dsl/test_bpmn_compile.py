"""DSL -> BPMN 2.0 XML: element per type, ids = graph references, lanes, labels (T-103)."""

from lxml import etree
from reqgraph.dsl.bpmn_compile import NS, compile_bpmn
from reqgraph.dsl.process import parse_process

from .conftest import all_processes, load


def tree(name: str) -> etree._Element:
    xml = compile_bpmn(parse_process(load(all_processes()[name])))
    return etree.fromstring(xml.encode("utf-8"))


def find(root: etree._Element, xpath: str) -> list[etree._Element]:
    found: list[etree._Element] = root.xpath(xpath, namespaces=NS)
    return found


def test_each_type_becomes_its_bpmn_element() -> None:
    root = tree("PRC-02_reminder")
    tags = {e.get("id"): etree.QName(e).localname for e in find(root, "//bpmn:process/*[@id]")}
    assert tags["PRC-02.S"] == "startEvent"
    assert tags["PRC-02.T01"] == "serviceTask"
    assert tags["PRC-02.G01"] == "eventBasedGateway"
    assert tags["PRC-02.M01"] == "intermediateCatchEvent"
    assert tags["PRC-02.W01"] == "intermediateCatchEvent"
    assert tags["PRC-02.E1"] == "endEvent"
    assert find(root, "//*[@id='PRC-02.W01']/bpmn:timerEventDefinition/bpmn:timeDate")
    assert find(root, "//*[@id='PRC-02.M01']/bpmn:messageEventDefinition")
    assert find(root, "//*[@id='PRC-02.S']/bpmn:timerEventDefinition")


def test_other_types() -> None:
    root = tree("PRC-01_booking")
    assert find(root, "//bpmn:userTask[@id='PRC-01.T01']")
    assert find(root, "//bpmn:exclusiveGateway[@id='PRC-01.G01']")
    assert find(tree("parallel"), "//bpmn:parallelGateway[@id='PRC-12.G01']")
    assert find(tree("linear"), "//bpmn:task[@id='PRC-11.T01']")
    assert find(tree("message_start"), "//bpmn:startEvent/bpmn:messageEventDefinition")


def test_ids_are_the_references_used_by_the_graph() -> None:
    root = tree("PRC-01_booking")
    ids = {e.get("id") for e in find(root, "//bpmn:process/*[@id]")}
    assert {"PRC-01.T05", "PRC-01.G02", "PRC-01.F01"} <= ids


def test_flows_carry_branch_labels_and_node_links() -> None:
    root = tree("PRC-01_booking")
    (yes,) = find(root, "//bpmn:sequenceFlow[@sourceRef='PRC-01.G01'][@targetRef='PRC-01.T04']")
    assert yes.get("name") == "да"
    outgoing = [e.text for e in find(root, "//*[@id='PRC-01.G01']/bpmn:outgoing")]
    assert len(outgoing) == 2
    incoming = [e.text for e in find(root, "//*[@id='PRC-01.G02']/bpmn:incoming")]
    assert len(incoming) == 2  # from T02 and back from T06


def test_lanes_hold_their_elements() -> None:
    root = tree("PRC-01_booking")
    lanes = {
        lane.get("name"): {r.text for r in find(lane, "bpmn:flowNodeRef")}
        for lane in find(root, "//bpmn:lane")
    }
    assert "PRC-01.T01" in lanes["Клиент"] and "PRC-01.T04" in lanes["Система"]
    assert find(root, "//bpmn:participant[@processRef='PRC-01']")


def test_without_lanes_there_is_no_collaboration() -> None:
    root = tree("linear")
    assert not find(root, "//bpmn:collaboration") and not find(root, "//bpmn:laneSet")
    (plane,) = find(root, "//bpmndi:BPMNPlane")
    assert plane.get("bpmnElement") == "PRC-11"


def test_every_element_and_flow_has_a_diagram_shape() -> None:
    root = tree("PRC-01_booking")
    drawn = {e.get("bpmnElement") for e in find(root, "//bpmndi:BPMNShape|//bpmndi:BPMNEdge")}
    semantic = {e.get("id") for e in find(root, "//bpmn:process/*[@id]")} - {"PRC-01.lanes"}
    assert semantic <= drawn


def test_output_is_deterministic_and_unix_text() -> None:
    dsl = parse_process(load(all_processes()["PRC-01_booking"]))
    xml = compile_bpmn(dsl)
    assert xml == compile_bpmn(dsl)
    assert xml.startswith("<?xml") and xml.endswith("\n") and "\r" not in xml
