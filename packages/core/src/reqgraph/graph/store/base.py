"""ProjectStore: where a project lives. FileStore — a folder (CLI, tests, git); Supabase — later."""

from typing import Protocol

from reqgraph.graph.store.project import Project


class ProjectStore(Protocol):
    def load(self) -> Project: ...

    def save(self, project: Project) -> object: ...
