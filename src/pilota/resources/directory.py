"""Read-only or explicitly scoped directory resource."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any, Literal, TypeAlias

from pilota.errors import PermissionDenied, ToolError
from pilota.resources.base import ResourceOperation
from pilota.workspaces.base import normalize_relative_path

DirectoryOperation: TypeAlias = Literal["list", "read"]


class DirectoryResource:
    def __init__(
        self,
        root: str | Path,
        *,
        allow: Collection[DirectoryOperation] = ("list", "read"),
        deny_globs: Collection[str] = (),
    ) -> None:
        self.root = Path(root).resolve()
        self._allow = frozenset(allow)
        self._deny_globs = tuple(deny_globs)

    @property
    def operations(self) -> Mapping[str, ResourceOperation]:
        available: dict[str, ResourceOperation] = {}
        if "list" in self._allow:
            available["list"] = ResourceOperation(
                name="list",
                description="List files below a relative directory path.",
                input_schema={"path": {"type": "string"}},
            )
        if "read" in self._allow:
            available["read"] = ResourceOperation(
                name="read",
                description="Read a UTF-8 text file by relative path.",
                input_schema={"path": {"type": "string"}},
            )
        return available

    def invoke(self, operation: str, arguments: Mapping[str, Any]) -> Any:
        if operation not in self._allow:
            raise PermissionDenied(f"Directory operation is not allowed: {operation}")
        path = arguments.get("path", ".")
        if not isinstance(path, str):
            raise ToolError("Directory path must be a string")
        target = self._resolve(path)
        if operation == "list":
            if not target.exists():
                return []
            if target.is_file():
                return [str(target.relative_to(self.root))]
            return sorted(
                str(candidate.relative_to(self.root))
                for candidate in target.rglob("*")
                if candidate.is_file()
            )
        if operation == "read":
            return target.read_text()
        raise ToolError(f"Unsupported directory operation: {operation}")

    def _resolve(self, path: str) -> Path:
        relative = normalize_relative_path(path)
        if any(relative.match(pattern) for pattern in self._deny_globs):
            raise PermissionDenied(f"Directory path is denied: {relative}")
        target = (self.root / relative).resolve()
        if not target.is_relative_to(self.root):
            raise PermissionDenied(f"Path escapes the directory resource: {path}")
        return target
