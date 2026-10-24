"""Scenarios of the experiment (T-303): 3 dev + 12 test, the protocol of 09_eval, the seal."""

from pathlib import Path

import pytest
import yaml
from reqgraph_evals import scenario as sc
from reqgraph_evals.cli import app
from typer.testing import CliRunner


def test_fifteen_scenarios_three_dev_and_twelve_test() -> None:
    assert sc.scenario_ids(split="dev") == ["dev-01", "dev-02", "dev-03"]
    assert sc.scenario_ids(split="test") == [f"test-{i:02d}" for i in range(1, 13)]


@pytest.mark.parametrize("scenario_id", sc.scenario_ids())
def test_every_scenario_keeps_the_protocol(scenario_id: str) -> None:
    item = sc.load_scenario(scenario_id, final=True)
    assert sc.problems(item) == []
    assert item.info.split == scenario_id.split("-")[0]


def test_sizes_and_domains_follow_the_plan() -> None:
    items = [sc.load_scenario(i, final=True) for i in sc.scenario_ids()]
    assert sorted(i.info.size for i in items) == sorted("SML" * 5)
    dev = {i.info.domain for i in items if i.info.split == "dev"}
    test = {i.info.domain.split(":")[0] for i in items if i.info.split == "test"}
    assert len(test) == 4  # 4 test domains x 3 sizes
    assert not {d.split(":")[0] for d in dev} & test  # no domain is both tuned on and tested on
    assert not [i for i in items if "автосервис" in i.info.domain]  # garage61 is in the prompts


def test_test_scenarios_are_sealed_and_not_loaded_by_default() -> None:
    with pytest.raises(sc.SealedScenario, match="финальной матрицы"):
        sc.load_scenario("test-01")
    assert sc.seal_broken() == []  # nobody changed a test scenario after the author's check


def test_a_changed_test_file_breaks_the_seal(tmp_path: Path) -> None:
    import shutil

    root = tmp_path / "scenarios"
    shutil.copytree(sc.SCENARIOS, root)
    assert sc.seal_broken(root) == []
    brief = root / "test-01" / "brief.md"
    brief.write_text(brief.read_text(encoding="utf-8") + "\nПодсказка.\n", encoding="utf-8")
    assert [line.split("  ")[-1] for line in sc.seal_broken(root)] == [
        "test-01/brief.md",
        "test-01/brief.md",
    ]  # the sealed hash and the new one


def make(**changes: object) -> sc.Scenario:
    base = sc.load_scenario("dev-01")
    return base.model_copy(update=changes)


def test_problems_name_what_breaks_the_protocol() -> None:
    base = sc.load_scenario("dev-01")
    items = list(base.hidden.requirements)
    short = make(hidden=sc.Hidden(requirements=items[:10]))
    found = sc.problems(short)
    assert any("для размера S нужно 25" in p for p in found)
    assert any("нет требований в областях" in p for p in found)

    gap = [items[0], *items[2:]]  # H-002 is missing
    assert any("подряд" in p for p in sc.problems(make(hidden=sc.Hidden(requirements=gap))))

    leaked = [r.model_copy(update={"in_brief": True}) for r in items]
    assert any(
        "в брифе уже 100%" in p for p in sc.problems(make(hidden=sc.Hidden(requirements=leaked)))
    )

    unmarked = [r.model_copy(update={"in_brief": False}) if r.id == "H-008" else r for r in items]
    copied = make(
        brief=base.brief + "\n" + items[7].statement,
        hidden=sc.Hidden(requirements=unmarked),
    )
    assert "H-008: почти дословно есть в брифе — отметьте in_brief: true" in sc.problems(copied)


def test_formats_are_strict() -> None:
    with pytest.raises(ValueError, match="H-001"):
        sc.HiddenRequirement.model_validate(
            {
                "id": "X-1",
                "kind": "FR",
                "area": "data",
                "statement": "Система хранит данные.",
                "reveal": "данные",
            }
        )
    with pytest.raises(ValueError, match="split"):
        sc.ScenarioInfo.model_validate(
            {"id": "dev-09", "title": "t", "domain": "d", "size": "S", "split": "test"}
        )
    raw = yaml.safe_load((sc.SCENARIOS / "dev-02" / "hidden.yaml").read_text(encoding="utf-8"))
    assert {r["source"] for r in sc.Hidden.model_validate(raw).model_dump()["requirements"]} == {
        "own"
    }


def test_cli_checks_without_printing_test_texts() -> None:
    result = CliRunner().invoke(app, ["scenarios"])
    assert result.exit_code == 0, result.output
    assert "dev-01: S, требований 25" in result.output and "test-12: L" in result.output
    test_brief = (sc.SCENARIOS / "test-01" / "brief.md").read_text(encoding="utf-8")
    assert test_brief.splitlines()[2][:40] not in result.output
