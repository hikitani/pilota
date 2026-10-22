from dataclasses import dataclass
from pathlib import Path

import pytest

from pilota import (
    RESULT_TOOL_NAME,
    Artifact,
    Editor,
    FinalResult,
    InMemoryWorkspace,
    Limits,
    ScriptedModel,
    ToolCall,
    agent,
    run_agent,
)
from pilota.errors import ConfigurationError, ModelLimitError, ResultContractError
from pilota.models import ToolSpec


@dataclass(frozen=True)
class Change:
    summary: str
    files: list[Path]


def test_agent_returns_typed_dataclass() -> None:
    model = ScriptedModel(
        [
            FinalResult(
                {
                    "summary": "Added response caching",
                    "files": ["src/cache.py"],
                }
            )
        ]
    )

    result = agent("Implement caching", model=model, returns=Change)

    assert result == Change(
        summary="Added response caching",
        files=[Path("src/cache.py")],
    )
    assert model.requests[0].result_schema["type"] == "object"


def test_run_agent_executes_tools_and_collects_artifacts() -> None:
    workspace = InMemoryWorkspace()
    model = ScriptedModel(
        [
            ToolCall(
                id="write-cache",
                name="editor",
                arguments={
                    "operation": "write",
                    "path": "src/cache.py",
                    "content": "CACHE = {}\n",
                },
            ),
            FinalResult(
                {
                    "summary": "Created cache module",
                    "files": ["src/cache.py"],
                }
            ),
        ]
    )

    execution = run_agent(
        "Create a cache module",
        model=model,
        workspace=workspace,
        tools=[Editor()],
        returns=Change,
    )

    assert workspace.read_text("src/cache.py") == "CACHE = {}\n"
    assert execution.artifacts == (Artifact(path=Path("src/cache.py"), operation="created"),)
    assert execution.usage.model_calls == 2
    assert execution.usage.tool_calls == 1
    assert "artifact.created" in [event.kind for event in execution.trace.events]
    assert model.requests[1].observations[0].output == {
        "path": "src/cache.py",
        "written": 11,
    }
    assert model.requests[1].tool_calls == (
        ToolCall(
            id="write-cache",
            name="editor",
            arguments={
                "operation": "write",
                "path": "src/cache.py",
                "content": "CACHE = {}\n",
            },
        ),
    )


def test_permission_denial_is_returned_to_model() -> None:
    workspace = InMemoryWorkspace(allow={"list", "read"})
    model = ScriptedModel(
        [
            ToolCall(
                id="forbidden-write",
                name="editor",
                arguments={
                    "operation": "write",
                    "path": "src/cache.py",
                    "content": "CACHE = {}\n",
                },
            ),
            FinalResult({"summary": "Could not write", "files": []}),
        ]
    )

    execution = run_agent(
        "Create a cache module",
        model=model,
        workspace=workspace,
        tools=[Editor()],
        returns=Change,
    )

    assert model.requests[1].observations[0].error == ("Workspace operation is not allowed: create")
    assert "tool.denied" in [event.kind for event in execution.trace.events]
    assert execution.artifacts == ()


def test_invalid_result_raises_contract_error() -> None:
    model = ScriptedModel([FinalResult({"summary": "Missing files"})] * 3)

    with pytest.raises(ResultContractError):
        agent("Implement caching", model=model, returns=Change)


@pytest.mark.parametrize("invalid", [None, {}, "wrong"])
def test_result_retry_then_success(invalid: object) -> None:
    model = ScriptedModel(
        [FinalResult(invalid, id="result-1", provider_data={"reasoning": "x"}), FinalResult(5)]
    )
    execution = run_agent("Return five", model=model, returns=int)
    assert execution.value == 5
    assert execution.usage.model_calls == 2
    assert execution.usage.tool_calls == 0
    call = model.requests[1].tool_calls[0]
    assert call == ToolCall("result-1", RESULT_TOOL_NAME, invalid)
    assert call.provider_data == {"reasoning": "x"}
    assert model.requests[1].observations[0].error
    assert "result.rejected" in [event.kind for event in execution.trace.events]


@pytest.mark.parametrize("retries", [0, 2])
def test_result_retries_exhausted_preserve_diagnostics(retries: int) -> None:
    model = ScriptedModel(
        [
            ToolCall(
                "write", "editor", {"operation": "write", "path": "note.txt", "content": "hi"}
            ),
            *[FinalResult(None) for _ in range(retries + 1)],
        ]
    )
    with pytest.raises(ResultContractError) as raised:
        run_agent(
            "Write",
            model=model,
            returns=int,
            tools=[Editor()],
            workspace=InMemoryWorkspace(),
            limits=Limits(result_retries=retries),
        )
    assert len(model.requests) == retries + 2
    assert raised.value.execution_id == model.requests[0].execution_id
    assert raised.value.artifacts == ("note.txt",)
    assert raised.value.trace is not None
    assert raised.value.trace.events[-1].data == {"limit": "result_retries"}
    if retries:
        assert model.requests[-1].tool_calls[-1].id


def test_result_retry_still_obeys_model_limit() -> None:
    with pytest.raises(ModelLimitError):
        run_agent(
            "Return int",
            model=ScriptedModel([FinalResult(None)]),
            returns=int,
            limits=Limits(model_calls=1),
        )


def test_reserved_result_tool_name() -> None:
    class ReservedTool:
        spec = ToolSpec(RESULT_TOOL_NAME, "Conflict", {})

        def invoke(self, arguments: object, context: object) -> None:
            raise AssertionError("must not execute")

    with pytest.raises(ConfigurationError, match="Reserved tool name"):
        run_agent("Conflict", model=ScriptedModel([]), returns=int, tools=[ReservedTool()])


def test_negative_result_retries() -> None:
    with pytest.raises(ValueError, match="result_retries"):
        Limits(result_retries=-1)


def test_model_call_limit_is_enforced() -> None:
    model = ScriptedModel(
        [
            ToolCall(id="unknown", name="missing", arguments={}),
        ]
    )

    with pytest.raises(ModelLimitError):
        agent(
            "Try an unavailable tool",
            model=model,
            returns=str,
            limits=Limits(model_calls=1),
        )
