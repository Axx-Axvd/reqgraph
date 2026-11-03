"""B1 one-shot (09_eval, T-405): the brief and the interview of the M1 run of the same case go
to the model in one request; the answer — requirements, processes and entities in one form — is
built by the same code as the agents' answers, with no checks, no retries and no repair.

The model is the Analyst's (the same ladder as the agents): one model for every method.
"""

import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.models import Model
from reqgraph.agents.analyst import AnalystDraft, DraftActor, DraftRequirement, to_patch
from reqgraph.agents.common import guarded
from reqgraph.agents.modeler import DraftEntity, DraftProcess, ModelerDraft, to_models
from reqgraph.agents.run import init_project
from reqgraph.dsl.readers import model_readers
from reqgraph.graph.errors import GraphError
from reqgraph.graph.nodes import InterviewTurn, NodeKind
from reqgraph.graph.patch import AddOp, GraphPatch, Op
from reqgraph.graph.store import FileStore
from reqgraph.llm.config import load_roles
from reqgraph.llm.prompts import read_prompt
from reqgraph.llm.router import structured
from reqgraph.sim.stakeholder import Character

from reqgraph_evals.interview import Row
from reqgraph_evals.scenario import SCENARIOS, load_scenario

ROLE = "analyst"


class OneShotDraft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    actors: list[DraftActor] = Field(default_factory=list)
    requirements: list[DraftRequirement] = Field(default_factory=list)
    processes: list[DraftProcess] = Field(default_factory=list)
    entities: list[DraftEntity] = Field(default_factory=list)


def transcript(source: Path) -> list[InterviewTurn]:
    """The turns of a kept run, in order."""
    graph = FileStore(source, readers=model_readers()).load().graph
    return sorted(
        (n for n in graph.nodes_of("TURN") if isinstance(n, InterviewTurn)), key=lambda n: n.id
    )


async def run_one_shot(
    scenario_id: str,
    character: Character,
    repeat: int,
    *,
    source: Path,
    profile: str = "free",
    models: Mapping[str, Model] | None = None,
    root: Path = SCENARIOS,
    keep: Path | None = None,
) -> Row:
    """One request for the case whose M1 run is kept in `source`; the project goes to `keep`."""
    scenario = load_scenario(scenario_id, root)
    cfg = load_roles()
    row = Row(scenario_id, character, repeat, "one-shot", "B1", package_version=version("reqgraph"))
    row.temperature = cfg.temperature(ROLE)
    row.seed = (cfg.defaults.seed or 0) + repeat
    if not source.is_dir():
        row.error = f"B1 нужен прогон M1 того же случая: нет {source}"
        return row
    turns = transcript(source)
    with tempfile.TemporaryDirectory() as tmp:
        folder = init_project(
            Path(tmp) / scenario_id,
            name=scenario.info.title,
            brief=scenario.brief,
            project_id=scenario_id,
        )
        store = FileStore(folder, readers=model_readers())
        project = store.load()
        ops: list[Op] = [
            AddOp(
                op="add",
                kind=NodeKind.TURN,
                tmp_id=f"t{i}",
                fields={"role": t.role, "text": t.text},
            )
            for i, t in enumerate(turns)
        ]
        graph = project.graph.apply(GraphPatch(ops=ops), actor="agent").graph
        prompt = read_prompt("reqgraph_evals", "oneshot/extract")
        text = prompt.render(
            brief=scenario.brief,
            turns=[
                {"id": t.id, "role": t.role, "text": t.text}
                for t in graph.nodes_of("TURN")
                if isinstance(t, InterviewTurn)
            ],
        )
        chosen = (models or {}).get(ROLE) or (models or {}).get("*")
        try:
            draft, stats = await structured(ROLE, text, OneShotDraft, profile=profile, model=chosen)
        except Exception as exc:  # a failed run is a result too (CLAUDE.md, honesty)
            row.error = f"{type(exc).__name__}: {exc}"[:300]
            return row
        row.llm_calls = 1
        row.models = f"{ROLE}={stats.provider}/{stats.model}"
        row.prompt_hashes = f"oneshot/extract={prompt.hash}"
        row.input_tokens, row.output_tokens = stats.input_tokens, stats.output_tokens
        row.cost_usd, row.latency_ms = stats.cost_usd, stats.latency_ms
        requirements = to_patch(
            AnalystDraft(actors=draft.actors, requirements=draft.requirements), graph
        )
        # the guard only keeps the graph whole (unknown refs, wrong links): no checks, no retry
        kept = guarded(requirements.patch, graph, "analyst", [], requirements.dropped)
        graph = graph.apply(kept.patch, actor="agent").graph
        models_update = to_models(
            ModelerDraft(processes=draft.processes, entities=draft.entities), graph, project.files
        )
        kept_models = guarded(models_update.patch, graph, "modeler", [], models_update.dropped)
        try:
            graph = graph.apply(kept_models.patch, actor="agent").graph
            files = models_update.files
        except GraphError as exc:  # the models do not fit the graph: requirements only
            row.error = f"модели: {exc}"[:300]
            files = {}
        store.save(replace(project, graph=graph, files=project.files | files))
        row.turns = sum(t.role == "agent" for t in turns)
        row.end = "one-shot"
        row.requirements = sum(
            len(graph.nodes_of(kind)) for kind in ("BR", "UR", "FR", "NFR", "CON")
        )
        if keep is not None:
            target = keep / f"{scenario_id}-{character}-r{repeat}"
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(folder, target, ignore=shutil.ignore_patterns(".reqgraph"))
    return row
