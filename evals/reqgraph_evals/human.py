"""The pilot «a person instead of the simulator» (T-306): a person answers the interviewer.

One turn per call: `start` asks the first question and pauses, `answer` gives the person's answer
and pauses on the next question, `finish` ends the interview. Between calls the interview waits in
its checkpoint (the pause of `reqgraph interview`, T-301), so the calls may come from a terminal,
from a browser page through the session, or after a break of any length. The answer goes to the
interviewer as it was typed. The marks «what I told» are optional and checked against the
scenario. At the end the run is one row in the format of the simulator's interviews, read by the
same `reqgraph-evals metrics`, and a dialog for the manual check.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from importlib.metadata import version
from pathlib import Path
from typing import Any

from pydantic_ai.models import Model
from reqgraph.agents.interview import EVENTS, Outcome, Reply, interview_project
from reqgraph.agents.nodes import DONE
from reqgraph.agents.run import init_project
from reqgraph.agents.state import AREAS
from reqgraph.llm.config import load_roles
from reqgraph.llm.prompts import read_prompt
from reqgraph.sim.stakeholder import Character, Stakeholder

from reqgraph_evals import interview
from reqgraph_evals.scenario import load_scenario

RUNS = Path(__file__).resolve().parents[1] / "runs" / "human"
REPORTS = Path(__file__).resolve().parents[1] / "reports"
CHARACTER: Character = "cooperative"  # the person follows the rules of the cooperative simulator
METHOD = "M2-human"
STATE = ".human"  # the session's own files inside the project folder; the store does not read it
AREA_TITLES = {
    "goals": "Цели",
    "stakeholders": "Роли и участники",
    "scenarios": "Сценарии работы",
    "exceptions": "Исключения и ошибки",
    "data": "Данные",
    "rules": "Правила и расчёты",
    "integrations": "Интеграции",
    "nfr": "Качество: скорость, надёжность, безопасность",
    "constraints": "Ограничения",
}


class UnknownMark(ValueError):
    """A mark names no hidden requirement of the scenario (or one the brief already says)."""


@dataclass(frozen=True)
class Pending:
    turn: int
    question: str
    area: str | None


@dataclass
class Session:
    folder: Path  # the project folder of the run; the metrics read it like a simulator's run
    scenario: str
    repeat: int
    max_turns: int
    profile: str
    status: str = "asking"  # asking | done
    pending: Pending | None = None
    csv: Path = field(default_factory=Path)
    dialog: Path = field(default_factory=Path)

    @property
    def project(self) -> Path:
        return self.folder

    @property
    def log(self) -> Path:
        return self.folder / STATE / "human.jsonl"

    def save(self) -> None:
        data = asdict(self) | {"folder": str(self.folder), "csv": str(self.csv)}
        data["dialog"] = str(self.dialog)
        path = self.folder / STATE / "session.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def card(scenario_id: str) -> dict[str, Any]:
    """What the person answers from: the persona, the brief, the rules and the hidden requirements
    outside the brief by area. Test scenarios stay sealed (load_scenario refuses them)."""
    scenario = load_scenario(scenario_id)
    persona = scenario.persona
    hidden = [r for r in scenario.hidden.requirements if not r.in_brief]
    areas = [
        {
            "area": area,
            "title": AREA_TITLES[area],
            "requirements": [
                {"id": r.id, "statement": r.statement, "in_brief": r.in_brief}
                for r in hidden
                if r.area == area
            ],
        }
        for area in AREAS
        if any(r.area == area for r in hidden)
    ]
    return {
        "scenario": scenario.id,
        "title": scenario.info.title,
        "character": CHARACTER,
        "persona": {
            "name": persona.name,
            "role": persona.role,
            "facts": list(persona.facts),
            "style": persona.style,
        },
        "brief": scenario.brief,
        "rules": read_prompt("reqgraph_evals", "human/rules").source,
        "areas": areas,
        "area_titles": AREA_TITLES,
    }


def load(folder: Path) -> Session:
    data = json.loads((folder / STATE / "session.json").read_text(encoding="utf-8"))
    pending = data.pop("pending")
    session = Session(
        folder,  # where it is now, even if the folder was moved
        data["scenario"],
        data["repeat"],
        data["max_turns"],
        data["profile"],
        data["status"],
        None if pending is None else Pending(**pending),
        Path(data["csv"]),
        Path(data["dialog"]),
    )
    return session


async def start(
    scenario_id: str,
    *,
    root: Path = RUNS,
    max_turns: int = 30,
    profile: str = "free",
    models: Mapping[str, Model] | None = None,
) -> Session:
    """A new session: the project from the scenario's brief, the first question."""
    scenario = load_scenario(scenario_id)
    repeat = 1 + sum(1 for _ in root.glob(f"{scenario_id}-{CHARACTER}-r*"))
    folder = init_project(
        root / f"{scenario_id}-{CHARACTER}-r{repeat}",
        name=scenario.info.title,
        brief=scenario.brief,
        project_id=scenario_id,
    )
    session = Session(folder, scenario_id, repeat, max_turns, profile)
    await _drive(session, None, models=models)
    return session


async def answer(
    folder: Path,
    text: str,
    told: Sequence[str] = (),
    *,
    models: Mapping[str, Model] | None = None,
    max_iter: int | None = None,
    reports: Path = REPORTS,
) -> Session:
    """The person's answer to the pending question; the session pauses on the next one or, at
    the end of the interview, writes its row and dialog."""
    session = load(folder)
    if session.pending is None:
        raise RuntimeError(f"{folder.name}: интервью уже закончено")
    if not text.strip():
        raise ValueError("пустой ответ: напишите, что сказал заказчик")
    marks = _checked(session.scenario, told)
    pending = session.pending
    record = {
        "number": pending.turn,
        "question": pending.question,
        "area": pending.area,
        "answer": text,
        "told": marks,
    }
    await _drive(session, text, models=models, max_iter=max_iter, reports=reports, record=record)
    return session


async def finish(
    folder: Path,
    *,
    models: Mapping[str, Model] | None = None,
    max_iter: int | None = None,
    reports: Path = REPORTS,
) -> Session:
    """The person ends the interview on the pending question: the pipeline runs as usual."""
    session = load(folder)
    if session.pending is None:
        return session
    await _drive(session, dict(DONE), models=models, max_iter=max_iter, reports=reports)
    return session


def _checked(scenario_id: str, told: Sequence[str]) -> list[str]:
    scenario = load_scenario(scenario_id)
    known = {r.id for r in scenario.hidden.requirements if not r.in_brief}
    marks = list(dict.fromkeys(t.strip() for t in told if t.strip()))
    if unknown := [m for m in marks if m not in known]:
        raise UnknownMark(f"нет таких скрытых требований в {scenario_id}: {', '.join(unknown)}")
    return marks


async def _drive(
    session: Session,
    reply: str | dict[str, bool] | None,
    *,
    models: Mapping[str, Model] | None,
    max_iter: int | None = None,
    reports: Path = REPORTS,
    record: dict[str, Any] | None = None,
) -> None:
    """Resume the interview: the pending question gets `reply` (None: only ask the first one),
    the next question is kept as pending and the interview pauses on it."""
    asked = 0
    session.pending = None

    async def respond(question: str, turn: int) -> Reply:
        nonlocal asked
        asked += 1
        if asked == 1 and reply is not None:
            if record is not None:
                session.log.parent.mkdir(parents=True, exist_ok=True)
                with session.log.open("a", encoding="utf-8") as out:
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
            return reply
        session.pending = Pending(turn, question, _last_area(session.folder))
        return None  # pause: the next call answers it

    outcome = await interview_project(
        session.folder,
        respond,
        profile=session.profile,
        max_turns=session.max_turns,
        max_iter=max_iter,
        offline=True,
        models=models,
    )
    if not outcome.paused:
        session.status = "done"
        _write_result(session, outcome, reports)
    session.save()


def _last_area(folder: Path) -> str | None:
    events = interview._events(folder / "reports" / EVENTS)
    questions = [e for e in events if e["type"] == "question"]
    area = questions[-1].get("area") if questions else None
    return str(area) if area else None


def _turns(session: Session, sim: Stakeholder) -> list[interview.Turn]:
    if not session.log.is_file():
        return []
    turns = []
    for line in session.log.read_text(encoding="utf-8").splitlines():
        t = json.loads(line)
        told = [{"id": i, "mode": "tell", "area": sim.items[i].area} for i in t["told"]]
        turns.append(interview.Turn(t["number"], t["question"], t["area"], t["answer"], told))
    return turns


def _write_result(session: Session, outcome: Outcome, reports: Path) -> None:
    """The row in the format of the simulator's interviews and the dialog for the manual check."""
    scenario = load_scenario(session.scenario)
    sim = Stakeholder(scenario, CHARACTER)  # no model: only the scenario's items and what was told
    turns = _turns(session, sim)
    sim.revealed = {t["id"] for turn in turns for t in turn.told}
    row = interview.Row(
        session.scenario,
        CHARACTER,
        session.repeat,
        "coverage",
        METHOD,
        package_version=version("reqgraph"),
    )
    row.temperature = load_roles().temperature("analyst")
    events = interview._events(session.folder / "reports" / EVENTS)
    interview._fill(row, events, [], turns, sim)
    if outcome.summary is not None:
        row.requirements = outcome.summary.requirements
        row.errors_final = outcome.summary.errors
    stem = f"interview-{date.today().isoformat()}-human-{session.scenario}-r{session.repeat}"
    session.csv = reports / f"{stem}.csv"
    interview.write_csv([row], session.csv)
    session.dialog = reports / "dialogs" / stem / f"{session.scenario}-{CHARACTER}-r{row.repeat}.md"
    session.dialog.parent.mkdir(parents=True, exist_ok=True)
    text = interview.dialog_markdown(row, turns, sim)
    note = (
        "Отвечал человек по карточке сценария (T-306); «рассказано» — по его отметкам после "
        "ответов, отметки необязательны."
    )
    title, rest = text.split("\n", 1)
    session.dialog.write_text(f"{title}\n\n{note}\n{rest}", encoding="utf-8")


def page_docs(session: Session) -> dict[str, dict[str, Any]]:
    """The documents of the pilot page's database (evals/human/page.html): the session's state
    with the card, and the pending question as a turn the page answers."""
    status = "done" if session.status == "done" else "asking"
    docs: dict[str, dict[str, Any]] = {
        "pilot/state": {
            "scenario": session.scenario,
            "session": session.folder.name,
            "status": status,
            "max_turns": session.max_turns,
            "card": card(session.scenario),
        }
    }
    if session.pending is not None:
        p = session.pending
        docs[f"turns/{p.turn:04d}"] = {"turn": p.turn, "question": p.question, "area": p.area}
    return docs


async def from_page(
    folder: Path,
    turn: Mapping[str, Any],
    *,
    models: Mapping[str, Model] | None = None,
    max_iter: int | None = None,
    reports: Path = REPORTS,
) -> Session:
    """Apply the page's turn document: its answer and marks, or the end of the interview."""
    session = load(folder)
    if session.pending is None or turn.get("turn") != session.pending.turn:
        raise RuntimeError(
            f"на странице вопрос {turn.get('turn')}, а сессия ждёт ответа на "
            f"{session.pending.turn if session.pending else '—'}"
        )
    if turn.get("finish"):
        return await finish(folder, models=models, max_iter=max_iter, reports=reports)
    told = [str(t) for t in turn.get("told") or []]
    return await answer(
        folder,
        str(turn.get("answer") or ""),
        told,
        models=models,
        max_iter=max_iter,
        reports=reports,
    )
