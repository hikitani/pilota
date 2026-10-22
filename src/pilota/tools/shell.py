"""Workspace-scoped local command execution."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any

from pilota.errors import ConfigurationError, ToolError, ToolTimeoutError
from pilota.models import ToolSpec
from pilota.tools.base import ProcessWorkspaceHandle, ToolContext


class Shell:
    """Execute explicitly configured command aliases inside a workspace."""

    def __init__(
        self,
        commands: Mapping[str, Sequence[str]],
        *,
        timeout: float = 30.0,
        max_output_chars: int = 20_000,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if max_output_chars < 1:
            raise ValueError("max_output_chars must be at least one")

        self._commands = _validate_commands(commands)
        self._timeout = timeout
        self._max_output_chars = max_output_chars
        self._environment = {
            "PATH": os.defpath,
            **_validate_environment(environment or {}),
        }

    @property
    def spec(self) -> ToolSpec:
        aliases = sorted(self._commands)
        return ToolSpec(
            name="shell",
            description=(
                "Run one configured command inside the workspace. "
                f"Available commands: {', '.join(aliases)}."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "enum": aliases},
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "cwd": {"type": "string"},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        )

    def invoke(self, arguments: Mapping[str, Any], context: ToolContext) -> Any:
        if context.workspace is None:
            raise ConfigurationError("Shell requires a workspace")
        if not isinstance(context.workspace, ProcessWorkspaceHandle):
            raise ConfigurationError(
                "Shell requires a process-backed workspace",
                execution_id=context.execution_id,
            )

        alias = arguments.get("command")
        if not isinstance(alias, str):
            raise ToolError("Shell command must be a string")
        command = self._commands.get(alias)
        if command is None:
            raise ToolError(f"Shell command is not allowed: {alias}")

        raw_args = arguments.get("args", [])
        if not isinstance(raw_args, list) or not all(isinstance(item, str) for item in raw_args):
            raise ToolError("Shell args must be a list of strings")
        if any("\0" in item for item in raw_args):
            raise ToolError("Shell args must not contain null bytes")

        cwd = arguments.get("cwd", ".")
        if not isinstance(cwd, str):
            raise ToolError("Shell cwd must be a string")

        try:
            execution_directory = context.workspace.execution_directory(cwd)
        except (OSError, ValueError) as error:
            raise ToolError(str(error), execution_id=context.execution_id) from error

        try:
            completed = subprocess.run(
                (*command, *raw_args),
                cwd=execution_directory,
                env=self._environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as error:
            raise ToolTimeoutError(
                f"Shell command {alias!r} exceeded its {self._timeout:g}s timeout",
                execution_id=context.execution_id,
            ) from error
        except OSError as error:
            raise ToolError(
                f"Shell command {alias!r} could not start: {error}",
                execution_id=context.execution_id,
            ) from error

        stdout, stdout_truncated = _decode_output(
            completed.stdout,
            max_chars=self._max_output_chars,
        )
        stderr, stderr_truncated = _decode_output(
            completed.stderr,
            max_chars=self._max_output_chars,
        )
        return {
            "command": alias,
            "exit_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }


def _validate_commands(commands: Mapping[str, Sequence[str]]) -> dict[str, tuple[str, ...]]:
    if not commands:
        raise ValueError("commands must contain at least one alias")

    validated: dict[str, tuple[str, ...]] = {}
    for alias, command in commands.items():
        if not isinstance(alias, str) or not alias or "\0" in alias:
            raise ValueError("command aliases must be non-empty and contain no null bytes")
        if (
            isinstance(command, (str, bytes))
            or not command
            or not all(isinstance(item, str) and item for item in command)
        ):
            raise ValueError(f"Command {alias!r} must contain non-empty string arguments")
        if any("\0" in item for item in command):
            raise ValueError(f"Command {alias!r} must not contain null bytes")
        validated[alias] = tuple(command)
    return validated


def _validate_environment(environment: Mapping[str, str]) -> dict[str, str]:
    validated: dict[str, str] = {}
    for name, value in environment.items():
        if (
            not isinstance(name, str)
            or not isinstance(value, str)
            or not name
            or "=" in name
            or "\0" in name
            or "\0" in value
        ):
            raise ValueError(f"Invalid environment variable: {name!r}")
        validated[name] = value
    return validated


def _decode_output(value: bytes, *, max_chars: int) -> tuple[str, bool]:
    decoded = value.decode(errors="replace")
    if len(decoded) <= max_chars:
        return decoded, False
    return decoded[:max_chars], True
