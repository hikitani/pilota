"""Provider-neutral execution types."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar

T = TypeVar("T")


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Limits:
    model_calls: int = 30
    tool_calls: int = 100
    wall_time: timedelta | None = None

    def __post_init__(self) -> None:
        if self.wall_time is not None:
            if not isinstance(self.wall_time, timedelta):
                raise TypeError("wall_time must be a datetime.timedelta")
            if self.wall_time <= timedelta(0):
                raise ValueError("wall_time must be greater than zero")
        if self.model_calls < 1:
            raise ValueError("model_calls must be at least 1")
        if self.tool_calls < 0:
            raise ValueError("tool_calls cannot be negative")


@dataclass(frozen=True)
class Artifact:
    path: Path
    operation: Literal["created", "modified", "deleted"]


@dataclass(frozen=True)
class Usage:
    model_calls: int = 0
    tool_calls: int = 0


@dataclass(frozen=True)
class TraceEvent:
    kind: str
    data: Mapping[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class Trace:
    events: tuple[TraceEvent, ...]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Mapping[str, Any]


@dataclass(frozen=True)
class Observation:
    call_id: str
    tool_name: str
    output: Any | None = None
    error: str | None = None


@dataclass(frozen=True)
class ModelRequest:
    execution_id: str
    task: str
    context: Mapping[str, Any]
    instructions: Sequence[str]
    tools: Sequence[ToolSpec]
    result_schema: Mapping[str, Any]
    tool_calls: Sequence[ToolCall]
    observations: Sequence[Observation]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: Mapping[str, Any]
    provider_data: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True)
class FinalResult:
    value: Any


ModelAction = ToolCall | FinalResult


@dataclass(frozen=True)
class Execution(Generic[T]):
    id: str
    value: T
    artifacts: tuple[Artifact, ...]
    trace: Trace
    usage: Usage
    status: ExecutionStatus = ExecutionStatus.SUCCEEDED
