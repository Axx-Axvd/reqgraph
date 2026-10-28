"""Manual check of the judge (09_eval, R4): a person labels a random 20% of the judged references.

The unit is a reference requirement with all its candidates — what the judge decides and what
recall counts — not a single pair: asked about one candidate «alone or with its neighbours», a
person answers for the reference anyway (27.10, κ 0.22 on pairs). The answer has the judge's three
levels: fully, partly (the topic without its numbers or a key condition), not at all. The sample is
drawn with a fixed seed, so it can be repeated; the answers go into <pairs>.human.csv next to the
pairs file, and the work can be stopped and continued. The judge's verdict is never shown.
"""

import csv
import random
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from reqgraph_evals.metrics.agreement import agreement, cohen_kappa

SHARE = 0.2
HUMAN_FIELDS = ["run", "hidden_id", "judge", "human"]
LEVELS = {"f": "full", "p": "partial", "n": "none"}
Ask = Callable[[str], str]


def read_pairs(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def human_path(pairs: Path) -> Path:
    return pairs.with_name(pairs.stem + ".human.csv")


def _key(row: dict[str, Any]) -> tuple[str, str]:
    return (row["run"], row["hidden_id"])


def references(pairs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """The judged references in file order, each with its candidates and the judge's level."""
    refs: dict[tuple[str, str], dict[str, Any]] = {}
    for pair in pairs:
        ref = refs.setdefault(
            _key(pair),
            {
                "run": pair["run"],
                "hidden_id": pair["hidden_id"],
                "hidden": pair["hidden"],
                "level": pair.get("level") or "none",
                "candidates": [],
            },
        )
        ref["candidates"].append({"id": pair["found_id"], "text": pair["found"]})
    return list(refs.values())


def sample(items: Sequence[Any], share: float = SHARE, seed: int = 42) -> list[int]:
    """Indexes of the items to label: a seeded random share, at least one."""
    count = max(1, round(len(items) * share)) if items else 0
    return sorted(random.Random(seed).sample(range(len(items)), count))


def read_human(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
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
    """Ask about every sampled reference not labelled yet; «q» stops and keeps what is done."""
    refs = references(read_pairs(pairs_path))
    out = human_path(pairs_path)
    done = read_human(out)
    todo = [refs[i] for i in sample(refs, share, seed) if _key(refs[i]) not in done]
    echo(f"к разметке {len(todo)} эталонов (уже размечено {len(done)})")
    for number, ref in enumerate(todo, 1):
        echo(f"\n[{number}/{len(todo)}] {ref['run']}")
        echo(f"  эталон {ref['hidden_id']}: {ref['hidden']}")
        for cand in ref["candidates"]:
            echo(f"  система {cand['id']}: {cand['text']}")
        question = (
            "  есть ли среди них то же требование (одно или несколько вместе)? "
            "f — полностью, p — частично (без чисел или главного условия), n — нет, q — закончить: "
        )
        while (answer := ask(question).strip()) not in (*LEVELS, "q"):
            echo("  ответьте f, p, n или q")
        if answer == "q":
            break
        done[_key(ref)] = {
            "run": ref["run"],
            "hidden_id": ref["hidden_id"],
            "judge": ref["level"],
            "human": LEVELS[answer],
        }
        _write(out, list(done.values()))
    return len(done)


def _write(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=HUMAN_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def compare(pairs_path: Path) -> dict[str, float]:
    """Kappa of the judge and the person on the labelled references: «found fully» or not (what
    recall counts, the T-304 threshold), «found at all», and the three levels as they are."""
    rows = list(read_human(human_path(pairs_path)).values())
    if not rows:
        raise ValueError(f"нет разметки: сначала reqgraph-evals label {pairs_path}")
    judge = [r["judge"] for r in rows]
    human = [r["human"] for r in rows]
    full = ([j == "full" for j in judge], [h == "full" for h in human])
    found = ([j != "none" for j in judge], [h != "none" for h in human])
    return {
        "references": len(rows),
        "kappa": round(cohen_kappa(*full), 3),
        "agreement": round(agreement(*full), 3),
        "kappa_found": round(cohen_kappa(*found), 3),
        "kappa_3": round(cohen_kappa(judge, human), 3),
        "agreement_3": round(agreement(judge, human), 3),
        "judge_full": sum(full[0]),
        "human_full": sum(full[1]),
        "judge_partial": judge.count("partial"),
        "human_partial": human.count("partial"),
    }
