"""FileStore: a project folder (docs-as-code, examples/garage61) <-> Project.

Reading collects the graph from requirements/*.yaml, the interview transcript, process DSL files
and the diagram files; writing puts it back. A file whose content did not change is written back
byte for byte (comments and hand formatting survive); a changed file gets the canonical text.
"""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from reqgraph.graph.edges import Edge
from reqgraph.graph.errors import GraphError
from reqgraph.graph.graph import ArtifactGraph
from reqgraph.graph.nodes import Node, NodeKind, ProcessNode
from reqgraph.graph.store import formats as fmt
from reqgraph.graph.store.errors import StoreError
from reqgraph.graph.store.project import Project
from reqgraph.graph.store.scan import scan_c4, scan_dbml, scan_puml

# Diagram texts kept in the project; other files under models/ (images and the like) are not ours.
MODEL_SUFFIXES = frozenset({".dbml", ".puml", ".dsl", ".bpmn", ".svg"})
Reader = Callable[[str, str], Sequence[Node]]
# Simple scanner of the diagram files; entry points pass the parsers of dsl/ instead
# (`FileStore(root, readers=reqgraph.dsl.readers.model_readers())`).
DEFAULT_READERS: dict[str, Reader] = {".dbml": scan_dbml, ".puml": scan_puml, ".dsl": scan_c4}
DIAGRAM_KINDS = (NodeKind.ENT, NodeKind.UC, NodeKind.C4)


def _is_model_file(rel: str) -> bool:
    return rel.startswith("models/") and Path(rel).suffix in MODEL_SUFFIXES


class FileStore:
    """Project store in a folder. Paths inside the project are POSIX and relative to `root`."""

    def __init__(self, root: Path | str, readers: Mapping[str, Reader] | None = None) -> None:
        self.root = Path(root)
        self.readers = dict(DEFAULT_READERS if readers is None else readers)

    def _scan(self, rel: str, text: str) -> list[Node]:
        """Nodes of a diagram file by its suffix; a parse error names the file."""
        reader = self.readers.get(Path(rel).suffix)
        if reader is None:
            return []
        try:
            return list(reader(text, rel))
        except GraphError:
            raise
        except ValueError as exc:  # DslError of dsl/ and the like
            raise StoreError(str(exc)) from None

    # --- reading ---------------------------------------------------------------------------

    def _read(self, rel: str) -> str | None:
        path = self.root / rel
        if not path.is_file():
            return None
        try:
            return path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            raise StoreError(f"{rel}: файл не в кодировке UTF-8") from None

    def _files_under(self, folder: str) -> list[str]:
        base = self.root / folder
        if not base.is_dir():
            return []
        return sorted(p.relative_to(self.root).as_posix() for p in base.rglob("*") if p.is_file())

    def load(self) -> Project:
        files: dict[str, str] = {}
        layout: dict[str, str] = {}
        found: list[tuple[Node, str]] = []
        edges: list[Edge] = []

        def read(rel: str) -> str | None:
            text = self._read(rel)
            if text is not None:
                files[rel] = text
            return text

        config_text = read(fmt.CONFIG_FILE)
        if config_text is None:
            raise StoreError(f"в папке {self.root} нет файла reqgraph.yaml — это не папка проекта")
        config = fmt.parse_config(config_text)
        read(fmt.BRIEF_FILE)
        for kind, rel in fmt.REQUIREMENT_FILES.items():
            text = read(rel)
            if text is not None:
                nodes, kept = fmt.parse_requirements(kind, text, rel)
                found += [(n, rel) for n in nodes]
                edges += kept
        text = read(fmt.TRANSCRIPT_FILE)
        if text is not None:
            found += [(n, fmt.TRANSCRIPT_FILE) for n in fmt.parse_transcript(text)]
        for rel in self._files_under("models"):
            if not (rel.endswith(fmt.PROCESS_SUFFIX) or _is_model_file(rel)):
                continue
            text = read(rel)
            assert text is not None
            if rel.endswith(fmt.PROCESS_SUFFIX):
                process = fmt.parse_process(text, rel)
                bpmn = rel.removesuffix(fmt.PROCESS_SUFFIX) + ".bpmn"
                if (self.root / bpmn).is_file():
                    process = process.model_copy(update={"bpmn_path": bpmn})
                scanned: list[Node] = [process]
            else:
                scanned = self._scan(rel, text)
            for node in scanned:
                found.append((node, rel))
                layout[node.id] = rel
        trace = read(fmt.EDGES_FILE)
        ids_text = read(fmt.IDS_FILE)
        high_water = fmt.parse_ids(ids_text) if ids_text is not None else {}

        origin: dict[str, str] = {}
        for node, rel in found:
            if node.id in origin:
                raise StoreError(f"узел {node.id} повторяется: {origin[node.id]} и {rel}")
            origin[node.id] = rel
        try:
            graph = ArtifactGraph.from_parts([n for n, _ in found], edges, high_water)
        except StoreError:
            raise
        except GraphError as exc:
            raise StoreError(f"проект {self.root.name}: {exc}") from None

        warnings = []
        if trace is not None:
            expected, listed = fmt.stored_edges(graph), fmt.parse_edges(trace)
            if listed != expected:
                warnings.append(
                    f"{fmt.EDGES_FILE} не совпадает с requirements/*.yaml (лишних "
                    f"{len(listed - expected)}, недостающих {len(expected - listed)}): "
                    "файл сгенерированный, он будет пересоздан при записи"
                )
        return Project(self.root, config, graph, files, layout, warnings)

    # --- writing ---------------------------------------------------------------------------

    def save(self, project: Project) -> list[Path]:
        """Write the project into `root`; returns the paths of all files the project owns."""
        graph, files = project.graph, project.files
        self._refuse_unwritable_changes(project)
        texts: dict[str, str] = {}

        def keep_or(rel: str, unchanged: bool, render: str) -> None:
            texts[rel] = files[rel] if rel in files and unchanged else render

        config_raw = files.get(fmt.CONFIG_FILE)
        same_config = config_raw is not None and fmt.parse_config(config_raw) == project.config
        keep_or(fmt.CONFIG_FILE, same_config, fmt.render_config(project.config))
        for rel, text in files.items():
            if rel == fmt.BRIEF_FILE or _is_model_file(rel):
                texts[rel] = text

        stored = fmt.stored_edges(graph)
        for kind, rel in fmt.REQUIREMENT_FILES.items():
            nodes = {n.id: n for n in graph.nodes_of(kind)}
            if not nodes and rel not in files:
                continue
            owned = {e for e in stored if e.src in nodes}
            same = False
            if rel in files:
                old_nodes, old_edges = fmt.parse_requirements(kind, files[rel], rel)
                same = {n.id: n for n in old_nodes} == nodes and set(old_edges) == owned
            keep_or(rel, same, fmt.render_requirements(kind, graph))

        turns = graph.nodes_of(NodeKind.TURN)
        if turns or fmt.TRANSCRIPT_FILE in files:
            raw = files.get(fmt.TRANSCRIPT_FILE)
            same = raw is not None and fmt.parse_transcript(raw) == turns
            keep_or(fmt.TRANSCRIPT_FILE, same, fmt.render_transcript(graph))

        for node in graph.nodes_of(NodeKind.PRC):
            assert isinstance(node, ProcessNode)
            rel = project.layout.get(node.id, fmt.process_path(node.id))
            raw = files.get(rel)
            old = fmt.parse_process(raw, rel) if raw is not None else None
            same = old is not None and (old.dsl, old.name) == (node.dsl, node.name)
            keep_or(rel, same, fmt.render_process(node))

        raw = files.get(fmt.EDGES_FILE)
        keep_or(
            fmt.EDGES_FILE,
            raw is not None and fmt.parse_edges(raw) == stored,
            fmt.render_edges(graph),
        )

        from_nodes = ArtifactGraph.from_parts(graph.nodes.values(), graph.edges).high_water
        needed = any(v > from_nodes.get(k, 0) for k, v in graph.high_water.items())
        if needed or fmt.IDS_FILE in files:
            raw = files.get(fmt.IDS_FILE)
            same = raw is not None and fmt.parse_ids(raw) == graph.high_water
            keep_or(fmt.IDS_FILE, same, fmt.render_ids(graph.high_water))

        written = [self._write(rel, text) for rel, text in sorted(texts.items())]
        self._remove_stale_processes(project, texts)
        return written

    def _write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        data = text.encode("utf-8")
        if not path.is_file() or path.read_bytes() != data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return path

    def _remove_stale_processes(self, project: Project, texts: dict[str, str]) -> None:
        """A removed process must not come back on the next load: delete its DSL file."""
        for node_id, rel in project.layout.items():
            removed = node_id not in project.graph.nodes and rel not in texts
            if removed and rel.endswith(fmt.PROCESS_SUFFIX):
                (self.root / rel).unlink(missing_ok=True)

    def _refuse_unwritable_changes(self, project: Project) -> None:
        """Diagram files are text written by people and the Modeler, never generated from the
        graph: a change of an ENT, UC or C4 node that is not in its file would be lost."""
        scanned: dict[str, Node] = {}
        for rel, text in project.files.items():
            if _is_model_file(rel):
                scanned |= {n.id: n for n in self._scan(rel, text)}
        in_graph = {n.id: n for kind in DIAGRAM_KINDS for n in project.graph.nodes_of(kind)}
        differ = sorted(
            i for i in scanned.keys() | in_graph.keys() if scanned.get(i) != in_graph.get(i)
        )
        if differ:
            raise StoreError(
                f"узлы {', '.join(differ)} изменены в графе, но не в файлах диаграмм: модели "
                "данных, сценариев и C4 меняются правкой самих файлов (DBML, PlantUML, Structurizr)"
            )
