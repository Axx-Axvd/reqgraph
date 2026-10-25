"""Quality metrics of a saved project from the deterministic checks (09_eval, no LLM).

ambiguity — share of requirements with ISO-001…004 findings; validity — share of models (each
process and the ERD) without SCH errors; soundness — share of processes without SND errors;
trace coverage — share of FR realized in a model (TRC-002); orphan rate — share of the elements
TRC-003 looks at that realize no requirement. Completeness of the SRS (TPL) comes with the export
(T-401): the sections are not stored in the project yet.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from reqgraph.checks.report import CIReport
from reqgraph.checks.runner import run_checks
from reqgraph.dsl.process import TASKS, DslError, parse_process
from reqgraph.dsl.readers import model_readers
from reqgraph.graph.edges import Rel
from reqgraph.graph.nodes import C4Node, ProcessNode
from reqgraph.graph.store import FileStore

AMBIGUITY = ("ISO-001", "ISO-002", "ISO-003", "ISO-004")
KINDS = ("BR", "UR", "FR", "NFR", "CON")


def model_elements(graph: Any) -> int:
    """What TRC-003 looks at: entities, use cases, C4 containers and externals, process tasks."""
    count = len(graph.nodes_of("ENT")) + len(graph.nodes_of("UC"))
    count += sum(
        1
        for n in graph.nodes_of("C4")
        if isinstance(n, C4Node) and n.c4_kind in ("container", "external")
    )
    for node in graph.nodes_of("PRC"):
        if isinstance(node, ProcessNode):
            try:
                count += sum(1 for el in parse_process(node.dsl or {}).nodes if el.type in TASKS)
            except DslError:
                continue
    return count


@dataclass
class Quality:
    requirements: int = 0
    ambiguity: float = 0.0
    model_count: int = 0  # processes and the ERD
    validity: float = 0.0
    processes: int = 0
    soundness: float = 0.0
    trace_coverage: float = 0.0
    orphan_rate: float = 0.0
    errors: int = 0
    warnings: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _share(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


async def quality(root: Path) -> Quality:
    project = FileStore(root, readers=model_readers()).load()
    report = await run_checks(project, offline=True)
    return measure(project.graph, report, has_erd=bool(project.graph.nodes_of("ENT")))


def measure(graph: Any, report: CIReport, *, has_erd: bool) -> Quality:
    def first(node_ids: list[str]) -> str:
        return node_ids[0].split(".")[0] if node_ids else ""

    requirements = [n.id for kind in KINDS for n in graph.nodes_of(kind)]
    vague = {
        n
        for f in report.findings
        if f.check_id in AMBIGUITY
        for n in f.node_ids
        if n in requirements
    }
    processes = [n.id for n in graph.nodes_of("PRC")]
    errors = [f for f in report.findings if f.severity == "error"]
    bad_models = {first(f.node_ids) for f in errors if f.check_id.startswith("SCH")}
    erd_broken = any(f.check_id == "SCH-003" for f in errors)
    models = len(processes) + int(has_erd)
    valid = sum(p not in bad_models for p in processes) + int(has_erd and not erd_broken)
    unsound = {first(f.node_ids) for f in errors if f.check_id.startswith("SND")}
    frs = [n.id for n in graph.nodes_of("FR")]
    realized = {e.src for e in graph.edges if e.rel is Rel.REALIZED_BY}
    orphans = {n for f in report.findings if f.check_id == "TRC-003" for n in f.node_ids}
    return Quality(
        requirements=len(requirements),
        ambiguity=_share(len(vague), len(requirements)),
        model_count=models,
        validity=_share(valid, models),
        processes=len(processes),
        soundness=_share(sum(p not in unsound for p in processes), len(processes)),
        trace_coverage=_share(sum(f in realized for f in frs), len(frs)),
        orphan_rate=_share(len(orphans), model_elements(graph)),
        errors=report.summary.errors,
        warnings=report.summary.warnings,
    )
