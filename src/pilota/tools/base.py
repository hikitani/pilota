"""Tool contracts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pilota.models import ToolSpec


class WorkspaceHandle(Protocol):
    def read_text(self, path: str) -> str: ...

    def write_text(self, path: str, content: str) -> None: ...

    def list_files(self, path: str = ".") -> list[str]: ...

    def snapshot(self) -> Mapping[str, str]: ...

    def artifacts_since(self, snapshot: Mapping[str, str]) -> list[Any]: ...


@runtime_checkable
class ProcessWorkspaceHandle(Protocol):
    def execution_directory(self, path: str = ".") -> Path: ...


@dataclass(frozen=True)
class ToolContext:
    """Execution details and tracing access provided to tools."""

    execution_id: str
    workspace: WorkspaceHandle | None
    record: Callable[[str, Mapping[str, Any]], None] = field(
        default=lambda kind, data: None,
        repr=False,
        compare=False,
    )


class Tool(Protocol):
    @property
    def spec(self) -> ToolSpec: ...

    def invoke(self, arguments: Mapping[str, Any], context: ToolContext) -> Any: ...
