"""Deterministic scores for probe answers, each in [0, 1]; ``score`` is the mean of the parts.

Temporary until the real checks exist: vague terms -> ISO-001 (T-107), process structure ->
SCH/SND (T-106). The probe is re-run with real checks in T-601.
"""

import re
from collections import deque
from collections.abc import Mapping, Sequence
from typing import Any

from reqgraph_evals.schemas import Extraction, ProcessSketch, Question, Rewrite

MATCH_THRESHOLD = 0.5
STEM = 5  # crude Russian stemming: first letters of a word survive most inflections
STOPWORDS = {"систем", "котор", "чтобы", "можно", "должн", "когда", "через", "после", "также"}
VAGUE_TERMS = [
    "быстро",
    "быстрый",
    "удобно",
    "удобный",
    "надёжно",
    "надежно",
    "гибко",
    "просто",
    "интуитивно",
    "современный",
    "современным",
    "большое количество",
    "без проблем",
    "при необходимости",
    "желательно",
    "и т. д.",
    "и т.д.",
    "и т. п.",
    "оптимальн",
    "эффективн",
]
SHALL = re.compile(r"\bдолж(ен|на|но|ны)\b", re.IGNORECASE)

Scores = dict[str, float]


def _stems(text: str) -> set[str]:
    words = re.findall(r"\w+", text.lower().replace("ё", "е"))
    return {w[:STEM] for w in words if len(w) > 3 or w.isdigit()} - STOPWORDS


def _similar(a: str, b: str) -> float:
    """Share of the shorter text's word stems found in the other text."""
    sa, sb = _stems(a), _stems(b)
    return len(sa & sb) / min(len(sa), len(sb)) if sa and sb else 0.0


def _with_score(parts: Scores) -> Scores:
    return (
        {**parts, "score": round(sum(parts.values()) / len(parts), 4)} if parts else {"score": 0.0}
    )


def vague_terms(text: str) -> list[str]:
    low = text.lower()
    return [t for t in VAGUE_TERMS if t in low]


def score_extract(out: Extraction, expected: Sequence[Mapping[str, str]]) -> Scores:
    """Greedy one-to-one matching of extracted to expected requirements by text similarity."""
    found = list(out.requirements)
    used: set[int] = set()
    matched = kind_ok = 0
    for exp in expected:
        best, best_i = 0.0, -1
        for i, got in enumerate(found):
            if i not in used and (r := _similar(exp["text"], got.text)) > best:
                best, best_i = r, i
        if best >= MATCH_THRESHOLD:
            used.add(best_i)
            matched += 1
            kind_ok += found[best_i].kind == exp["kind"]
    recall = matched / len(expected) if expected else 0.0
    precision = matched / len(found) if found else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    vague = sum(bool(vague_terms(r.text)) for r in found)
    return {
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "f1": round(f1, 4),
        "kind_accuracy": round(kind_ok / matched, 4) if matched else 0.0,
        "no_vague": round(1 - vague / len(found), 4) if found else 0.0,
        "score": round(f1, 4),
    }


def _reachable(start: set[str], edges: Mapping[str, list[str]]) -> set[str]:
    seen, queue = set(start), deque(start)
    while queue:
        for nxt in edges.get(queue.popleft(), []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def score_process(out: ProcessSketch, expected: Mapping[str, Any]) -> Scores:
    ids = {n.id for n in out.nodes}
    kinds = {n.id: n.kind for n in out.nodes}
    fwd: dict[str, list[str]] = {}
    back: dict[str, list[str]] = {}
    for f in out.flows:
        fwd.setdefault(f.source, []).append(f.target)
        back.setdefault(f.target, []).append(f.source)
    starts = {i for i, k in kinds.items() if k == "start"}
    ends = {i for i, k in kinds.items() if k == "end"}
    gateways = [i for i, k in kinds.items() if k == "xor"]
    refs_ok = all(f.source in ids and f.target in ids for f in out.flows)
    reach = _reachable(starts, fwd) if len(starts) == 1 else set()
    to_end = _reachable(ends, back)
    names = " ".join(n.name.lower().replace("ё", "е") for n in out.nodes if n.kind == "task")
    task_stems = [t.replace("ё", "е") for t in expected.get("tasks", [])]
    parts = {
        "one_start": float(len(starts) == 1),
        "has_end": float(bool(ends)),
        "refs_ok": float(refs_ok),
        "all_reachable": float(bool(reach) and ids <= reach),
        "no_dead_ends": float(bool(ends) and ids <= to_end),
        "gateways_ok": float(
            len(gateways) >= expected.get("min_gateways", 0)
            and all(len(fwd.get(g, [])) >= 2 for g in gateways)
        ),
    }
    structure = sum(parts.values()) / len(parts)
    task_recall = sum(t in names for t in task_stems) / len(task_stems) if task_stems else 1.0
    return {
        **parts,
        "structure": round(structure, 4),
        "task_recall": round(task_recall, 4),
        "score": round((structure + task_recall) / 2, 4),
    }


def score_rewrite(out: Rewrite, keep: Sequence[str]) -> Scores:
    text = " ".join([out.statement, *out.acceptance]).lower().replace("ё", "е")
    return _with_score(
        {
            "has_shall": float(bool(SHALL.search(out.statement))),
            "no_vague": float(not vague_terms(text)),
            "keeps_subject": sum(k.replace("ё", "е") in text for k in keep) / len(keep)
            if keep
            else 1.0,
            "has_acceptance": float(
                bool(out.acceptance) and all(a.strip() for a in out.acceptance)
            ),
            "measurable": float(bool(re.search(r"\d", text))),
        }
    )


def score_question(out: Question, case: Mapping[str, Any]) -> Scores:
    q = out.question.strip()
    low = q.lower().replace("ё", "е")
    hidden = [h.lower().replace("ё", "е") for h in case.get("hidden", [])]
    raw_area = case.get("area", [])
    areas = [
        a.lower().replace("ё", "е") for a in ([raw_area] if isinstance(raw_area, str) else raw_area)
    ]
    told = f"{out.area} {q}".lower().replace("ё", "е")
    return _with_score(
        {
            "is_question": float(q.endswith("?")),
            "single": float(q.count("?") == 1),
            "short": float(len(q) <= 200),
            "no_hint": float(not any(h in low for h in hidden)),
            "on_topic": float(any(a in told for a in areas)),
        }
    )
