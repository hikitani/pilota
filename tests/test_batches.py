from threading import Event

import pytest

from pilota import (
    RESULT_TOOL_NAME,
    Editor,
    FinalResult,
    InMemoryWorkspace,
    Limits,
    ScriptedModel,
    ToolCall,
    run_agent,
)
from pilota.errors import (
    ConfigurationError,
    ExecutionCancelled,
    ModelLimitError,
    ResultContractError,
)
from pilota.tools import ToolContext


def write(call_id: str, path: str) -> ToolCall:
    return ToolCall(call_id, "editor", {"operation": "write", "path": path, "content": "saved"})


def test_batch_executes_sequentially_and_observes_errors() -> None:
    model = ScriptedModel(
        [
            (
                write("one", "one.txt"),
                ToolCall("missing", "absent", {}),
                ToolCall("read", "editor", {"operation": "read", "path": "one.txt"}),
            ),
            FinalResult("done"),
        ]
    )
    execution = run_agent(
        "Write and read", model=model, returns=str, tools=[Editor()], workspace=InMemoryWorkspace()
    )
    assert execution.usage.model_calls == 2
    assert execution.usage.tool_calls == 2
    assert [o.call_id for o in model.requests[1].observations] == ["one", "missing", "read"]
    assert model.requests[1].observations[1].error
    assert model.requests[1].observations[2].output == "saved"


def test_tool_limit_mid_batch_retains_first_artifact() -> None:
    workspace = InMemoryWorkspace()
    with pytest.raises(ModelLimitError) as raised:
        run_agent(
            "Write",
            model=ScriptedModel([(write("one", "one.txt"), write("two", "two.txt"))]),
            returns=str,
            tools=[Editor()],
            workspace=workspace,
            limits=Limits(tool_calls=1),
        )
    assert workspace.list_files() == ["one.txt"]
    assert raised.value.artifacts == ("one.txt",)


def test_cancel_mid_batch() -> None:
    event = Event()

    class CancellingEditor(Editor):
        def invoke(self, arguments: object, context: ToolContext) -> object:
            output = super().invoke(arguments, context)  # type: ignore[arg-type]
            event.set()
            return output

    workspace = InMemoryWorkspace()
    with pytest.raises(ExecutionCancelled) as raised:
        run_agent(
            "Write",
            model=ScriptedModel([(write("one", "one.txt"), write("two", "two.txt"))]),
            returns=str,
            tools=[CancellingEditor()],
            workspace=workspace,
            cancel_event=event,
        )
    assert workspace.list_files() == ["one.txt"]
    assert raised.value.artifacts == ("one.txt",)


@pytest.mark.parametrize("retries", [0, 2])
def test_mixed_result_runs_tools_and_rejects_completion(retries: int) -> None:
    workspace = InMemoryWorkspace()
    model = ScriptedModel(
        [
            (ToolCall("final", RESULT_TOOL_NAME, "premature"), write("one", "one.txt")),
            FinalResult("done"),
        ]
    )
    if retries == 0:
        with pytest.raises(ResultContractError, match="final_result alone") as raised:
            run_agent(
                "Write",
                model=model,
                returns=str,
                tools=[Editor()],
                workspace=workspace,
                limits=Limits(result_retries=retries),
            )
        assert raised.value.artifacts == ("one.txt",)
    else:
        execution = run_agent(
            "Write", model=model, returns=str, tools=[Editor()], workspace=workspace
        )
        assert execution.value == "done"
        assert execution.usage.tool_calls == 1
        assert model.requests[1].observations[-1].call_id == "final"
        assert "final_result alone" in (model.requests[1].observations[-1].error or "")
    assert workspace.read_text("one.txt") == "saved"


def test_empty_batch_is_invalid() -> None:
    with pytest.raises(ConfigurationError, match="invalid tool-call batch"):
        run_agent("Empty", model=ScriptedModel([()]), returns=str)
