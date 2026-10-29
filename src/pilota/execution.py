"""Provider-neutral agent execution loop."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from threading import Event
from time import monotonic
from typing import Any, Never, TypeVar
from uuid import uuid4

from pilota.errors import (
    AgentError,
    ConfigurationError,
    ExecutionCancelled,
    MalformedToolCall,
    ModelLimitError,
    PermissionDenied,
    ResultContractError,
    ToolError,
)
from pilota.instructions import InstructionInput, render_instructions
from pilota.models import (
    RESULT_TOOL_NAME,
    Artifact,
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
from pilota.tracing import ProgressCallback, TraceRecorder

T = TypeVar("T")


def run_agent(
    task: str,
    *,
    model: Model,
    returns: type[T],
    context: Mapping[str, Any] | None = None,
    resources: Mapping[str, Resource] | None = None,
    instructions: Sequence[InstructionInput] | None = None,
    tools: Sequence[Tool] | None = None,
    workspace: WorkspaceHandle | None = None,
    limits: Limits | None = None,
    cancel_event: Event | None = None,
    progress: ProgressCallback | None = None,
) -> Execution[T]:
    execution_id = str(uuid4())
    recorder = TraceRecorder(progress)
    selected_limits = limits or Limits()
    deadline = (
        monotonic() + selected_limits.wall_time.total_seconds()
        if selected_limits.wall_time is not None
        else None
    )
    codec = ResultCodec(returns)
    rendered_instructions = render_instructions(
        tuple(instructions or ()),
        execution_id=execution_id,
    )
    selected_tools = (*tuple(tools or ()), *resource_tools(resources or {}))
    tool_registry = _build_tool_registry(selected_tools)
    tool_call_history: list[ToolCall] = []
    observations: list[Observation] = []
    model_calls = 0
    tool_calls = 0
    result_rejections = 0
    workspace_snapshot = workspace.snapshot() if workspace is not None else {}

    recorder.record("execution.started", {"task": task})

    def reject_result(attempt: FinalResult, error: ResultContractError) -> None:
        nonlocal result_rejections
        recorder.record("result.rejected", {"error": str(error)})
        if result_rejections >= selected_limits.result_retries:
            artifacts = _current_artifacts(workspace, workspace_snapshot)
            _record_artifacts(recorder, artifacts)
            recorder.record("execution.limit_exhausted", {"limit": "result_retries"})
            raise ResultContractError(
                str(error),
                execution_id=execution_id,
                artifacts=tuple(str(artifact.path) for artifact in artifacts),
                trace=recorder.snapshot(),
            ) from error
        result_rejections += 1
        call_id = attempt.id or str(uuid4())
        tool_call_history.append(
            ToolCall(call_id, RESULT_TOOL_NAME, attempt.value, attempt.provider_data)
        )
        observations.append(Observation(call_id, RESULT_TOOL_NAME, error=str(error)))

    while model_calls < selected_limits.model_calls:
        _check_execution_boundary(
            execution_id=execution_id,
            boundary="before_model",
            cancel_event=cancel_event,
            deadline=deadline,
            recorder=recorder,
            workspace=workspace,
            workspace_snapshot=workspace_snapshot,
        )
        request = ModelRequest(
            execution_id=execution_id,
            task=task,
            context=context or {},
            instructions=rendered_instructions,
            tools=tuple(tool.spec for tool in selected_tools),
            result_schema=codec.schema(),
            tool_calls=tuple(tool_call_history),
            observations=tuple(observations),
        )
        recorder.record("model.requested", {"call": model_calls + 1})
        try:
            action = model.respond(request)
        except MalformedToolCall as error:
            model_calls += 1
            _check_execution_boundary(
                execution_id=execution_id,
                boundary="after_model",
                cancel_event=cancel_event,
                deadline=deadline,
                recorder=recorder,
                workspace=workspace,
                workspace_snapshot=workspace_snapshot,
            )
            if error.tool_name == RESULT_TOOL_NAME:
                reject_result(FinalResult({}, error.call_id), ResultContractError(str(error)))
            else:
                recorder.record(
                    "tool.failed",
                    {"tool": error.tool_name, "call_id": error.call_id, "error": str(error)},
                )
                tool_call_history.append(ToolCall(error.call_id, error.tool_name, {}))
                observations.append(Observation(error.call_id, error.tool_name, error=str(error)))
            continue
        except AgentError as error:
            recorder.record("model.failed", {"error": str(error)})
            try:
                _check_execution_boundary(
                    execution_id=execution_id,
                    boundary="after_model",
                    cancel_event=cancel_event,
                    deadline=deadline,
                    recorder=recorder,
                    workspace=workspace,
                    workspace_snapshot=workspace_snapshot,
                )
            except AgentError as boundary_error:
                raise boundary_error from error
            artifacts = _current_artifacts(workspace, workspace_snapshot)
            _record_artifacts(recorder, artifacts)
            error.execution_id = execution_id
            error.artifacts = tuple(str(artifact.path) for artifact in artifacts)
            error.trace = recorder.snapshot()
            raise
        recorder.record("model.responded", {"call": model_calls + 1})
        model_calls += 1
        _check_execution_boundary(
            execution_id=execution_id,
            boundary="after_model",
            cancel_event=cancel_event,
            deadline=deadline,
            recorder=recorder,
            workspace=workspace,
            workspace_snapshot=workspace_snapshot,
        )

        if isinstance(action, tuple) and (
            not action or not all(isinstance(call, ToolCall) for call in action)
        ):
            raise ConfigurationError(
                "Model returned an invalid tool-call batch", execution_id=execution_id
            )
        if isinstance(action, tuple) and len(action) == 1:
            action = action[0]
        if isinstance(action, ToolCall) and action.name == RESULT_TOOL_NAME:
            action = FinalResult(action.arguments, action.id, action.provider_data)

        if isinstance(action, FinalResult):
            try:
                value = codec.decode(action.value, execution_id=execution_id)
            except ResultContractError as error:
                reject_result(action, error)
                continue
            _check_execution_boundary(
                execution_id=execution_id,
                boundary="after_result_validation",
                cancel_event=cancel_event,
                deadline=deadline,
                recorder=recorder,
                workspace=workspace,
                workspace_snapshot=workspace_snapshot,
            )
            artifacts = _current_artifacts(workspace, workspace_snapshot)
            recorder.record("result.produced")
            _record_artifacts(recorder, artifacts)
            recorder.record("execution.completed")
            return Execution(
                id=execution_id,
                value=value,
                artifacts=artifacts,
                trace=recorder.snapshot(),
                usage=Usage(model_calls=model_calls, tool_calls=tool_calls),
                status=ExecutionStatus.SUCCEEDED,
            )

        if not isinstance(action, (ToolCall, tuple)):
            raise ConfigurationError(
                f"Model returned unsupported action: {type(action).__name__}",
                execution_id=execution_id,
            )

        batch = action if isinstance(action, tuple) else (action,)
        for action in (
            *[call for call in batch if call.name != RESULT_TOOL_NAME],
            *[call for call in batch if call.name == RESULT_TOOL_NAME],
        ):
            if action.name == RESULT_TOOL_NAME:
                reject_result(
                    FinalResult(action.arguments, action.id, action.provider_data),
                    ResultContractError(
                        "Call final_result alone, not together with other tool calls."
                    ),
                )
                continue
            tool_call_history.append(action)

            if tool_calls >= selected_limits.tool_calls:
                _raise_limit_error(
                    f"Tool-call limit of {selected_limits.tool_calls} was exhausted",
                    execution_id=execution_id,
                    limit="tool_calls",
                    recorder=recorder,
                    workspace=workspace,
                    workspace_snapshot=workspace_snapshot,
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

            _check_execution_boundary(
                execution_id=execution_id,
                boundary="before_tool",
                cancel_event=cancel_event,
                deadline=deadline,
                recorder=recorder,
                workspace=workspace,
                workspace_snapshot=workspace_snapshot,
            )
            recorder.record("tool.started", {"tool": action.name, "call_id": action.id})
            tool_calls += 1

            try:
                output = tool.invoke(
                    action.arguments,
                    ToolContext(
                        execution_id=execution_id,
                        workspace=workspace,
                        record=recorder.record,
                    ),
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
            _check_execution_boundary(
                execution_id=execution_id,
                boundary="after_tool",
                cancel_event=cancel_event,
                deadline=deadline,
                recorder=recorder,
                workspace=workspace,
                workspace_snapshot=workspace_snapshot,
            )

    _check_execution_boundary(
        execution_id=execution_id,
        boundary="after_loop",
        cancel_event=cancel_event,
        deadline=deadline,
        recorder=recorder,
        workspace=workspace,
        workspace_snapshot=workspace_snapshot,
    )
    _raise_limit_error(
        f"Model-call limit of {selected_limits.model_calls} was exhausted",
        execution_id=execution_id,
        limit="model_calls",
        recorder=recorder,
        workspace=workspace,
        workspace_snapshot=workspace_snapshot,
    )


def _build_tool_registry(tools: Sequence[Tool]) -> dict[str, Tool]:
    registry: dict[str, Tool] = {}
    for tool in tools:
        if tool.spec.name == RESULT_TOOL_NAME:
            raise ConfigurationError(f"Reserved tool name: {RESULT_TOOL_NAME}")
        if tool.spec.name in registry:
            raise ConfigurationError(f"Duplicate tool name: {tool.spec.name}")
        registry[tool.spec.name] = tool
    return registry


def _check_execution_boundary(
    *,
    execution_id: str,
    boundary: str,
    cancel_event: Event | None,
    deadline: float | None,
    recorder: TraceRecorder,
    workspace: WorkspaceHandle | None,
    workspace_snapshot: Mapping[str, str],
) -> None:
    if cancel_event is not None and cancel_event.is_set():
        artifacts = _current_artifacts(workspace, workspace_snapshot)
        _record_artifacts(recorder, artifacts)
        recorder.record("execution.cancelled", {"boundary": boundary})
        raise ExecutionCancelled(
            "Execution was cancelled",
            execution_id=execution_id,
            artifacts=tuple(str(artifact.path) for artifact in artifacts),
            trace=recorder.snapshot(),
        )
    if deadline is not None and monotonic() >= deadline:
        _raise_limit_error(
            "Wall-time limit was exhausted",
            execution_id=execution_id,
            limit="wall_time",
            boundary=boundary,
            recorder=recorder,
            workspace=workspace,
            workspace_snapshot=workspace_snapshot,
        )


def _raise_limit_error(
    message: str,
    *,
    execution_id: str,
    limit: str,
    recorder: TraceRecorder,
    workspace: WorkspaceHandle | None,
    workspace_snapshot: Mapping[str, str],
    boundary: str | None = None,
) -> Never:
    artifacts = _current_artifacts(workspace, workspace_snapshot)
    _record_artifacts(recorder, artifacts)
    data = {"limit": limit}
    if boundary is not None:
        data["boundary"] = boundary
    recorder.record("execution.limit_exhausted", data)
    raise ModelLimitError(
        message,
        execution_id=execution_id,
        artifacts=tuple(str(artifact.path) for artifact in artifacts),
        trace=recorder.snapshot(),
    )


def _current_artifacts(
    workspace: WorkspaceHandle | None,
    workspace_snapshot: Mapping[str, str],
) -> tuple[Artifact, ...]:
    if workspace is None:
        return ()
    try:
        artifacts = workspace.artifacts_since(workspace_snapshot)
    except Exception:
        return ()
    return tuple(artifacts)


def _record_artifacts(recorder: TraceRecorder, artifacts: Sequence[Artifact]) -> None:
    for artifact in artifacts:
        recorder.record(
            f"artifact.{artifact.operation}",
            {"path": str(artifact.path)},
        )
