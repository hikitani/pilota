from dataclasses import dataclass
from pathlib import Path

import pytest

from pilota import (
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
from pilota.errors import ModelLimitError, ResultContractError


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
    assert model.requests[1].observations[0].output == {
        "path": "src/cache.py",
        "written": 11,
    }


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
    model = ScriptedModel([FinalResult({"summary": "Missing files"})])

    with pytest.raises(ResultContractError):
        agent("Implement caching", model=model, returns=Change)


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
