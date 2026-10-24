"""Reviewer (03_agents, 05_ci, T-205): the CI report -> repair tasks for owners; repeat detector.

Code decides who fixes what: errors are grouped by owner and node (at most MAX_TASKS groups), and
TPL-001 on a section listed from the graph goes to the owner of those nodes — an empty «quality
requirements» section is the Analyst's job, not the Standards'. The LLM only words the instruction
of each group (ReviewerDraft); a group it skips gets the template text. With reviewer="template"
there is no LLM at all: the «without Reviewer» ablation (09_eval).

Repeat detector: when the error fingerprints of the report are the same as in the two reports
before, repair has made no progress twice in a row — the run stops with needs_human (reason
«stuck»). Errors left after the last round (max_iter) stop it the same way (reason «limit»).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict, Field

from reqgraph.agents.common import start
from reqgraph.agents.prompts import load_prompt
from reqgraph.agents.runtime import RunContext
from reqgraph.agents.state import RepairTask, RunState
from reqgraph.checks.base import Finding, Owner
from reqgraph.checks.report import CIReport
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.llm.router import BudgetExceeded
from reqgraph.standards import load_structure

MAX_TASKS = 10  # repair tasks per round (03_agents)
STUCK_ROUNDS = 2  # the same errors after this many repair rounds in a row -> needs_human
_ANALYST_KINDS = frozenset({"BR", "UR", "FR", "NFR", "CON", "ACT"})


@dataclass
class Group:
    """Errors one owner fixes on the same nodes: one repair task."""

    owner: Owner
    node_ids: list[str]
    findings: list[Finding] = field(default_factory=list)

    def template(self) -> str:
        return "; ".join(explain(f) for f in self.findings)

    def task(self, instruction: str | None = None) -> RepairTask:
        return RepairTask(
            owner=self.owner,
            node_ids=self.node_ids,
            instruction=instruction or self.template(),
            check_ids=sorted({f.check_id for f in self.findings}),
        )


def fingerprints(report: CIReport | None) -> list[str]:
    """Error fingerprints of a report (check + nodes, not the text), sorted."""
    if report is None:
        return []
    return sorted({f.fingerprint for f in report.findings if f.severity == "error"})


def stuck(history: Sequence[Sequence[str]]) -> bool:
    """The last STUCK_ROUNDS + 1 reports have the same, non-empty set of errors."""
    if len(history) <= STUCK_ROUNDS:
        return False
    last = history[-(STUCK_ROUNDS + 1) :]
    return bool(last[-1]) and all(set(h) == set(last[-1]) for h in last)


def owner_of(finding: Finding) -> Owner:
    """TPL-001 on a section built from graph nodes belongs to the owner of those nodes."""
    if finding.check_id != "TPL-001" or not finding.node_ids:
        return finding.owner
    sections = {s.id: s for s in load_structure("iso29148_srs").sections}
    section = sections.get(finding.node_ids[0])
    if section is None:
        return finding.owner
    if section.fill in ("acceptance", "assumptions"):
        return "analyst"
    kinds = set(section.node_kinds)
    if kinds and kinds <= _ANALYST_KINDS:
        return "analyst"
    if kinds:
        return "modeler"
    return finding.owner


_KIND_NAMES = {
    "BR": "бизнес-требований (BR)",
    "UR": "пользовательских требований (UR)",
    "FR": "функциональных требований (FR)",
    "NFR": "нефункциональных требований (NFR)",
    "CON": "ограничений (CON)",
    "ACT": "ролей (actors)",
    "ENT": "сущностей модели данных",
    "PRC": "процессов",
}


def explain(finding: Finding) -> str:
    """The message and hint; an empty section listed from the graph says which nodes are missing."""
    text = finding.message + (f" — {finding.hint}" if finding.hint else "")
    if finding.check_id != "TPL-001" or not finding.node_ids:
        return text
    section = {s.id: s for s in load_structure("iso29148_srs").sections}.get(finding.node_ids[0])
    if section is None or not (section.node_kinds or section.fill == "acceptance"):
        return text
    missing = (
        "критериев приёмки у ФТ"
        if section.fill == "acceptance"
        else ", ".join(_KIND_NAMES.get(k, k) for k in section.node_kinds)
    )
    return (
        f"раздел «{section.title}» пуст: в графе нет {missing}. Добавьте их по репликам заказчика; "
        "если заказчик о них не говорил, но без них системы нет — запишите как допущение "
        "(assumption: true), чтобы уточнить у заказчика"
    )


def group_findings(report: CIReport) -> list[Group]:
    groups: dict[tuple[str, tuple[str, ...]], Group] = {}
    for finding in report.findings:
        if finding.severity != "error":
            continue
        owner = owner_of(finding)
        key = (owner, tuple(finding.node_ids[:1]))  # the first node names the place to fix
        group = groups.setdefault(key, Group(owner, list(finding.node_ids)))
        group.findings.append(finding)
        group.node_ids = list(dict.fromkeys([*group.node_ids, *finding.node_ids]))
    return list(groups.values())[:MAX_TASKS]


# --- the LLM part -------------------------------------------------------------------------------


class _Draft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class DraftTask(_Draft):
    group: int = Field(description="номер группы из <groups>")
    instruction: str = Field(description="что и как исправить, 1–3 предложения")


class ReviewerDraft(_Draft):
    tasks: list[DraftTask] = Field(default_factory=list)


def _node_line(graph: ArtifactGraph, node_id: str) -> str:
    node = graph.get(node_id.split(".")[0])
    if node is None:
        return node_id
    title = getattr(node, "title", None) or getattr(node, "name", "")
    text = getattr(node, "statement", None) or ""
    return f"{node_id} {title}" + (f": {text}" if text else "")


def render(groups: list[Group], graph: ArtifactGraph) -> str:
    return load_prompt("reviewer/review").render(
        groups=[
            {
                "number": i,
                "owner": g.owner,
                "nodes": [_node_line(graph, n) for n in g.node_ids],
                "findings": [f"{f.check_id}: {explain(f)}" for f in g.findings],
            }
            for i, g in enumerate(groups, 1)
        ]
    )


def tasks_from(draft: ReviewerDraft, groups: list[Group]) -> list[RepairTask]:
    """Instructions of the LLM by group number; a skipped or unknown group keeps the template."""
    words = {t.group: t.instruction.strip() for t in draft.tasks if t.instruction.strip()}
    return [g.task(words.get(i)) for i, g in enumerate(groups, 1)]


async def reviewer(state: RunState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = start(runtime, "reviewer")
    history = state["history"]
    reason = "stuck" if stuck(history) else "limit" if state["iteration"] >= ctx.max_iter else None
    if reason is not None:  # no progress, or no rounds left: a person decides what is next
        errors = history[-1] if history else []
        ctx.events.emit("needs_human", iteration=state["iteration"], reason=reason, errors=errors)
        return {"stop": "needs_human", "tasks": []}
    report = state["ci"]
    groups = group_findings(report) if report is not None else []
    update: dict[str, Any] = {"iteration": state["iteration"] + 1}
    tasks = [g.task() for g in groups]
    if ctx.reviewer == "llm" and groups:
        template = load_prompt("reviewer/review")
        try:
            draft, update["budget"] = await ctx.ask(
                "reviewer",
                render(groups, state["graph"]),
                ReviewerDraft,
                state["budget"],
                template=template,
            )
            tasks = tasks_from(draft, groups)
        except BudgetExceeded:
            ctx.events.emit("stop", reason="budget", node="reviewer")
            return {"stop": "budget", "tasks": []}
    ctx.events.emit("repair", iteration=update["iteration"], tasks=[t.model_dump() for t in tasks])
    return update | {"tasks": tasks}
