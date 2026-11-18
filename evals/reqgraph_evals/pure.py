"""Own count on the PURE dataset (T-308): how many requirements of real documents are typical.

PURE (Ferrari, Spagnolo, Gnesi, RE 2017) is a set of public requirements documents. The documents
stay outside the repository (their own copyright): this module takes their text with external
programs (pdftotext for PDF, LibreOffice for doc and rtf, the standard HTML parser for pages),
cuts it into requirements, draws a seeded sample per document and writes a CSV without the
requirement texts. The labels follow the rule of evals/scenarios/README.md; the counting rule and
the list of documents are in docs/backlog.md (T-308), written before the documents were opened.
"""

import csv
import math
import random
import re
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from reqgraph_evals.groups import ANSWERS, CHEAT_SHEET
from reqgraph_evals.metrics.agreement import agreement, cohen_kappa

FIELDS = ["doc", "pos", "section", "kind", "group", "reason"]
CHECK_FIELDS = ["doc", "pos", "first", "second"]
Run = Callable[..., subprocess.CompletedProcess[str]]
Ask = Callable[[str], str]
Echo = Callable[[str], None]

_TOC = re.compile(r"\.{4,}|…{2,}")
_HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+(\S.*)$")
_ITEM = re.compile(r"^\s*[A-Z]{1,6}[-_ ]?\d+(?:\.\d+)*\b")
_MODAL = re.compile(r"\b(shall|must|will)\b", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"])")


@dataclass(frozen=True)
class Requirement:
    pos: int  # the number of the requirement in its document, from 1
    section: str
    text: str


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n\n")


def extract_text(path: Path, run: Run = subprocess.run, workdir: Path | None = None) -> str:
    """The plain text of a document: PDF, doc, docx, rtf, htm or html."""
    suffix = path.suffix.lower()
    if suffix in {".htm", ".html"}:
        parser = _Text()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        return re.sub(r"[ \t]+", " ", "".join(parser.parts))
    if suffix == ".pdf":
        return _call(run, ["pdftotext", "-enc", "UTF-8", str(path), "-"]).stdout
    with tempfile.TemporaryDirectory() as tmp:
        out = workdir or Path(tmp)
        args = [
            "soffice",
            "--headless",
            "--convert-to",
            "txt:Text",
            "--outdir",
            str(out),
            str(path),
        ]
        _call(run, args)
        return (out / f"{path.stem}.txt").read_text(encoding="utf-8", errors="replace")


def _call(run: Run, args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return run(args, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise RuntimeError(f"нет программы {args[0]}: текст документа не извлечь") from None


def split_requirements(text: str) -> list[Requirement]:
    """Numbered items (FR-12, REQ 5) and sentences with shall / must / will, with the number of
    the section they are in. Table of contents lines and headings are not requirements."""
    found: list[tuple[str, str]] = []
    section = ""
    paragraph: list[str] = []
    para_section = ""

    def flush() -> None:
        if not paragraph:
            return
        joined = " ".join(" ".join(paragraph).split())
        paragraph.clear()
        if _ITEM.match(joined) and not _HEADING.match(joined):
            found.append((para_section, joined))
            return
        found.extend((para_section, s) for s in _SENTENCE.split(joined) if _MODAL.search(s))

    for line in text.replace("\r", "").split("\n"):
        stripped = line.strip()
        if not stripped or _TOC.search(stripped):
            flush()
            continue
        heading = _HEADING.match(stripped)
        if heading and not _MODAL.search(stripped):
            flush()
            section = heading.group(1)
            continue
        if heading or _ITEM.match(stripped):
            flush()
            if heading:
                section = heading.group(1)
        if not paragraph:
            para_section = section
        paragraph.append(stripped)
    flush()
    return [Requirement(i, s, t) for i, (s, t) in enumerate(found, start=1)]


def order(count: int, seed: int, doc: str) -> list[int]:
    """A seeded permutation of a document's requirement indexes: the sample is its start,
    a dropped non-requirement is replaced by the next one."""
    indexes = list(range(count))
    random.Random(f"{seed}:{doc}").shuffle(indexes)
    return indexes


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """The Wilson score interval of a share k / n (95% by default)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def write_sample(
    found: Mapping[str, Sequence[Requirement]], n: int, seed: int, out: Path
) -> list[dict[str, str]]:
    """n requirements of each document in the seeded order; no requirement text in the file."""
    rows = []
    for doc, reqs in found.items():
        for i in order(len(reqs), seed, doc)[:n]:
            r = reqs[i]
            rows.append(
                dict.fromkeys(FIELDS, "") | {"doc": doc, "pos": str(r.pos), "section": r.section}
            )
    _write(out, FIELDS, rows)
    return rows


def _write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_labels(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _share(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    typical = sum(r["group"] == "typical" for r in rows)
    return {"n": len(rows), "typical": typical, "share": round(typical / len(rows), 4)}


def report(path: Path) -> dict[str, Any]:
    """The share of typical requirements: overall with the Wilson interval, by document, by kind."""
    rows = [r for r in read_labels(path) if r["group"] in ("typical", "unique")]
    if not rows:
        raise ValueError(f"{path}: нет размеченных требований")
    total = _share(rows)
    low, high = wilson(total["typical"], total["n"])
    by: dict[str, dict[str, list[dict[str, str]]]] = {"doc": {}, "kind": {}}
    for r in rows:
        by["doc"].setdefault(r["doc"], []).append(r)
        by["kind"].setdefault(r["kind"] or "?", []).append(r)
    return {
        "total": total,
        "interval": (round(low, 4), round(high, 4)),
        "by_doc": {k: _share(v) for k, v in sorted(by["doc"].items())},
        "by_kind": {k: _share(v) for k, v in sorted(by["kind"].items())},
    }


def report_markdown(result: Mapping[str, Any]) -> str:
    total, (low, high) = result["total"], result["interval"]
    lines = [
        "# Типовые требования в документах PURE (T-308)",
        "",
        f"Всего {total['n']}, типовых {total['typical']} — {total['share']:.0%} "
        f"(95% интервал Уилсона {low:.0%}–{high:.0%}).",
        "",
        "| Документ | Требований | Типовых | Доля |",
        "|---|---|---|---|",
        *(
            f"| {doc} | {s['n']} | {s['typical']} | {s['share']:.0%} |"
            for doc, s in result["by_doc"].items()
        ),
        "",
        "| Вид | Требований | Типовых | Доля |",
        "|---|---|---|---|",
        *(
            f"| {kind} | {s['n']} | {s['typical']} | {s['share']:.0%} |"
            for kind, s in result["by_kind"].items()
        ),
        "",
    ]
    return "\n".join(lines)


def check_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}-check.csv")


def check(
    path: Path,
    text_of: Callable[[tuple[str, int]], str],
    ask: Ask,
    share: float = 0.2,
    seed: int = 42,
    echo: Echo = print,
) -> dict[str, Any]:
    """Second labelling of a seeded share of the labelled requirements, the first labels hidden;
    agreement and Cohen's kappa. The text is shown to the person at the keyboard only."""
    rows = [r for r in read_labels(path) if r["group"] in ("typical", "unique")]
    picked = random.Random(seed).sample(rows, max(1, round(len(rows) * share)))
    echo(CHEAT_SHEET)
    done: list[dict[str, str]] = []
    for i, row in enumerate(picked, start=1):
        text = text_of((row["doc"], int(row["pos"])))
        echo(f"\n[{i}/{len(picked)}] {row['doc']} #{row['pos']}\n  {text}")
        answer = ""
        while answer not in ANSWERS:
            answer = (
                ask("  t — типовое, u — уникальное, ? — правило, q — закончить: ").strip().lower()
            )
            if answer == "q":
                break
            if answer == "?":
                echo(CHEAT_SHEET)
            elif answer not in ANSWERS:
                echo("  ответьте t, u, ? или q")
        if answer == "q":
            break
        done.append(
            {"doc": row["doc"], "pos": row["pos"], "first": row["group"], "second": ANSWERS[answer]}
        )
    _write(check_path(path), CHECK_FIELDS, done)
    if not done:
        return {"checked": 0, "agreement": 0.0, "kappa": 0.0}
    first, second = [r["first"] for r in done], [r["second"] for r in done]
    return {
        "checked": len(done),
        "agreement": round(agreement(first, second), 4),
        "kappa": round(cohen_kappa(first, second), 4),
    }


def document(folder: Path, doc: str) -> Path:
    """The file of a document by its name in the set, any extension (doc before pdf)."""
    for suffix in (".doc", ".docx", ".rtf", ".pdf", ".htm", ".html"):
        path = folder / f"{doc}{suffix}"
        if path.exists():
            return path
    raise FileNotFoundError(f"нет документа {doc!r} в {folder}")


def texts(folder: Path, docs: Sequence[str]) -> dict[str, list[Requirement]]:
    return {doc: split_requirements(extract_text(document(folder, doc))) for doc in docs}
