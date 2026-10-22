"""Provider-neutral agent execution loop."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar
from uuid import uuid4

from pilota.errors import (
    AgentError,
    ConfigurationError,
    ModelLimitError,
    PermissionDenied,
    ToolError,
)
from pilota.models import (
    Execution,
    ExecutionStatus,
    FinalResult,
    Limits,
    ModelRequest,
    Observation,
    ToolCall,
    Usage,
)
from pilota.providers import Model
from pilota.resources import Resource
from pilota.resources.base import resource_tools
from pilota.results import ResultCodec
from pilota.tools import Tool, ToolContext, WorkspaceHandle
from pilota.tracing import TraceRecorder

T = TypeVar("T")


def run_agent(
    task: str,
    *,
    model: Model,
    returns: type[T],
    context: Mapping[str, Any] | None = None,
    resources: Mapping[str, Resource] | None = None,
    instructions: Sequence[str] | None = None,
    tools: Sequence[Tool] | None = None,
    workspace: WorkspaceHandle | None = None,
    limits: Limits | None = None,
) -> Execution[T]:
    execution_id = str(uuid4())
    recorder = TraceRecorder()
    codec = ResultCodec(returns)
    selected_limits = limits or Limits()
    selected_tools = (*tuple(tools or ()), *resource_tools(resources or {}))
    tool_registry = _build_tool_registry(selected_tools)
    observations: list[Observation] = []
    model_calls = 0
    tool_calls = 0
    workspace_snapshot = workspace.snapshot() if workspace is not None else {}

    recorder.record("execution.started", {"task": task})

    while model_calls < selected_limits.model_calls:
        request = ModelRequest(
            execution_id=execution_id,
            task=task,
            context=context or {},
            instructions=tuple(instructions or ()),
            tools=tuple(tool.spec for tool in selected_tools),
            result_schema=codec.schema(),
            observations=tuple(observations),
        )
        recorder.record("model.requested", {"call": model_calls + 1})
        action = model.respond(request)
        model_calls += 1

        if isinstance(action, FinalResult):
            value = codec.decode(action.value, execution_id=execution_id)
            recorder.record("result.produced")
            recorder.record("execution.completed")
            return Execution(
                id=execution_id,
                value=value,
                artifacts=tuple(
                    workspace.artifacts_since(workspace_snapshot) if workspace is not None else ()
                ),
                trace=recorder.snapshot(),
                usage=Usage(model_calls=model_calls, tool_calls=tool_calls),
                status=ExecutionStatus.SUCCEEDED,
            )

        if not isinstance(action, ToolCall):
            raise ConfigurationError(
                f"Model returned unsupported action: {type(action).__name__}",
                execution_id=execution_id,
            )

        if tool_calls >= selected_limits.tool_calls:
            raise ModelLimitError(
                f"Tool-call limit of {selected_limits.tool_calls} was exhausted",
                execution_id=execution_id,
            )

        tool = tool_registry.get(action.name)
        if tool is None:
            message = f"Tool is not available: {action.name}"
            recorder.record("tool.denied", {"tool": action.name, "reason": message})
            observations.append(
                Observation(
                    call_id=action.id,
                    tool_name=action.name,
                    error=message,
                )
            )
            continue

        recorder.record("tool.started", {"tool": action.name, "call_id": action.id})
        tool_calls += 1

        try:
            output = tool.invoke(
                action.arguments,
                ToolContext(execution_id=execution_id, workspace=workspace),
            )
        except PermissionDenied as error:
            recorder.record(
                "tool.denied",
                {"tool": action.name, "call_id": action.id, "error": str(error)},
            )
            observations.append(
                Observation(
                    call_id=action.id,
                    tool_name=action.name,
                    error=str(error),
                )
            )
        except AgentError as error:
            recorder.record(
                "tool.failed",
                {"tool": action.name, "call_id": action.id, "error": str(error)},
            )
            observations.append(
                Observation(
                    call_id=action.id,
                    tool_name=action.name,
                    error=str(error),
                )
            )
        except Exception as error:
            wrapped = ToolError(
                f"Tool {action.name!r} failed: {error}",
                execution_id=execution_id,
            )
            recorder.record(
                "tool.failed",
                {"tool": action.name, "call_id": action.id, "error": str(wrapped)},
            )
            observations.append(
                Observation(
                    call_id=action.id,
                    tool_name=action.name,
                    error=str(wrapped),
                )
            )
        else:
            recorder.record("tool.completed", {"tool": action.name, "call_id": action.id})
            observations.append(
                Observation(
                    call_id=action.id,
                    tool_name=action.name,
                    output=output,
                )
            )

    raise ModelLimitError(
        f"Model-call limit of {selected_limits.model_calls} was exhausted",
        execution_id=execution_id,
    )


def _build_tool_registry(tools: Sequence[Tool]) -> dict[str, Tool]:
    registry: dict[str, Tool] = {}
    for tool in tools:
        if tool.spec.name in registry:
            raise ConfigurationError(f"Duplicate tool name: {tool.spec.name}")
        registry[tool.spec.name] = tool
    return registry
