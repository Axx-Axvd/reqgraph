"""Reviewer (T-205): errors -> repair tasks by owner and node, TPL-001 to the node owner, LLM
words the instructions, template without LLM, repeat detector."""

import json
from collections.abc import Callable

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from reqgraph.agents.graph import build_graph
from reqgraph.agents.reviewer import (
    MAX_TASKS,
    ReviewerDraft,
    fingerprints,
    group_findings,
    owner_of,
    stuck,
    tasks_from,
)
from reqgraph.agents.runtime import RunContext
from reqgraph.agents.state import initial_state
from reqgraph.checks.base import Finding, Owner, Severity
from reqgraph.checks.report import CIReport, Summary

from .conftest import events_of, stub_models
from .test_graph import with_vague_fr001

pytestmark = pytest.mark.anyio


def finding(
    check: str, nodes: list[str], owner: Owner = "analyst", severity: Severity = "error"
) -> Finding:
    return Finding(
        check_id=check,
        severity=severity,
        node_ids=nodes,
        message=f"{check} на {nodes}",
        owner=owner,
    )


def report(*findings: Finding) -> CIReport:
    summary = Summary(
        errors=sum(f.severity == "error" for f in findings),
        warnings=0,
        infos=0,
        passed=0,
        warned=0,
        failed=0,
        skipped=0,
    )
    return CIReport(project="t", checks=[], findings=list(findings), summary=summary)


def test_errors_on_one_node_make_one_task_warnings_none() -> None:
    groups = group_findings(
        report(
            finding("ISO-001", ["FR-001"]),
            finding("ISO-003", ["FR-001"]),
            finding("ISO-002", ["FR-002"], severity="warning"),
            finding("SND-001", ["PRC-01.T03"], owner="modeler"),
        )
    )
    assert [(g.owner, g.node_ids, [f.check_id for f in g.findings]) for g in groups] == [
        ("analyst", ["FR-001"], ["ISO-001", "ISO-003"]),
        ("modeler", ["PRC-01.T03"], ["SND-001"]),
    ]
    assert groups[0].task().check_ids == ["ISO-001", "ISO-003"]


def test_at_most_ten_tasks_per_round() -> None:
    many = [finding("ISO-001", [f"FR-{i:03d}"]) for i in range(1, 15)]
    assert len(group_findings(report(*many))) == MAX_TASKS


@pytest.mark.parametrize(
    ("section", "owner"),
    [
        ("SEC-SRS-3.3", "analyst"),  # «Требования к качеству» is empty: no NFR in the graph
        ("SEC-SRS-3.5", "modeler"),  # no entities
        ("SEC-SRS-4", "analyst"),  # no acceptance criteria
        ("SEC-SRS-1.4", "standards"),  # the glossary is the Standards' own text
    ],
)
def test_empty_section_goes_to_the_owner_of_its_nodes(section: str, owner: str) -> None:
    assert owner_of(finding("TPL-001", [section], owner="standards")) == owner


def test_llm_words_the_tasks_and_skipped_groups_keep_the_template() -> None:
    groups = group_findings(
        report(finding("ISO-001", ["FR-001"]), finding("TRC-002", ["FR-002"], owner="modeler"))
    )
    draft = ReviewerDraft.model_validate(
        {
            "tasks": [
                {"group": 1, "instruction": "Замените «быстро» на «за 2 секунды»."},
                {"group": 9, "instruction": "x"},
            ]
        }
    )
    first, second = tasks_from(draft, groups)
    assert first.instruction == "Замените «быстро» на «за 2 секунды»."
    assert second.instruction == "TRC-002 на ['FR-002']" and second.owner == "modeler"


def test_repeat_detector() -> None:
    a, b = ["fp1"], ["fp2"]
    assert not stuck([a, a])  # one round without progress is not yet stuck
    assert stuck([b, a, a, a])
    assert not stuck([a, b, a])
    assert not stuck([[], [], []])  # no errors is not stuck
    assert fingerprints(
        report(finding("ISO-001", ["FR-001"]), finding("ISO-002", ["FR-001"], severity="warning"))
    ) == [finding("ISO-001", ["FR-001"]).fingerprint]


async def test_reviewer_asks_the_llm_once_per_round_with_the_groups(
    context: Callable[..., RunContext],
) -> None:
    prompts: list[str] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompts.append(str(messages[0]))
        task = {"group": 1, "instruction": "Уберите «быстро» из FR-001."}
        return ModelResponse(parts=[TextPart(json.dumps({"tasks": [task]}, ensure_ascii=False))])

    ctx = context(models=stub_models() | {"reviewer": FunctionModel(fn)})
    await build_graph().ainvoke(
        initial_state(with_vague_fr001(ctx.project.graph), "brief"), context=ctx
    )
    assert len(prompts) == 2  # two rounds, then needs_human
    assert "## Группа 1 — владелец analyst" in prompts[0] and "FR-001 Каталог услуг" in prompts[0]
    assert events_of(ctx, "repair")[0]["tasks"][0]["instruction"] == "Уберите «быстро» из FR-001."


async def test_template_reviewer_makes_no_llm_call(context: Callable[..., RunContext]) -> None:
    ctx = context(reviewer="template")
    await build_graph().ainvoke(
        initial_state(with_vague_fr001(ctx.project.graph), "brief"), context=ctx
    )
    assert [e for e in events_of(ctx, "llm_call") if e["role"] == "reviewer"] == []
    assert events_of(ctx, "repair")[0]["tasks"][0]["instruction"].startswith("FR-001: размытые")


def test_empty_section_task_says_which_nodes_are_missing() -> None:
    (group,) = group_findings(report(finding("TPL-001", ["SEC-SRS-3.3"], owner="standards")))
    assert group.owner == "analyst"
    assert "нет нефункциональных требований (NFR)" in group.template()
    assert "assumption: true" in group.template()
