"""`reqgraph run` end to end on the dev-01 brief (free profile), replayed from a cassette (T-206).

Every agent is real: Analyst -> Modeler -> Standards -> checks -> Reviewer and repair. Re-record
after a deliberate change of a prompt or of an agent schema (needs network and keys; in a cloud
session the proxy injects them):
    uv run pytest packages/core/tests/agents/test_run_live.py \\
        --record-mode=rewrite --force-enable-socket
"""

import json
from pathlib import Path

import pytest
from reqgraph.agents.run import init_project
from reqgraph.cli import app
from typer.testing import CliRunner

TESTS = Path(__file__).resolve().parents[1]
DEV_01 = TESTS.parents[2] / "evals" / "scenarios" / "dev-01" / "brief.md"
CASSETTE = TESTS / "cassettes" / "test_run_from_a_dev_brief_to_a_report.yaml"
SECRETS = ("authorization:", "x-goog-api-key:", "api-key:", "cookie:", "bearer ", "key=")


@pytest.mark.vcr
def test_run_from_a_dev_brief_to_a_report(tmp_path: Path) -> None:
    root = init_project(
        tmp_path / "dev-01", name="dev-01", brief=DEV_01.read_text(encoding="utf-8")
    )
    result = CliRunner().invoke(app, ["run", str(root), "--offline"])
    assert result.exit_code in (0, 1), result.output  # 1: errors left, explained in the report
    assert "→ Analyst: требования" in result.output and "Отчёт:" in result.output
    summary = json.loads((root / "reports" / "run-summary.json").read_text(encoding="utf-8"))
    assert summary["requirements"] >= 5 and summary["processes"] >= 1
    assert summary["entities"] >= 1 and summary["sections"] == 15
    assert summary["llm_calls"] >= 3 and summary["cost_usd"] == 0.0  # free profile
    assert {"analyst", "modeler", "standards"} <= set(summary["models"])
    assert (root / "reports" / "ci-report.md").is_file()
    assert (root / "models" / "data" / "erd.dbml").is_file()
    report = json.loads((root / "reports" / "ci-report.json").read_text(encoding="utf-8"))
    schema_errors = [
        f
        for f in report["findings"]
        if f["check_id"].startswith("SCH") and f["severity"] == "error"
    ]
    assert schema_errors == []


def test_the_cassette_keeps_no_keys() -> None:
    text = CASSETTE.read_text(encoding="utf-8").lower()
    assert [s for s in SECRETS if s in text] == []
