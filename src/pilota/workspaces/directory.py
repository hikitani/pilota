"""Directory-backed workspace with path confinement."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from hashlib import sha256
from pathlib import Path

from pilota.models import Artifact
from pilota.workspaces.base import Operation, WorkspacePolicy, normalize_relative_path


class DirectoryWorkspace:
    def __init__(
        self,
        root: str | Path,
        *,
        allow: Collection[Operation],
        deny_globs: Collection[str] = (),
    ) -> None:
        self.root = Path(root).resolve()
        self._policy = WorkspacePolicy(allow=allow, deny_globs=deny_globs)

    def list_files(self, path: str = ".") -> list[str]:
        self._policy.authorize("list", path)
        target = self._resolve(path)
        if not target.exists():
            return []
        if target.is_file():
            return [str(target.relative_to(self.root))]
        return sorted(
            str(candidate.relative_to(self.root))
            for candidate in target.rglob("*")
            if candidate.is_file()
        )

    def read_text(self, path: str) -> str:
        self._policy.authorize("read", path)
        return self._resolve(path).read_text()

    def write_text(self, path: str, content: str) -> None:
        target = self._resolve(path)
        operation: Operation = "edit" if target.exists() else "create"
        self._policy.authorize(operation, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def execution_directory(self, path: str = ".") -> Path:
        self._policy.authorize("execute", path)
        target = self._resolve(path)
        if not target.exists():
            raise ValueError(f"Workspace execution directory does not exist: {path}")
        if not target.is_dir():
            raise ValueError(f"Workspace execution path is not a directory: {path}")
        return target

    def snapshot(self) -> Mapping[str, str]:
        if not self.root.exists():
            return {}
        return {
            str(path.relative_to(self.root)): sha256(path.read_bytes()).hexdigest()
            for path in self.root.rglob("*")
            if path.is_file()
        }

    def artifacts_since(self, snapshot: Mapping[str, str]) -> list[Artifact]:
        current = self.snapshot()
        artifacts: list[Artifact] = []
        for path, digest in current.items():
            if path not in snapshot:
                artifacts.append(Artifact(path=Path(path), operation="created"))
            elif snapshot[path] != digest:
                artifacts.append(Artifact(path=Path(path), operation="modified"))
        for path in snapshot.keys() - current.keys():
            artifacts.append(Artifact(path=Path(path), operation="deleted"))
        return sorted(artifacts, key=lambda artifact: str(artifact.path))

    def _resolve(self, path: str) -> Path:
        relative = normalize_relative_path(path)
        target = (self.root / relative).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError(f"Path escapes the workspace: {path}")
        return target
