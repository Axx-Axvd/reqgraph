"""Exported documents of a revision (T-505): the core exporters into a temporary folder, the
files to Storage, a row per file in public.exports. No LLM: an export costs nothing."""

import asyncio
import mimetypes
import tempfile
from pathlib import Path
from uuid import UUID

from reqgraph.graph.store.project import Project

from reqgraph_api.storage import Storage

TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".reqif": "application/xml",
    ".svg": "image/svg+xml",
}


async def _write(project: Project, out: Path, *, offline: bool) -> list[Path]:
    from reqgraph.exporters.reqif import write_reqif
    from reqgraph.exporters.srs import export_documents, exports_of

    wanted = exports_of(project)
    documents = [d for d in wanted if d != "reqif"]
    written: list[Path] = []
    if documents:
        written += await export_documents(
            project,
            out,
            documents,  # type: ignore[arg-type]
            ("md", "docx"),
            offline=offline,
        )
    if "reqif" in wanted:
        written.append(write_reqif(project, out))
    return written


def write_files(project: Project, out: Path, *, offline: bool) -> list[Path]:
    """Documents (md, docx), scheme pictures and ReqIF; pandoc and Kroki block, so this runs in
    a thread with its own event loop."""
    return asyncio.run(_write(project, out, offline=offline))


def file_format(path: Path) -> str:
    return path.suffix.lstrip(".").lower()


def content_type(path: Path) -> str:
    return (
        TYPES.get(path.suffix.lower())
        or mimetypes.guess_type(path.name)[0]
        or "application/octet-stream"
    )


async def export_revision(
    project: Project, project_id: UUID, rev: int, storage: Storage, *, offline: bool
) -> list[tuple[str, str]]:
    """Write and upload; returns (format, storage path) of every file."""
    with tempfile.TemporaryDirectory(prefix="reqgraph-export-") as tmp:
        out = Path(tmp)
        files = await asyncio.to_thread(write_files, project, out, offline=offline)
        stored: list[tuple[str, str]] = []
        for file in sorted(set(files)):
            path = f"{project_id}/{rev}/{file.relative_to(out).as_posix()}"
            await storage.upload(path, file.read_bytes(), content_type(file))
            stored.append((file_format(file), path))
    return stored
