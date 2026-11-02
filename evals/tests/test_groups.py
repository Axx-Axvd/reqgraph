"""Typical / unique labels asked in the terminal (T-308): written at once, can be continued."""

import re
import shutil
from collections.abc import Iterator
from pathlib import Path

from reqgraph_evals import groups
from reqgraph_evals.scenario import SCENARIOS, load_scenario


def answers(*items: str) -> groups.Ask:
    queue: Iterator[str] = iter(items)
    return lambda _question: next(queue)


def unlabelled_copy(tmp_path: Path) -> Path:
    root = tmp_path / "scenarios"
    shutil.copytree(SCENARIOS / "dev-01", root / "dev-01")
    path = root / "dev-01" / "hidden.yaml"
    path.write_text(re.sub(r", group: \w+\}", "}", path.read_text(encoding="utf-8")), "utf-8")
    assert all(r.group is None for r in load_scenario("dev-01", root).hidden.requirements)
    return root


def test_answers_are_written_at_once_and_the_work_continues(tmp_path: Path) -> None:
    root = unlabelled_copy(tmp_path)
    shown: list[str] = []
    done = groups.label_groups(
        ["dev-01"], answers("x", "?", "t", "u", "q"), root=root, echo=shown.append
    )
    assert done == {"typical": 1, "unique": 1}
    assert any("ответьте t, u, ? или q" in s for s in shown)  # a wrong key asks again
    assert sum("Правило" in s for s in shown) == 2  # at the start and on «?»
    items = load_scenario("dev-01", root).hidden.requirements
    assert [r.group for r in items[:3]] == ["typical", "unique", None]
    rest = len(items) - 2
    done = groups.label_groups(["dev-01"], answers(*["t"] * rest), root=root, echo=shown.append)
    assert done == {"typical": rest, "unique": 0}
    assert all(r.group for r in load_scenario("dev-01", root).hidden.requirements)


def test_a_label_changes_only_its_line(tmp_path: Path) -> None:
    root = unlabelled_copy(tmp_path)
    path = root / "dev-01" / "hidden.yaml"
    before = path.read_text(encoding="utf-8").split("\n")
    groups.set_group(path, "H-002", "unique")
    groups.set_group(path, "H-002", "typical")  # a second answer replaces the first
    after = path.read_text(encoding="utf-8").split("\n")
    changed = [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b]
    assert len(changed) == 1 and after[changed[0]].endswith(", group: typical}")


def test_a_second_labeller_is_compared_on_a_seeded_sample(tmp_path: Path) -> None:
    items = {r.id: r.group for r in load_scenario("dev-01").hidden.requirements}
    shown: list[str] = []
    seen: list[str] = []

    def same(_question: str) -> str:
        item_id = re.findall(r"(H-\d{3}) ·", shown[-2])[0]
        seen.append(item_id)
        return "t" if items[item_id] == "typical" else "u"

    result = groups.check_groups(["dev-01"], same, out=tmp_path, echo=shown.append)
    assert result["checked"] == 5 and result["agreement"] == 1.0  # 20% of 25
    assert not any("typical" in s or "unique" in s for s in shown)  # the first labels are hidden
    again = groups.check_groups(["dev-01"], answers(), out=tmp_path, echo=shown.append)
    assert again["checked"] == 5  # all done: nothing is asked, the file is read back
    assert groups.check_path(tmp_path).is_file() and len(set(seen)) == 5


def test_the_command_labels_and_says_what_is_left(tmp_path: Path) -> None:
    from reqgraph_evals.cli import app
    from typer.testing import CliRunner

    root = unlabelled_copy(tmp_path)
    args = ["groups", "dev-01", "--root", str(root)]
    result = CliRunner().invoke(app, args, input="t\nu\nq\n")
    assert result.exit_code == 0, result.output
    assert "размечено: типовых 1, уникальных 1" in result.output
    assert "осталось без метки: 23" in result.output
