"""Running checks on a project: statuses, skipped, crashed checks, determinism (T-105)."""

import asyncio
from pathlib import Path

from reqgraph.checks.report import CIReport
from reqgraph.checks.runner import run_checks
from reqgraph.dsl.readers import model_readers
from reqgraph.graph.store import FileStore

from .conftest import training_registry


def run(folder: Path, offline: bool = True) -> CIReport:
    project = FileStore(folder, readers=model_readers()).load()
    return asyncio.run(run_checks(project, training_registry().checks(), offline=offline))


def test_statuses_of_checks(garage61: Path) -> None:
    status = {c.id: c.status for c in run(garage61).checks}
    assert status == {
        "ISO-900": "warning",
        "SCH-900": "skipped",
        "SND-900": "passed",
        "TPL-900": "failed",
        "TRC-900": "failed",
    }


def test_summary_counts(garage61: Path) -> None:
    report = run(garage61)
    errors = sum(f.severity == "error" for f in report.findings)
    assert report.summary.errors == errors > 0
    assert (report.summary.passed, report.summary.skipped) == (1, 1)
    assert not report.ok


def test_skipped_check_leaves_an_info_finding(garage61: Path) -> None:
    (skip,) = [f for f in run(garage61).findings if f.check_id == "SCH-900"]
    assert skip.severity == "info" and "Kroki" in skip.message


def test_crashed_check_is_an_error_not_a_lost_report(garage61: Path) -> None:
    (crash,) = [f for f in run(garage61).findings if f.check_id == "TPL-900"]
    assert crash.severity == "error" and "деление на ноль" in crash.message


def test_disabled_checks_are_skipped_without_findings(garage61: Path) -> None:
    config = garage61 / "reqgraph.yaml"
    text = config.read_text(encoding="utf-8").replace("disabled: []", "disabled: [TRC-900]")
    config.write_text(text, encoding="utf-8")
    report = run(garage61)
    assert {c.id: c.status for c in report.checks}["TRC-900"] == "skipped"
    assert not [f for f in report.findings if f.check_id == "TRC-900"]


def test_findings_are_sorted_and_the_report_is_stable(garage61: Path) -> None:
    first, second = run(garage61), run(garage61)
    assert first.to_json() == second.to_json()
    order = [c.id for c in first.checks]
    assert order == ["SCH-900", "SND-900", "ISO-900", "TRC-900", "TPL-900"]  # groups as in 05_ci
    keys = [(order.index(f.check_id), f.node_ids, f.message) for f in first.findings]
    assert keys == sorted(keys)


def test_finding_with_a_foreign_check_id_is_rejected(garage61: Path) -> None:
    from reqgraph.checks.base import BaseCheck, CheckContext, Finding
    from reqgraph.graph import ArtifactGraph

    class Liar(BaseCheck):
        id = "TRC-901"
        title = "чужой id"
        group = "trc"
        owner = "analyst"

        def run(self, graph: ArtifactGraph, ctx: CheckContext) -> list[Finding]:
            return [Finding(check_id="TRC-002", severity="error", message="x", owner="analyst")]

    project = FileStore(garage61).load()
    report = asyncio.run(run_checks(project, [Liar()], offline=True))
    (finding,) = report.findings
    assert finding.check_id == "TRC-901" and "TRC-002" in finding.message
