# Test agent programs

Test application logic without relying on a live model. `ScriptedModel` returns a predetermined
sequence of actions and records every request it receives.

## Test a direct result

```python
from dataclasses import dataclass

from pilota import FinalResult, ScriptedModel, agent


@dataclass
class Classification:
    label: str
    confidence: float


def test_classifies_incident() -> None:
    model = ScriptedModel(
        [FinalResult({"label": "database", "confidence": 0.91})]
    )

    result = agent(
        "Classify the incident",
        model=model,
        context={"title": "Primary database is unavailable"},
        returns=Classification,
    )

    assert result == Classification(label="database", confidence=0.91)
```

## Test tool interaction

Script tool calls and the final result in order:

```python
from pilota import (
    Editor,
    FinalResult,
    InMemoryWorkspace,
    ScriptedModel,
    ToolCall,
    run_agent,
)


def test_agent_updates_file() -> None:
    workspace = InMemoryWorkspace({"version.txt": "1\n"})
    model = ScriptedModel(
        [
            ToolCall(
                id="write-version",
                name="editor",
                arguments={
                    "operation": "write",
                    "path": "version.txt",
                    "content": "2\n",
                },
            ),
            FinalResult("Updated version.txt"),
        ]
    )

    execution = run_agent(
        "Set the version to 2",
        model=model,
        workspace=workspace,
        tools=[Editor()],
        returns=str,
    )

    assert workspace.read_text("version.txt") == "2\n"
    assert [(item.operation, str(item.path)) for item in execution.artifacts] == [
        ("modified", "version.txt")
    ]
```

## Assert request wiring

```python
request = model.requests[0]

assert request.task == "Set the version to 2"
assert request.context == {}
assert [tool.name for tool in request.tools] == ["editor"]
assert request.result_schema["type"] == "string"
```

After a tool call, the next recorded request contains the call and its observation.

## Test invalid result recovery

```python
from pilota import FinalResult, Limits, ScriptedModel, agent

model = ScriptedModel(
    [
        FinalResult({"label": "database", "confidence": "not-a-number"}),
        FinalResult({"label": "database", "confidence": 0.91}),
    ]
)

result = agent(
    "Classify the incident",
    model=model,
    returns=Classification,
    limits=Limits(result_retries=1),
)

assert result.confidence == 0.91
assert len(model.requests) == 2
assert model.requests[1].observations[0].error is not None
```

## Keep live tests separate

Use a small opt-in integration suite to verify provider compatibility:

```bash
PILOTA_RUN_OPENROUTER_TESTS=1 \
OPENROUTER_API_KEY=... \
OPENROUTER_MODEL=... \
pytest tests/integration/test_openrouter_live.py
```

Live tests answer a different question from deterministic tests. They can discover provider
behavior changes, but should not be the foundation of application correctness.
