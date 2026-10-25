"""Scenarios of the experiment (T-303, 09_eval): a brief, the client and the hidden requirements.

One folder per scenario in evals/scenarios/<id>/:
- scenario.yaml — title, domain, size (S/M/L), split (dev/test);
- brief.md — what the client writes before the interview;
- persona.yaml — who the client is: name, role, facts about the company, manner of speech
  (the character — cooperative, vague, contradictory — is a parameter of the simulator, T-302);
- hidden.yaml — the reference: the requirements the client knows; the simulator reveals one only
  when a question touches its topic (`reveal`), recall is counted against them (T-304).

Test scenarios are sealed: their files are listed with hashes in test-scenarios.sha256 and are not
loaded before the final matrix (S6) unless asked explicitly (CLAUDE.md, honesty of the experiment).
"""

import hashlib
from collections import Counter
from pathlib import Path

import yaml
from rapidfuzz import fuzz
from reqgraph.graph.store.config import Area
from reqgraph.sim.scenario import Hidden, HiddenRequirement, Persona, Scenario, ScenarioInfo

SCENARIOS = Path(__file__).resolve().parent.parent / "scenarios"
MANIFEST = "test-scenarios.sha256"
FILES = ("scenario.yaml", "brief.md", "persona.yaml", "hidden.yaml")
AREAS: tuple[Area, ...] = (
    "goals",
    "stakeholders",
    "scenarios",
    "exceptions",
    "data",
    "rules",
    "integrations",
    "nfr",
    "constraints",
)
SIZES = {"S": 25, "M": 40, "L": 60}  # hidden requirements per size, ± TOLERANCE
TOLERANCE = 5
__all__ = ["Hidden", "HiddenRequirement", "Persona", "Scenario", "ScenarioInfo"]
MAX_IN_BRIEF = 0.3  # at most this share of the reference may already be in the brief


class SealedScenario(RuntimeError):
    """A test scenario is opened only for the final matrix (S6)."""


def _yaml(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def scenario_ids(root: Path = SCENARIOS, split: str | None = None) -> list[str]:
    ids = sorted(p.name for p in root.iterdir() if (p / "scenario.yaml").is_file())
    return [i for i in ids if split is None or i.startswith(split)]


def load_scenario(scenario_id: str, root: Path = SCENARIOS, *, final: bool = False) -> Scenario:
    """A dev scenario; a test one only with final=True (the final matrix of S6)."""
    if scenario_id.startswith("test") and not final:
        raise SealedScenario(
            f"{scenario_id}: test-сценарий открывается только для финальной матрицы (S6)"
        )
    folder = root / scenario_id
    info = ScenarioInfo.model_validate(_yaml(folder / "scenario.yaml"))
    if info.id != scenario_id:
        raise ValueError(f"{folder}: id в scenario.yaml — «{info.id}»")
    return Scenario(
        info=info,
        brief=(folder / "brief.md").read_text(encoding="utf-8"),
        persona=Persona.model_validate(_yaml(folder / "persona.yaml")),
        hidden=Hidden.model_validate(_yaml(folder / "hidden.yaml")),
    )


def problems(scenario: Scenario) -> list[str]:
    """What breaks the protocol of 09_eval: size, areas, ids, kinds, too much in the brief."""
    found: list[str] = []
    items = scenario.hidden.requirements
    need = SIZES[scenario.info.size]
    if abs(len(items) - need) > TOLERANCE:
        found.append(f"{len(items)} требований, для размера {scenario.info.size} нужно {need} ± 5")
    ids = [r.id for r in items]
    if ids != [f"H-{i:03d}" for i in range(1, len(items) + 1)]:
        found.append("id должны идти подряд: H-001, H-002, …")
    areas = Counter(r.area for r in items)
    missing = [a for a in AREAS if not areas[a]]
    if missing:
        found.append(f"нет требований в областях: {', '.join(missing)}")
    if not any(r.kind == "BR" for r in items):
        found.append("нет ни одного бизнес-требования (BR)")
    if len({r.statement for r in items}) != len(items):
        found.append("есть одинаковые формулировки")
    share = sum(r.in_brief for r in items) / len(items)
    if share > MAX_IN_BRIEF:
        found.append(f"в брифе уже {share:.0%} эталона, допустимо до {MAX_IN_BRIEF:.0%}")
    found += _unmarked_in_brief(scenario)
    return found


def _unmarked_in_brief(scenario: Scenario, threshold: float = 85.0) -> list[str]:
    """A requirement the brief states almost word for word must be marked in_brief."""
    brief = scenario.brief.lower()
    return [
        f"{r.id}: почти дословно есть в брифе — отметьте in_brief: true"
        for r in scenario.hidden.requirements
        if not r.in_brief and fuzz.partial_ratio(r.statement.lower(), brief) >= threshold
    ]


# --- the seal of the test scenarios -------------------------------------------------------------


def _test_files(root: Path) -> list[Path]:
    return sorted(
        root / scenario_id / name
        for scenario_id in scenario_ids(root, "test")
        for name in FILES
        if (root / scenario_id / name).is_file()
    )


def manifest(root: Path = SCENARIOS) -> str:
    """sha256 of every test scenario file, one line per file (like sha256sum)."""
    lines = []
    for path in _test_files(root):
        data = path.read_bytes().replace(b"\r\n", b"\n")  # the same hash on a Windows checkout
        digest = hashlib.sha256(data).hexdigest()
        lines.append(f"{digest}  {path.relative_to(root).as_posix()}")
    return "\n".join(lines) + ("\n" if lines else "")


def seal_broken(root: Path = SCENARIOS) -> list[str]:
    """Files that differ from the manifest: test scenarios were changed after sealing."""
    path = root / MANIFEST
    sealed = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    now = manifest(root).splitlines()
    return sorted(set(sealed) ^ set(now))
