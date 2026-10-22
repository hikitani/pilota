from datetime import timedelta
from threading import Event

import pytest

from pilota import Editor, InMemoryWorkspace, Limits, ToolCall, run_agent
from pilota.errors import AgentError, ExecutionCancelled, ModelLimitError, ProviderError
from pilota.models import ModelAction, ModelRequest


@pytest.mark.parametrize("boundary", [None, "cancel", "wall"])
def test_model_failure_preserves_context_and_boundary_precedence(
    boundary: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = Event()
    clock = [0.0]
    monkeypatch.setattr("pilota.execution.monotonic", lambda: clock[0])
    original = ProviderError("provider broke", execution_id="wrong")

    class FailingModel:
        calls = 0

        def respond(self, request: ModelRequest) -> ModelAction:
            self.calls += 1
            if self.calls == 1:
                return ToolCall(
                    "write",
                    "editor",
                    {
                        "operation": "write",
                        "path": "note.txt",
                        "content": "saved",
                    },
                )
            if boundary == "cancel":
                event.set()
            if boundary == "wall":
                clock[0] = 2.0
            raise original

    expected = {None: ProviderError, "cancel": ExecutionCancelled, "wall": ModelLimitError}[
        boundary
    ]
    with pytest.raises(expected) as raised:
        run_agent(
            "Write then fail",
            model=FailingModel(),
            returns=str,
            workspace=InMemoryWorkspace(),
            tools=[Editor()],
            cancel_event=event,
            limits=Limits(wall_time=timedelta(seconds=1)),
        )
    error: AgentError = raised.value
    assert error.execution_id and error.execution_id != "wrong"
    assert error.artifacts == ("note.txt",)
    assert error.trace is not None
    events = error.trace.events
    assert any(e.kind == "model.failed" and e.data["error"] == "provider broke" for e in events)
    assert any(e.kind == "artifact.created" for e in events)
    if boundary is None:
        assert error is original
    else:
        assert error.__cause__ is original
        assert events[-1].data["boundary"] == "after_model"
