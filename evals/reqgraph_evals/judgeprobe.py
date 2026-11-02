"""The judge again on the references the author labelled by hand (T-310).

Each labelled reference is judged anew with the same prompt and the same candidates as in the run
(they are kept in labels/pairs-*.csv), so a change of the judge's model settings — here the
reasoning mode — is compared with the person's labels without new interviews or embeddings.
Agreement is Cohen's kappa «found fully or not» (what recall counts, threshold 0.8) and over the
three levels. Run: uv run python -m reqgraph_evals.judgeprobe --help
"""

import argparse
import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

from reqgraph.llm.router import CallStats, structured

from reqgraph_evals.metrics.agreement import agreement, cohen_kappa
from reqgraph_evals.metrics.label import human_path, read_human, read_pairs, references
from reqgraph_evals.metrics.recall import Verdict, judge_prompt
from reqgraph_evals.simprobe import REASONING, set_reasoning

LABELS = Path(__file__).resolve().parents[1] / "reports" / "labels"
# the author's labels: dev-03 (28, the check of the judge) and dev-01 (15, the narrow «partial»)
SETS = (
    LABELS / "pairs-results-2026-10-28-free-check-dev03.csv",
    LABELS / "pairs-results-2026-10-27-free-v8-levels.csv",
)
Judge = Callable[[str, list[str]], Awaitable[tuple[Verdict, CallStats | None]]]


def labelled(pairs: Path) -> list[dict[str, Any]]:
    """The references of a pairs file that the person labelled, with their candidates."""
    human = read_human(human_path(pairs))
    return [
        {**ref, "human": human[(ref["run"], ref["hidden_id"])]["human"], "set": pairs.stem}
        for ref in references(read_pairs(pairs))
        if (ref["run"], ref["hidden_id"]) in human
    ]


async def rejudge(refs: Sequence[dict[str, Any]], judge: Judge) -> list[dict[str, Any]]:
    rows = []
    for ref in refs:
        texts = [c["text"] for c in ref["candidates"]]
        row: dict[str, Any] = {k: ref[k] for k in ("set", "run", "hidden_id", "human")}
        try:
            verdict, stats = await judge(ref["hidden"], texts)
        except Exception as exc:  # a failed call is a result too
            rows.append(row | {"error": str(exc)[:200]})
            continue
        row["judge"] = verdict.level or "none"
        if stats is not None:
            row |= {
                "input_tokens": stats.input_tokens,
                "output_tokens": stats.output_tokens,
                "cost_usd": stats.cost_usd,
            }
        rows.append(row)
    return rows


def scores(rows: Sequence[dict[str, Any]]) -> dict[str, float]:
    done = [r for r in rows if "judge" in r]
    judge = [r["judge"] for r in done]
    human = [r["human"] for r in done]
    full = ([j == "full" for j in judge], [h == "full" for h in human])
    return {
        "references": len(done),
        "errors": len(rows) - len(done),
        "kappa": round(cohen_kappa(*full), 3) if done else 0.0,
        "agreement": round(agreement(*full), 3) if done else 0.0,
        "kappa_3": round(cohen_kappa(judge, human), 3) if done else 0.0,
        "output_tokens": sum(r.get("output_tokens", 0) for r in done),
        "cost_usd": round(sum(r.get("cost_usd", 0.0) for r in done), 6),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="openrouter/qwen/qwen3.8-27b")
    parser.add_argument("--reasoning", choices=sorted(REASONING), default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.reasoning:
        set_reasoning([args.model], args.reasoning)

    async def judge(reference: str, candidates: list[str]) -> tuple[Verdict, CallStats | None]:
        prompt = judge_prompt().render(reference=reference, candidates=candidates)
        return await structured("judge", prompt, Verdict, model_id=args.model)

    refs = [r for pairs in SETS for r in labelled(pairs)]
    rows = asyncio.run(rejudge(refs, judge))
    result = {
        "model": args.model,
        "reasoning": args.reasoning or "on",
        "all": scores(rows),
        **{s.stem: scores([r for r in rows if r["set"] == s.stem]) for s in SETS},
        "rows": rows,
    }
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
