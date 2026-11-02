"""Typical / unique labels of the hidden requirements (T-308), asked one by one in the terminal.

`label_groups` shows each requirement without a label and writes the answer into hidden.yaml at
once (only the line of that requirement changes), so the work can be stopped and continued. It is
for the author, who labels the test references before the seal: the texts are printed to the
person at the keyboard, not to a log. `check_groups` asks about a seeded sample of already labelled
requirements without showing their labels and compares the answers: agreement and Cohen's kappa
of two labellers. The rule is in evals/scenarios/README.md.
"""

import csv
import random
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from reqgraph_evals.metrics.agreement import agreement, cohen_kappa
from reqgraph_evals.scenario import SCENARIOS, load_scenario

Ask = Callable[[str], str]
Echo = Callable[[str], None]
ANSWERS = {"t": "typical", "u": "unique"}
CHECK_FIELDS = ["scenario", "id", "first", "second"]
CHEAT_SHEET = (
    "Правило (evals/scenarios/README.md, кратко):\n"
    "  t — типовое: есть в большинстве систем такого класса и пишется по шаблону — роли и права,\n"
    "      состав данных, уведомления, вход, оплата и чеки, отчёты, интеграции, качество,\n"
    "      закон о данных, сроки и бюджет; шаблон с числом заказчика («SMS за 24 часа») — тоже t;\n"
    "  u — уникальное: правило, расчёт или ограничение именно этого дела, с условием и\n"
    "      последствием («опоздал больше 15 минут — приём переносится»); цель с показателем\n"
    "      этого дела; сомневаетесь — u."
)
QUESTION = "  t — типовое, u — уникальное, ? — правило, q — закончить: "
_LINE = re.compile(r"^(\s*- \{id: (H-\d{3}),.*)\}\s*$")


def set_group(path: Path, requirement_id: str, group: str) -> None:
    """Write group: <group> into the one-line entry of a requirement in hidden.yaml."""
    lines = path.read_text(encoding="utf-8").split("\n")
    for number, line in enumerate(lines):
        match = _LINE.match(line)
        if match and match.group(2) == requirement_id:
            body = re.sub(r", group: \w+$", "", match.group(1))
            lines[number] = f"{body}, group: {group}}}"
            path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
            return
    raise ValueError(f"{path}: нет строки {requirement_id} в формате «- {{id: …}}»")


def _answer(ask: Ask, echo: Echo) -> str:
    while (answer := ask(QUESTION).strip().lower()) not in (*ANSWERS, "q"):
        if answer == "?":
            echo(CHEAT_SHEET)
        else:
            echo("  ответьте t, u, ? или q")
    return answer


def _show(echo: Echo, head: str, item: Any) -> None:
    echo(f"\n{head} {item.id} · {item.kind} · область {item.area}")
    echo(f"  {item.statement}")


def label_groups(
    scenario_ids: Sequence[str], ask: Ask, *, root: Path = SCENARIOS, echo: Echo = print
) -> dict[str, int]:
    """Ask about every requirement without a group; «q» stops, what is answered stays."""
    todo = []
    for scenario_id in scenario_ids:
        scenario = load_scenario(scenario_id, root, final=True)
        todo += [(scenario_id, r) for r in scenario.hidden.requirements if r.group is None]
    echo(CHEAT_SHEET)
    echo(f"\nк разметке {len(todo)} требований в {len(scenario_ids)} сценариях")
    done: dict[str, int] = {"typical": 0, "unique": 0}
    for number, (scenario_id, item) in enumerate(todo, 1):
        _show(echo, f"[{number}/{len(todo)}] {scenario_id}", item)
        answer = _answer(ask, echo)
        if answer == "q":
            break
        set_group(root / scenario_id / "hidden.yaml", item.id, ANSWERS[answer])
        done[ANSWERS[answer]] += 1
    return done


def check_path(out: Path) -> Path:
    return out / "labels" / "groups-check.csv"


def check_groups(
    scenario_ids: Sequence[str],
    ask: Ask,
    *,
    out: Path,
    share: float = 0.2,
    seed: int = 42,
    root: Path = SCENARIOS,
    echo: Echo = print,
) -> dict[str, float]:
    """A second labeller on a seeded sample of labelled requirements; the first labels are hidden.
    Answers go to <out>/labels/groups-check.csv at once; the result compares the two."""
    items = []
    for scenario_id in scenario_ids:
        scenario = load_scenario(scenario_id, root, final=True)
        items += [(scenario_id, r) for r in scenario.hidden.requirements if r.group is not None]
    count = max(1, round(len(items) * share)) if items else 0
    picked = [items[i] for i in sorted(random.Random(seed).sample(range(len(items)), count))]
    path = check_path(out)
    done = _read_check(path)
    todo = [(s, r) for s, r in picked if (s, r.id) not in done]
    echo(CHEAT_SHEET)
    echo(f"\nк проверке {len(todo)} требований (уже проверено {len(done)})")
    for number, (scenario_id, item) in enumerate(todo, 1):
        _show(echo, f"[{number}/{len(todo)}] {scenario_id}", item)
        answer = _answer(ask, echo)
        if answer == "q":
            break
        done[(scenario_id, item.id)] = {
            "scenario": scenario_id,
            "id": item.id,
            "first": str(item.group),
            "second": ANSWERS[answer],
        }
        _write_check(path, list(done.values()))
    rows = list(done.values())
    first = [r["first"] for r in rows]
    second = [r["second"] for r in rows]
    return {
        "checked": len(rows),
        "agreement": round(agreement(first, second), 3) if rows else 0.0,
        "kappa": round(cohen_kappa(first, second), 3) if rows else 0.0,
    }


def _read_check(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        return {(r["scenario"], r["id"]): r for r in csv.DictReader(fh)}


def _write_check(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CHECK_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
