"""The simulator's select step on questions of the T-305 v3 dialogs (T-309).

Each case is a question the interviewer asked, the dialog before it and the hidden requirements a
good choice names (untold ones about that question). The select prompt is rendered as the
simulator renders it, the code rule of Stakeholder.answer is applied, and the result is scored:
found — expected ids picked; wrong — untold ids the question is not about (a hint without a
question); repeat — ids told before. Run: uv run python -m reqgraph_evals.simprobe --help
"""

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any

from reqgraph.llm import router
from reqgraph.llm.config import ModelOptions, Step
from reqgraph.llm.router import structured
from reqgraph.sim.stakeholder import MAX_ITEMS, Selection, load_prompt

from reqgraph_evals.scenario import load_scenario

REPORTS = Path(__file__).resolve().parents[1] / "reports"
DIALOGS = {
    "dev-01": "dialogs/interview-2026-10-29-free-coverage-t305-12-v3/dev-01-cooperative-r1.md",
    "dev-02": "dialogs/interview-2026-10-29-free-coverage-t305-12-v3b/dev-02-cooperative-r1.md",
}
# (scenario, question number, ids a good choice names; empty — nothing new to tell)
CASES: list[tuple[str, int, set[str]]] = [
    ("dev-01", 1, {"H-022", "H-023", "H-024"}),
    ("dev-01", 3, {"H-015", "H-016", "H-017"}),
    ("dev-01", 6, {"H-018", "H-019", "H-020"}),  # a miss in v3: rules of booking
    ("dev-01", 7, {"H-006", "H-007", "H-010"}),
    ("dev-01", 8, set()),  # constraints are told already
    ("dev-02", 5, {"H-001", "H-002", "H-003"}),
    ("dev-02", 7, {"H-011", "H-012", "H-013"}),  # a miss in v3: scenarios
    ("dev-02", 8, {"H-028", "H-030", "H-031"}),
    ("dev-02", 9, {"H-039", "H-040"}),  # a miss in v3: terms and budget
    ("dev-02", 11, set()),  # a late courier: nothing new in the list
]


# T-310: OpenRouter's reasoning switch for the measured model; None — the provider's default
REASONING: dict[str, dict[str, Any] | None] = {
    "on": None,
    "low": {"reasoning": {"effort": "low"}},
    "off": {"reasoning": {"enabled": False}},
}


def set_reasoning(models: list[str], mode: str) -> None:
    """Put the reasoning mode into the loaded roles.yaml for these models (this process only)."""
    cfg = router._config()
    extra = REASONING[mode]
    for model in models:
        key = Step.parse(model).id
        if extra is None:
            cfg.model_settings.pop(key, None)
        else:
            cfg.model_settings[key] = ModelOptions(extra_body=extra)


def parse(md: str) -> dict[int, tuple[str, str, list[str]]]:
    """Questions of a dialog report: number -> (question, answer, ids told in full)."""
    turns = {}
    for block in re.split(r"\n## Вопрос ", md.split("## Не рассказано")[0])[1:]:
        n = int(block.split(" ", 1)[0])
        q = re.search(r"\*\*Интервьюер:\*\* (.*)", block)
        a = re.search(r"\*\*Заказчик:\*\* (.*)", block)
        told = re.findall(r"^- (H-\d+) .*— (?!повторил)", block, re.M)
        turns[n] = (q.group(1) if q else "", a.group(1) if a else "", told)
    return turns


async def run(models: list[str], repeat: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sid, n, expected in CASES:
        scenario = load_scenario(sid)
        turns = parse((REPORTS / DIALOGS[sid]).read_text(encoding="utf-8"))
        items = scenario.hidden.requirements
        revealed = {i for k in turns if k < n for i in turns[k][2]}
        revealed |= {r.id for r in items if r.in_brief}  # as Stakeholder.answer sees them
        prompt = load_prompt("stakeholder/select").render(
            question=turns[n][0],
            recent=[turns[n - 1][:2]] if n > 1 else [],
            untold=[r for r in items if r.id not in revealed],
            told=[r for r in items if r.id in revealed],
            max_items=MAX_ITEMS,
        )
        for model in models:
            for r in range(repeat):
                row: dict[str, Any] = {"case": f"{sid} Q{n}", "model": model, "rep": r}
                try:
                    sel, stats = await structured("stakeholder", prompt, Selection, model_id=model)
                except Exception as exc:  # a failed call is a result too
                    rows.append(row | {"error": str(exc)[:200]})
                    continue
                ids = [i for i in dict.fromkeys(sel.ids) if i in {x.id for x in items}]
                fresh = [i for i in ids if i not in revealed]
                told = (fresh or ids)[:MAX_ITEMS]  # the rule of Stakeholder.answer
                rows.append(
                    row
                    | {
                        "ids": told,
                        "found": len(set(told) & expected),
                        "expected": len(expected),
                        "wrong": len([i for i in told if i not in expected and i not in revealed]),
                        "repeat": len([i for i in told if i in revealed]),
                        "cost_usd": stats.cost_usd,
                        "input_tokens": stats.input_tokens,
                        "output_tokens": stats.output_tokens,
                    }
                )
                print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", default="openrouter/qwen/qwen3.8-27b")
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--reasoning", choices=sorted(REASONING), default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.reasoning:
        set_reasoning(args.models.split(","), args.reasoning)
    rows = asyncio.run(run(args.models.split(","), args.repeat))
    args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
