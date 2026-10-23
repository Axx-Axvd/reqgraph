"""Compiled BPMN is valid against the official OMG XSD (base of SCH-001, T-106)."""

import hashlib
import re
from pathlib import Path

import pytest
from reqgraph.dsl import bpmn_xsd
from reqgraph.dsl.bpmn_compile import compile_bpmn
from reqgraph.dsl.bpmn_xsd import validate_bpmn
from reqgraph.dsl.process import parse_process

from .conftest import all_processes, load


@pytest.mark.parametrize("name", sorted(all_processes()))
def test_compiled_processes_pass_the_xsd(name: str) -> None:
    xml = compile_bpmn(parse_process(load(all_processes()[name])))
    assert validate_bpmn(xml) == []


def test_invalid_bpmn_gives_line_and_reason() -> None:
    xml = compile_bpmn(parse_process(load(all_processes()["linear"])))
    broken = xml.replace("<bpmn:task ", "<bpmn:taskk ").replace("</bpmn:task>", "</bpmn:taskk>")
    errors = validate_bpmn(broken)
    assert errors and re.match(r"строка \d+: ", errors[0])


def test_not_xml_at_all() -> None:
    assert validate_bpmn("<definitions")[0].startswith("строка 1: XML не разобран")


def test_xsd_files_are_the_unchanged_omg_files() -> None:
    folder = Path(bpmn_xsd.__file__).parent / "xsd"
    readme = (folder / "README.md").read_text(encoding="utf-8")
    listed = dict(re.findall(r"\| (\w+\.xsd) \| `([0-9a-f]{64})` \|", readme))
    assert set(listed) == {p.name for p in folder.glob("*.xsd")}
    for name, digest in listed.items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest, name
