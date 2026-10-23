"""Golden BPMN files: any change of the compiler output shows up in the diff.

Regenerate after an intended change: REQGRAPH_UPDATE_GOLDEN=1 uv run pytest packages/core/tests/dsl
"""

import os

import pytest
from reqgraph.dsl.bpmn_compile import compile_bpmn
from reqgraph.dsl.process import parse_process

from .conftest import GOLDEN, all_processes, load


@pytest.mark.parametrize("name", sorted(all_processes()))
def test_compiler_output_matches_golden(name: str) -> None:
    xml = compile_bpmn(parse_process(load(all_processes()[name])))
    path = GOLDEN / f"{name}.bpmn"
    if os.environ.get("REQGRAPH_UPDATE_GOLDEN") == "1":
        path.write_bytes(xml.encode("utf-8"))
    assert path.read_bytes().decode("utf-8") == xml, f"{path.name}: REQGRAPH_UPDATE_GOLDEN=1"


def test_every_golden_file_has_a_process() -> None:
    assert {p.stem for p in GOLDEN.glob("*.bpmn")} == set(all_processes())
