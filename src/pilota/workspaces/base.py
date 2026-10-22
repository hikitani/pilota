"""Workspace authorization and path handling."""

from __future__ import annotations

from collections.abc import Collection
from pathlib import PurePosixPath
from typing import Literal, TypeAlias

from pilota.errors import PermissionDenied

Operation: TypeAlias = Literal["list", "read", "create", "edit", "delete", "execute"]


class WorkspacePolicy:
    def __init__(
        self,
        *,
        allow: Collection[Operation],
        deny_globs: Collection[str] = (),
    ) -> None:
        self.allow = frozenset(allow)
        self.deny_globs = tuple(deny_globs)

    def authorize(self, operation: Operation, path: str) -> None:
        normalized = normalize_relative_path(path)
        if operation not in self.allow:
            raise PermissionDenied(f"Workspace operation is not allowed: {operation}")
        if any(normalized.match(pattern) for pattern in self.deny_globs):
            raise PermissionDenied(f"Workspace path is denied: {normalized}")


def normalize_relative_path(path: str) -> PurePosixPath:
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PermissionDenied(f"Path escapes the workspace: {path}")
    if str(candidate) in {"", "."}:
        return PurePosixPath(".")
    return candidate
