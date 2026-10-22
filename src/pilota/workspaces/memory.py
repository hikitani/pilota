"""In-memory workspace for tests and ephemeral execution."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from pathlib import Path

from pilota.models import Artifact
from pilota.workspaces.base import Operation, WorkspacePolicy, normalize_relative_path


class InMemoryWorkspace:
    def __init__(
        self,
        files: Mapping[str, str] | None = None,
        *,
        allow: Collection[Operation] = ("list", "read", "create", "edit"),
        deny_globs: Collection[str] = (),
    ) -> None:
        self._files = {
            str(normalize_relative_path(path)): content for path, content in (files or {}).items()
        }
        self._policy = WorkspacePolicy(allow=allow, deny_globs=deny_globs)

    def list_files(self, path: str = ".") -> list[str]:
        self._policy.authorize("list", path)
        prefix = normalize_relative_path(path)
        if str(prefix) == ".":
            return sorted(self._files)
        return sorted(
            name for name in self._files if normalize_relative_path(name).is_relative_to(prefix)
        )

    def read_text(self, path: str) -> str:
        self._policy.authorize("read", path)
        normalized = str(normalize_relative_path(path))
        return self._files[normalized]

    def write_text(self, path: str, content: str) -> None:
        normalized = str(normalize_relative_path(path))
        operation: Operation = "edit" if normalized in self._files else "create"
        self._policy.authorize(operation, path)
        self._files[normalized] = content

    def snapshot(self) -> Mapping[str, str]:
        return dict(self._files)

    def artifacts_since(self, snapshot: Mapping[str, str]) -> list[Artifact]:
        artifacts: list[Artifact] = []
        before = dict(snapshot)
        for path, content in self._files.items():
            if path not in before:
                artifacts.append(Artifact(path=Path(path), operation="created"))
            elif before[path] != content:
                artifacts.append(Artifact(path=Path(path), operation="modified"))
        for path in before.keys() - self._files.keys():
            artifacts.append(Artifact(path=Path(path), operation="deleted"))
        return sorted(artifacts, key=lambda artifact: str(artifact.path))
