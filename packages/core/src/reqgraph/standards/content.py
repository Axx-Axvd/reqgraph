"""Sections built by code from the graph (T-204, T-401, T-408): lists of nodes with their ids, the
system features, NFR by characteristic, interfaces, models, open issues, acceptance criteria,
assumptions and the traceability table. The Standards agent, TPL-001 and the exporters share it,
so a section reads the same in the run, in the check and in the document."""

from reqgraph.graph.edges import Rel
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import (
    C4Node,
    EntityNode,
    FunctionalReq,
    Node,
    NonFunctionalReq,
    UserReq,
)
from reqgraph.standards import Section

PRIORITY = {"must": "обязательно", "should": "желательно", "could": "можно", "wont": "не сейчас"}
_REQUIREMENTS = ("BR", "UR", "FR", "NFR", "CON")


def line(node: Node) -> str:
    title = getattr(node, "title", None) or getattr(node, "name", "")
    text = getattr(node, "statement", None) or getattr(node, "description", None) or ""
    return f"- {node.id} {title}" + (f": {text}" if text else "")


def _targets(graph: ArtifactGraph, src: str, rel: Rel) -> list[str]:
    return sorted(e.dst for e in graph.edges if e.src == src and e.rel is rel)


def _sources(graph: ArtifactGraph, dst: str, rel: Rel) -> list[str]:
    return sorted(e.src for e in graph.edges if e.dst == dst and e.rel is rel)


def _features(section: Section, graph: ArtifactGraph) -> tuple[str, list[str]]:
    """A feature is a user requirement: its statement and priority, its scenario as the stimulus /
    response sequence, the FRs refining it. FRs refining no UR close the list."""
    blocks: list[str] = []
    refs: list[str] = []
    heading = "#" * (section.level + 1)
    frs = [n for n in graph.nodes_of("FR") if isinstance(n, FunctionalReq)]
    placed: set[str] = set()
    urs = [n for n in graph.nodes_of("UR") if isinstance(n, UserReq)]
    for number, ur in enumerate(urs, 1):
        own = [fr for fr in frs if ur.id in _targets(graph, fr.id, Rel.REFINES)]
        placed |= {fr.id for fr in own}
        actor = graph.get(ur.actor) if ur.actor else None
        priority = PRIORITY.get(ur.priority or "", "не задан")
        about = f"{ur.statement} Приоритет: {priority}."
        if actor is not None:
            about += f" Роль: {actor.id} {getattr(actor, 'name', '')}."
        steps = "\n".join(f"{i}. {step}" for i, step in enumerate(ur.scenario, 1)) or "Не описана."
        listed = "\n".join(line(fr) for fr in own) or "Функциональных требований пока нет."
        blocks.append(
            f"{heading} {section.number}.{number} {ur.title} ({ur.id})\n\n"
            f"**Описание и приоритет.** {about}\n\n"
            f"**Последовательность «стимул — отклик».**\n\n{steps}\n\n"
            f"**Функциональные требования.**\n\n{listed}"
        )
        refs += [ur.id, *(fr.id for fr in own)]
    rest = [fr for fr in frs if fr.id not in placed]
    if rest:
        number = len(urs) + 1
        blocks.append(
            f"{heading} {section.number}.{number} Прочие функции\n\n"
            + "\n".join(line(fr) for fr in rest)
        )
        refs += [fr.id for fr in rest]
    return "\n\n".join(blocks), refs


def _interfaces(graph: ArtifactGraph) -> tuple[str, list[str]]:
    nodes: list[Node] = [
        n for kind in _REQUIREMENTS for n in graph.nodes_of(kind) if n.area == "integrations"
    ]
    lines = [line(n) for n in nodes]
    for node in graph.nodes_of("C4"):
        if isinstance(node, C4Node) and node.c4_kind == "external":
            tech = f" ({node.technology})" if node.technology else ""
            lines.append(f"- {node.id} {node.name}: внешняя система{tech}")
            nodes.append(node)
    return "\n".join(lines), [n.id for n in nodes]


def _entity(node: EntityNode) -> str:
    fields = ", ".join(a.name for a in node.attributes)
    return f"- {node.id} {node.name}" + (f": {fields}" if fields else "")


def _models(graph: ArtifactGraph) -> tuple[str, list[str]]:
    entities = [n for n in graph.nodes_of("ENT") if isinstance(n, EntityNode)]
    processes = graph.nodes_of("PRC")
    parts = []
    if entities:
        parts.append("**Сущности данных.**\n\n" + "\n".join(_entity(n) for n in entities))
    if processes:
        parts.append("**Бизнес-процессы.**\n\n" + "\n".join(line(n) for n in processes))
    return "\n\n".join(parts), [n.id for n in [*entities, *processes]]


def _issues(graph: ArtifactGraph) -> tuple[str, list[str]]:
    lines, refs = [], []
    pairs = sorted(
        {tuple(sorted((e.src, e.dst))) for e in graph.edges if e.rel is Rel.CONFLICTS_WITH}
    )
    for a, b in pairs:
        lines.append(f"- {a} ↔ {b}: требования противоречат друг другу — согласовать с заказчиком")
        refs += [a, b]
    for node in graph.nodes.values():
        if node.assumption and node.id not in refs:
            title = getattr(node, "title", None) or getattr(node, "name", "")
            lines.append(f"- {node.id} {title}: допущение аналитика — подтвердить у заказчика")
            refs.append(node.id)
    return "\n".join(lines), refs


def trace_rows(graph: ArtifactGraph) -> list[tuple[str, str, list[str], list[str], list[str]]]:
    """Every FR with the UR it refines, the BR above those, the model elements realizing it."""
    rows = []
    for node in graph.nodes_of("FR"):
        assert isinstance(node, FunctionalReq)
        urs = _targets(graph, node.id, Rel.REFINES)
        brs = sorted({br for ur in urs for br in _targets(graph, ur, Rel.REFINES)})
        models = _targets(graph, node.id, Rel.REALIZED_BY)
        rows.append((node.id, node.title, urs, brs, models))
    return rows


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _trace(graph: ArtifactGraph) -> tuple[str, list[str]]:
    rows = trace_rows(graph)
    if not rows:
        return "", []
    lines = [
        "| ФТ | Пользовательские требования | Бизнес-цели | Реализовано в моделях |",
        "|---|---|---|---|",
    ]
    for fr, title, urs, brs, models in rows:
        cells = [", ".join(x) or "—" for x in (urs, brs, models)]
        lines.append(f"| {fr} {_cell(title)} | " + " | ".join(cells) + " |")
    return "\n".join(lines), [r[0] for r in rows]


def code_content(section: Section, graph: ArtifactGraph) -> tuple[str, list[str]] | None:
    """Text and node refs of a section the code builds; None for a heading or an LLM section."""
    if section.fill == "none" or section.llm_field is not None:
        return None
    if section.fill == "features":
        return _features(section, graph)
    if section.fill == "interfaces":
        return _interfaces(graph)
    if section.fill == "models":
        return _models(graph)
    if section.fill == "issues":
        return _issues(graph)
    if section.fill == "trace":
        return _trace(graph)
    if section.fill == "acceptance":
        checked = [n for n in graph.nodes_of("FR") if isinstance(n, FunctionalReq) and n.acceptance]
        lines = [f"- {n.id}: " + "; ".join(n.acceptance) for n in checked]
        return "\n".join(lines), [n.id for n in checked]
    if section.fill == "assumptions":
        nodes: list[Node] = [n for n in graph.nodes.values() if n.assumption]
    elif section.characteristics:
        nodes = [
            n
            for n in graph.nodes_of("NFR")
            if isinstance(n, NonFunctionalReq) and n.iso25010 in section.characteristics
        ]
    else:
        nodes = [n for kind in section.node_kinds for n in graph.nodes_of(kind)]
    return "\n".join(line(n) for n in nodes), [n.id for n in nodes]
