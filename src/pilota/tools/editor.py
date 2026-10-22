"""Workspace-scoped file editor tool."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pilota.errors import ConfigurationError, ToolError
from pilota.models import ToolSpec
from pilota.tools.base import ToolContext


class Editor:
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="editor",
            description="List, read, or write files inside the configured workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "operation": {"enum": ["list", "read", "write"]},
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["operation"],
                "additionalProperties": False,
            },
        )

    def invoke(self, arguments: Mapping[str, Any], context: ToolContext) -> Any:
        if context.workspace is None:
            raise ConfigurationError("Editor requires a workspace")

        operation = arguments.get("operation")
        path = arguments.get("path", ".")
        if not isinstance(path, str):
            raise ToolError("Editor path must be a string")

        if operation == "list":
            return context.workspace.list_files(path)
        if operation == "read":
            return context.workspace.read_text(path)
        if operation == "write":
            content = arguments.get("content")
            if not isinstance(content, str):
                raise ToolError("Editor write requires string content")
            context.workspace.write_text(path, content)
            return {"path": path, "written": len(content)}
        raise ToolError(f"Unsupported editor operation: {operation!r}")
