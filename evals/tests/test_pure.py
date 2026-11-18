"""Own count on PURE (T-308): extraction, splitting, a seeded sample, the report."""

import csv
import subprocess
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from reqgraph_evals import pure

SAMPLE = """\
Table of Contents
3.1 Booking ........................................ 12

1. Introduction
This document describes the system. Readers will find the scope here.

3. Functional Requirements
3.1 Booking
The system shall let a member book a seat. The booking
shall be kept for 30 minutes.
Definition: a seat is a place in a reading room.
FR-12 Show the list of free seats.
3.2 Reports
Staff must see the daily load. A report will be sent every Monday.
"""


def test_requirements_are_modal_sentences_and_numbered_items_with_their_section() -> None:
    found = pure.split_requirements(SAMPLE)
    assert [(r.section, r.text) for r in found] == [
        ("1", "Readers will find the scope here."),
        ("3.1", "The system shall let a member book a seat."),
        ("3.1", "The booking shall be kept for 30 minutes."),
        ("3.1", "FR-12 Show the list of free seats."),
        ("3.2", "Staff must see the daily load."),
        ("3.2", "A report will be sent every Monday."),
    ]
    assert [r.pos for r in found] == [1, 2, 3, 4, 5, 6]


def test_the_order_is_a_stable_permutation_per_document() -> None:
    first = pure.order(40, seed=42, doc="2009 - library")
    assert sorted(first) == list(range(40))
    assert first == pure.order(40, seed=42, doc="2009 - library")
    assert first != pure.order(40, seed=42, doc="2005 - phin")


def test_wilson_interval_on_known_values() -> None:
    assert pure.wilson(5, 10) == pytest.approx((0.2366, 0.7634), abs=1e-4)
    assert pure.wilson(0, 10) == pytest.approx((0.0, 0.2775), abs=1e-4)
    assert pure.wilson(180, 180)[1] == pytest.approx(1.0)


def fake_run(stdout: str, made: Path | None = None) -> Any:
    calls: list[Sequence[str]] = []

    def run(args: Sequence[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if made is not None:
            made.write_text(stdout, encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_text_comes_from_pdftotext_soffice_or_html(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    run = fake_run("The system shall work.")
    assert pure.extract_text(pdf, run=run) == "The system shall work."
    assert run.calls[0][0] == "pdftotext"

    doc = tmp_path / "b.doc"
    doc.write_bytes(b"x")
    out = tmp_path / "out"
    out.mkdir()
    run = fake_run("Staff must log in.", made=out / "b.txt")
    assert pure.extract_text(doc, run=run, workdir=out) == "Staff must log in."
    assert run.calls[0][0] == "soffice"

    page = tmp_path / "c.html"
    page.write_text("<html><body><p>The site <b>shall</b> load.</p></body></html>", "utf-8")
    assert "The site shall load." in pure.extract_text(page)


def test_a_missing_program_is_a_clear_error(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")

    def run(args: Sequence[str], **_: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(args[0])

    with pytest.raises(RuntimeError, match="pdftotext"):
        pure.extract_text(pdf, run=run)


def test_the_sample_file_has_no_requirement_text(tmp_path: Path) -> None:
    found = {"doc-a": pure.split_requirements(SAMPLE)}
    out = tmp_path / "sample.csv"
    rows = pure.write_sample(found, n=3, seed=42, out=out)
    assert len(rows) == 3
    with out.open(encoding="utf-8") as f:
        saved = list(csv.DictReader(f))
    assert list(saved[0]) == pure.FIELDS
    assert all("shall" not in v and "must" not in v for row in saved for v in row.values())


def labelled(tmp_path: Path) -> Path:
    path = tmp_path / "labels.csv"
    rows = [
        {"doc": "a", "pos": "1", "section": "3", "kind": "FR", "group": "typical", "reason": ""},
        {"doc": "a", "pos": "2", "section": "3", "kind": "FR", "group": "unique", "reason": "x"},
        {"doc": "b", "pos": "5", "section": "4", "kind": "NFR", "group": "typical", "reason": ""},
        {"doc": "b", "pos": "7", "section": "4", "kind": "NFR", "group": "typical", "reason": ""},
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=pure.FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_report_counts_typical_overall_by_document_and_by_kind(tmp_path: Path) -> None:
    result = pure.report(labelled(tmp_path))
    assert result["total"] == {"n": 4, "typical": 3, "share": 0.75}
    assert result["by_doc"]["a"]["share"] == 0.5
    assert result["by_kind"]["NFR"] == {"n": 2, "typical": 2, "share": 1.0}
    low, high = result["interval"]
    assert low < 0.75 < high
    text = pure.report_markdown(result)
    assert "75%" in text and "| a |" in text


def answers(*items: str) -> Any:
    queue: Iterator[str] = iter(items)
    return lambda _question: next(queue)


def test_second_labelling_hides_the_first_and_counts_kappa(tmp_path: Path) -> None:
    path = labelled(tmp_path)
    texts = {("a", 1): "A1", ("a", 2): "A2", ("b", 5): "B5", ("b", 7): "B7"}
    shown: list[str] = []
    result = pure.check(
        path, texts.__getitem__, answers("x", "t", "t", "t", "u"), share=1.0, echo=shown.append
    )
    assert result["checked"] == 4
    assert not any("typical" in s or "unique" in s for s in shown)  # the first labels are hidden
    assert pure.check_path(path).exists()
    assert 0 <= result["agreement"] <= 1
