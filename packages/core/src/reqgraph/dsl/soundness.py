"""Soundness of a process through pm4py (ADR-014): the DSL -> «soundness view» -> Petri net.

pm4py's BPMN converter knows tasks, start/end events and xor/and gateways only, so the view
turns an event-based gateway into xor (a deferred choice is a choice) and intermediate timer and
message events into tasks — equivalent for soundness. pm4py (AGPL, +160 MB, seconds to import)
is imported here, lazily: only the check SND-002 calls this module.
"""

import contextlib
import io
import warnings

from reqgraph.dsl.process import TASKS, ProcessDSL


def is_sound(dsl: ProcessDSL) -> bool:
    """True when the process is a sound workflow net: it can always finish, nothing hangs."""
    from pm4py.algo.analysis.woflan import algorithm as woflan
    from pm4py.objects.bpmn.obj import BPMN
    from pm4py.objects.conversion.bpmn import converter

    bpmn = BPMN()
    nodes = {}
    for element in dsl.nodes:
        if element.type == "start":
            node = BPMN.StartEvent(name=element.id)
        elif element.type == "end":
            node = BPMN.EndEvent(name=element.id)
        elif element.type in ("xor", "event_based"):
            node = BPMN.ExclusiveGateway(name=element.id)
        elif element.type == "and":
            node = BPMN.ParallelGateway(name=element.id)
        else:  # tasks, intermediate timer and message events
            assert element.type in TASKS | {"timer", "message"}
            node = BPMN.Task(name=element.id)
        nodes[element.id] = node
        bpmn.add_node(node)
    for flow in dsl.flow_list():
        bpmn.add_flow(BPMN.SequenceFlow(nodes[flow.src], nodes[flow.dst]))
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("ignore")  # pm4py: scipy precision notes, deprecations
        net, initial, final = converter.apply(bpmn)
        params = {
            woflan.Parameters.RETURN_ASAP_WHEN_NOT_SOUND: True,
            woflan.Parameters.PRINT_DIAGNOSTICS: False,
            woflan.Parameters.RETURN_DIAGNOSTICS: False,
        }
        return bool(woflan.apply(net, initial, final, parameters=params))
