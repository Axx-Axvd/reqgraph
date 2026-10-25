"""Manual check of the judge (09_eval, R4): a person labels a random 20% of the judged pairs.

The sample is drawn with a fixed seed, so it can be repeated and extended; the answers go into
<pairs>.human.csv next to the pairs file, and the work can be stopped and continued — labelled pairs
are not asked again. agreement.py then compares the judge with the person.
"""

import csv
import random
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from reqgraph_evals.metrics.agreement import agreement, cohen_kappa

SHARE = 0.2
HUMAN_FIELDS = ["run", "hidden_id", "found_id", "judge", "human"]
Ask = Callable[[str], str]


def read_pairs(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def human_path(pairs: Path) -> Path:
    return pairs.with_name(pairs.stem + ".human.csv")


def sample(pairs: Sequence[dict[str, Any]], share: float = SHARE, seed: int = 42) -> list[int]:
    """Indexes of the pairs to label: a seeded random share, at least one pair."""
    count = max(1, round(len(pairs) * share)) if pairs else 0
    return sorted(random.Random(seed).sample(range(len(pairs)), count))


def _key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (row["run"], row["hidden_id"], row["found_id"])


def read_human(path: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        return {_key(r): r for r in csv.DictReader(fh)}


def label(
    pairs_path: Path,
    ask: Ask,
    *,
    share: float = SHARE,
    seed: int = 42,
    echo: Callable[[str], None] = print,
) -> int:
    """Ask about every sampled pair not labelled yet; «q» stops and keeps what is done."""
    pairs = read_pairs(pairs_path)
    out = human_path(pairs_path)
    done = read_human(out)
    todo = [pairs[i] for i in sample(pairs, share, seed) if _key(pairs[i]) not in done]
    echo(f"к разметке {len(todo)} пар (уже размечено {len(done)})")
    for number, pair in enumerate(todo, 1):
        echo(f"\n[{number}/{len(todo)}] {pair['run']}")
        echo(f"  эталон  {pair['hidden_id']}: {pair['hidden']}")
        echo(f"  система {pair['found_id']}: {pair['found']}")
        others = [
            p
            for p in pairs
            if (p["run"], p["hidden_id"]) == (pair["run"], pair["hidden_id"]) and p is not pair
        ]
        for other in others:  # the reference may be split over several requirements
            echo(f"  рядом   {other['found_id']}: {other['found']}")
        question = (
            "  выражает эталон — сам или вместе с соседними? y — да, n — нет, q — закончить: "
            if others
            else "  то же требование? y — да, n — нет, q — закончить: "
        )
        while (answer := ask(question).strip()) not in ("y", "n", "q"):
            echo("  ответьте y, n или q")
        if answer == "q":
            break
        done[_key(pair)] = {
            "run": pair["run"],
            "hidden_id": pair["hidden_id"],
            "found_id": pair["found_id"],
            "judge": pair["judge"],
            "human": str(answer == "y"),
        }
        _write(out, list(done.values()))
    return len(done)


def _write(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=HUMAN_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def compare(pairs_path: Path) -> dict[str, float]:
    """Kappa and agreement of the judge with the person on the labelled pairs."""
    rows = list(read_human(human_path(pairs_path)).values())
    if not rows:
        raise ValueError(f"нет разметки: сначала reqgraph-evals label {pairs_path}")
    judge = [r["judge"] == "True" for r in rows]
    human = [r["human"] == "True" for r in rows]
    return {
        "pairs": len(rows),
        "kappa": round(cohen_kappa(judge, human), 3),
        "agreement": round(agreement(judge, human), 3),
        "judge_yes": sum(judge),
        "human_yes": sum(human),
    }
