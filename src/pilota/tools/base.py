"""Tool contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from pilota.models import ToolSpec


class WorkspaceHandle(Protocol):
    def read_text(self, path: str) -> str: ...

    def write_text(self, path: str, content: str) -> None: ...

    def list_files(self, path: str = ".") -> list[str]: ...

    def snapshot(self) -> Mapping[str, str]: ...

    def artifacts_since(self, snapshot: Mapping[str, str]) -> list[Any]: ...


@dataclass(frozen=True)
class ToolContext:
    execution_id: str
    workspace: WorkspaceHandle | None


class Tool(Protocol):
    @property
    def spec(self) -> ToolSpec: ...

    def invoke(self, arguments: Mapping[str, Any], context: ToolContext) -> Any: ...
