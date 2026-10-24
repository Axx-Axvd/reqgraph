"""reqgraph init / run (T-206): a project from a brief to a report in one command."""

import json
from pathlib import Path

import pytest
from reqgraph.agents.run import RunFailed, init_project, run_project
from reqgraph.cli import app
from reqgraph.llm.config import load_roles
from typer.testing import CliRunner

from .conftest import BRIEF, DRAFT, GARAGE61, stub_models
from .test_modeler import MODEL

pytestmark = pytest.mark.anyio


def project(tmp_path: Path) -> Path:
    return init_project(tmp_path / "ulybka", name="Улыбка", brief=BRIEF)


def test_init_writes_config_and_brief(tmp_path: Path) -> None:
    root = project(tmp_path)
    assert (root / "brief.md").read_text(encoding="utf-8") == BRIEF
    config = (root / "reqgraph.yaml").read_text(encoding="utf-8")
    assert "id: ulybka" in config and "name: Улыбка" in config  # profile free is the default
    with pytest.raises(RunFailed, match="уже есть"):
        init_project(root, name="x", brief=BRIEF)


def test_init_needs_a_latin_id(tmp_path: Path) -> None:
    with pytest.raises(RunFailed, match="--id"):
        init_project(tmp_path / "Улыбка", name="Улыбка", brief=BRIEF)
    assert init_project(
        tmp_path / "Улыбка", name="Улыбка", brief=BRIEF, project_id="smile"
    ).is_dir()


async def test_run_writes_the_project_reports_and_a_summary(tmp_path: Path) -> None:
    root = project(tmp_path)
    lines: list[str] = []
    models = stub_models(analyst=DRAFT, modeler=MODEL)
    summary, report = await run_project(root, models=models, offline=True, on_line=lines.append)
    assert (root / "requirements" / "functional.yaml").is_file()
    assert (root / "models" / "data" / "erd.dbml").is_file()
    assert list((root / "models" / "processes").glob("PRC-01*.process.json"))
    saved = json.loads((root / "reports" / "run-summary.json").read_text(encoding="utf-8"))
    assert saved == summary.to_dict()
    assert summary.requirements == 5 and summary.processes == 1 and summary.entities == 2
    assert summary.sections == 15 and summary.errors == report.summary.errors
    assert summary.models["analyst"] == "test/test" and summary.cost_usd == 0.0
    assert summary.temperature == load_roles().defaults.temperature
    assert summary.seeds["analyst"] == load_roles().defaults.seed
    assert (root / "reports" / "ci-report.md").is_file()
    events = (root / "reports" / "run-events.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(events[0])["type"] == "node_start"
    assert any("Analyst" in line for line in lines) and any("Проверки" in line for line in lines)


async def test_no_write_leaves_the_folder_as_it_was(tmp_path: Path) -> None:
    root = project(tmp_path)
    before = sorted(p.name for p in root.rglob("*"))
    await run_project(
        root, models=stub_models(analyst=DRAFT, modeler=MODEL), offline=True, write=False
    )
    assert sorted(p.name for p in root.rglob("*")) == before


async def test_run_refuses_the_reference_project_and_a_missing_brief(tmp_path: Path) -> None:
    with pytest.raises(RunFailed, match="эталонный"):
        await run_project(GARAGE61, models=stub_models(), write=False)
    root = project(tmp_path)
    (root / "brief.md").unlink()
    with pytest.raises(RunFailed, match=r"brief\.md"):
        await run_project(root, models=stub_models(), write=False)


async def test_options_override_reqgraph_yaml(tmp_path: Path) -> None:
    root = project(tmp_path)
    summary, _ = await run_project(
        root,
        models=stub_models(analyst=DRAFT, modeler=MODEL),
        offline=True,
        max_iter=0,
        budget_usd=0.25,
        reviewer="template",
        brief="# Бриф\n\nДругой текст брифа.\n",
    )
    assert summary.iterations == 0 and summary.budget_usd == 0.25 and summary.reviewer == "template"


def test_cli_exit_code_2_when_the_run_cannot_start(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["run", str(GARAGE61), "--no-write", "--offline"])
    assert result.exit_code == 2 and "эталонный" in result.output
    result = CliRunner().invoke(app, ["run", str(tmp_path / "nowhere")])
    assert result.exit_code == 2


def test_cli_init(tmp_path: Path) -> None:
    brief = tmp_path / "brief.md"
    brief.write_text(BRIEF, encoding="utf-8")
    result = CliRunner().invoke(
        app, ["init", str(tmp_path / "smile"), "--name", "Улыбка", "--brief", str(brief)]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "smile" / "reqgraph.yaml").is_file()
