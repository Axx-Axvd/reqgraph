"""Run checks on a project and build the CIReport (the CLI and, in S2, the ci_gate of agents)."""

import inspect
from collections.abc import Sequence

from reqgraph.checks.base import GROUP_ORDER, BaseCheck, CheckContext, CheckSkipped, Finding
from reqgraph.checks.registry import all_checks
from reqgraph.checks.report import CheckResult, CIReport, Status, Summary
from reqgraph.graph.store.project import Project

_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


async def _run_one(check: BaseCheck, ctx: CheckContext) -> tuple[list[Finding], bool]:
    """Findings of one check and whether it was skipped. A crash becomes an error finding."""
    try:
        result = check.run(ctx.project.graph, ctx)
        findings = await result if inspect.isawaitable(result) else result
    except CheckSkipped as skip:
        return [check.finding("info", [], f"пропущено: {skip.reason}")], True
    except Exception as exc:  # a bug in a check must not cost the whole report
        message = f"проверка упала: {type(exc).__name__}: {exc}"
        return [check.finding("error", [], message, hint="ошибка в коде проверки")], False
    fixed = []
    for found in findings:
        if found.check_id != check.id:  # a check speaks only for itself
            text = f"находка с чужим id {found.check_id}: {found.message}"
            found = found.model_copy(update={"check_id": check.id, "message": text})
        fixed.append(found)
    return fixed, False


def _order(check: BaseCheck) -> tuple[int, str]:
    """Groups in the order of the catalog (05_ci), checks by id inside a group."""
    return GROUP_ORDER[check.group], check.id


def _status(findings: list[Finding], skipped: bool) -> Status:
    if skipped:
        return "skipped"
    if any(f.severity == "error" for f in findings):
        return "failed"
    if any(f.severity == "warning" for f in findings):
        return "warning"
    return "passed"


async def run_checks(
    project: Project, checks: Sequence[BaseCheck] | None = None, *, offline: bool = False
) -> CIReport:
    """All registered checks by default; checks disabled in reqgraph.yaml are skipped."""
    ctx = CheckContext(project, offline=offline)
    disabled = set(project.config.checks.disabled)
    results: list[CheckResult] = []
    findings: list[Finding] = []
    ordered = sorted(all_checks() if checks is None else checks, key=_order)
    position = {check.id: index for index, check in enumerate(ordered)}
    for check in ordered:
        found: list[Finding]
        if check.id in disabled:
            found, skipped = [], True
        else:
            found, skipped = await _run_one(check, ctx)
        findings += found
        results.append(
            CheckResult(
                id=check.id,
                title=check.title,
                group=check.group,
                status=_status(found, skipped),
                errors=sum(f.severity == "error" for f in found),
                warnings=sum(f.severity == "warning" for f in found),
                infos=sum(f.severity == "info" for f in found),
            )
        )
    findings.sort(
        key=lambda f: (position[f.check_id], f.node_ids, _SEVERITY_ORDER[f.severity], f.message)
    )
    statuses = [r.status for r in results]
    summary = Summary(
        errors=sum(f.severity == "error" for f in findings),
        warnings=sum(f.severity == "warning" for f in findings),
        infos=sum(f.severity == "info" for f in findings),
        passed=statuses.count("passed"),
        warned=statuses.count("warning"),
        failed=statuses.count("failed"),
        skipped=statuses.count("skipped"),
    )
    return CIReport(
        project=project.config.project.id, checks=results, findings=findings, summary=summary
    )
