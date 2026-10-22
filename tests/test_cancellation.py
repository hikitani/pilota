from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from threading import Event
from typing import Any

import pytest

from pilota import (
    Editor,
    FinalResult,
    InMemoryWorkspace,
    Limits,
    ScriptedModel,
    ToolCall,
    agent,
    run_agent,
)
from pilota.errors import ExecutionCancelled, ModelLimitError
from pilota.models import ModelAction, ModelRequest, ToolSpec
from pilota.tools import ToolContext


class FakeClock:
    def __init__(self, *values: float) -> None:
        self._values = list(values)
        self._last = values[-1]

    def __call__(self) -> float:
        if self._values:
            self._last = self._values.pop(0)
        return self._last


class CancellingModel:
    def __init__(self, cancel_event: Event, action: ModelAction) -> None:
        self.cancel_event = cancel_event
        self.action = action
        self.requests: list[ModelRequest] = []

    def respond(self, request: ModelRequest) -> ModelAction:
        self.requests.append(request)
        self.cancel_event.set()
        return self.action


class CancellingTool:
    def __init__(self, cancel_event: Event) -> None:
        self.cancel_event = cancel_event
        self.calls = 0

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="cancel",
            description="Create a file, then request cancellation.",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        )

    def invoke(self, arguments: Mapping[str, Any], context: ToolContext) -> Any:
        del arguments
        self.calls += 1
        assert context.workspace is not None
        context.workspace.write_text("partial.txt", "partial\n")
        self.cancel_event.set()
        return {"cancelled": True}


class RecordingTool:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="record",
            description="Record whether the tool was invoked.",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        )

    def invoke(self, arguments: Mapping[str, Any], context: ToolContext) -> Any:
        del arguments, context
        self.calls += 1
        return {"called": True}


def test_limits_require_positive_timedelta() -> None:
    assert Limits(2, 3) == Limits(model_calls=2, tool_calls=3)

    with pytest.raises(ValueError, match="greater than zero"):
        Limits(wall_time=timedelta(0))

    with pytest.raises(TypeError, match=r"datetime\.timedelta"):
        Limits(wall_time=1)  # type: ignore[arg-type]


def test_pre_cancelled_execution_never_calls_model() -> None:
    cancel_event = Event()
    cancel_event.set()
    model = ScriptedModel([FinalResult("unused")])

    with pytest.raises(ExecutionCancelled) as raised:
        agent(
            "Do not start",
            model=model,
            returns=str,
            cancel_event=cancel_event,
        )

    assert model.requests == []
    assert raised.value.execution_id is not None
    assert raised.value.artifacts == ()
    assert raised.value.trace is not None
    assert raised.value.trace.events[-1].kind == "execution.cancelled"
    assert raised.value.trace.events[-1].data["boundary"] == "before_model"


def test_cancellation_after_model_prevents_tool_call() -> None:
    cancel_event = Event()
    workspace = InMemoryWorkspace()
    model = CancellingModel(
        cancel_event,
        ToolCall(
            id="write",
            name="editor",
            arguments={
                "operation": "write",
                "path": "should-not-exist.txt",
                "content": "unused",
            },
        ),
    )

    with pytest.raises(ExecutionCancelled) as raised:
        run_agent(
            "Cancel after the model responds",
            model=model,
            workspace=workspace,
            tools=[Editor()],
            returns=str,
            cancel_event=cancel_event,
        )

    assert len(model.requests) == 1
    assert workspace.snapshot() == {}
    assert raised.value.trace is not None
    assert "tool.started" not in [event.kind for event in raised.value.trace.events]


def test_cancellation_during_tool_stops_before_next_model_call() -> None:
    cancel_event = Event()
    workspace = InMemoryWorkspace()
    tool = CancellingTool(cancel_event)
    model = ScriptedModel(
        [
            ToolCall(id="cancel", name="cancel", arguments={}),
            FinalResult("unused"),
        ]
    )

    with pytest.raises(ExecutionCancelled) as raised:
        run_agent(
            "Create a partial artifact, then cancel",
            model=model,
            workspace=workspace,
            tools=[tool],
            returns=str,
            cancel_event=cancel_event,
        )

    assert tool.calls == 1
    assert len(model.requests) == 1
    assert raised.value.artifacts == ("partial.txt",)
    assert raised.value.trace is not None
    assert [event.kind for event in raised.value.trace.events[-3:]] == [
        "tool.completed",
        "artifact.created",
        "execution.cancelled",
    ]


def test_wall_time_can_stop_before_first_model_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pilota.execution.monotonic",
        FakeClock(0.0, 2.0),
    )
    model = ScriptedModel([FinalResult("unused")])

    with pytest.raises(ModelLimitError, match="Wall-time") as raised:
        run_agent(
            "Do not start after the deadline",
            model=model,
            returns=str,
            limits=Limits(wall_time=timedelta(seconds=1)),
        )

    assert model.requests == []
    assert raised.value.trace is not None
    assert raised.value.trace.events[-1].kind == "execution.limit_exhausted"
    assert raised.value.trace.events[-1].data == {
        "limit": "wall_time",
        "boundary": "before_model",
    }


def test_wall_time_after_model_prevents_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pilota.execution.monotonic",
        FakeClock(0.0, 0.0, 2.0),
    )
    tool = RecordingTool()
    model = ScriptedModel([ToolCall(id="record", name="record", arguments={})])

    with pytest.raises(ModelLimitError, match="Wall-time") as raised:
        run_agent(
            "Do not invoke a tool after the deadline",
            model=model,
            tools=[tool],
            returns=str,
            limits=Limits(wall_time=timedelta(seconds=1)),
        )

    assert len(model.requests) == 1
    assert tool.calls == 0
    assert raised.value.trace is not None
    assert raised.value.trace.events[-1].data["boundary"] == "after_model"


def test_wall_time_during_tool_preserves_partial_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pilota.execution.monotonic",
        FakeClock(0.0, 0.0, 0.0, 0.0, 2.0),
    )
    workspace = InMemoryWorkspace()
    tool = CancellingTool(Event())
    model = ScriptedModel(
        [
            ToolCall(id="write", name="cancel", arguments={}),
            FinalResult("unused"),
        ]
    )

    with pytest.raises(ModelLimitError, match="Wall-time") as raised:
        run_agent(
            "Stop after a tool crosses the deadline",
            model=model,
            workspace=workspace,
            tools=[tool],
            returns=str,
            limits=Limits(wall_time=timedelta(seconds=1)),
        )

    assert len(model.requests) == 1
    assert raised.value.artifacts == ("partial.txt",)
    assert raised.value.trace is not None
    assert [event.kind for event in raised.value.trace.events[-3:]] == [
        "tool.completed",
        "artifact.created",
        "execution.limit_exhausted",
    ]
    assert raised.value.trace.events[-1].data["boundary"] == "after_tool"


def test_execution_completes_before_wall_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pilota.execution.monotonic",
        FakeClock(0.0, 0.1, 0.2, 0.3),
    )

    execution = run_agent(
        "Finish within the deadline",
        model=ScriptedModel([FinalResult("done")]),
        returns=str,
        limits=Limits(wall_time=timedelta(seconds=1)),
    )

    assert execution.value == "done"
