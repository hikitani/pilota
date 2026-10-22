"""Structured Pilota errors."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pilota.models import Trace


class AgentError(Exception):
    """Base class for execution failures."""

    def __init__(
        self,
        message: str,
        *,
        execution_id: str | None = None,
        artifacts: Sequence[str] = (),
        trace: Trace | None = None,
    ) -> None:
        super().__init__(message)
        self.execution_id = execution_id
        self.artifacts = tuple(artifacts)
        self.trace = trace


class ConfigurationError(AgentError):
    """The requested execution cannot be configured safely."""


class ProviderError(AgentError):
    """A model provider failed."""


class ModelLimitError(AgentError):
    """An execution exhausted a model or tool-call limit."""


class ToolError(AgentError):
    """A tool failed while executing."""


class ToolTimeoutError(ToolError):
    """A tool exceeded its configured timeout."""


class PermissionDenied(AgentError):
    """A requested operation was outside the granted authority."""


class ResultContractError(AgentError):
    """A final model result did not satisfy the requested Python type."""


class ExecutionCancelled(AgentError):
    """The caller cancelled execution."""
