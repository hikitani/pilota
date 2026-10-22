# Pilota

Pilota embeds bounded autonomous AI work into ordinary Python programs.

```python
from dataclasses import dataclass

from pilota import FinalResult, ScriptedModel, agent


@dataclass
class Plan:
    steps: list[str]


task = "Add response caching"

plan = agent(
    "Create an implementation plan",
    model=ScriptedModel([FinalResult({"steps": ["Inspect the project", "Implement the change"]})]),
    context={"task": task},
    returns=Plan,
)
```

Python owns sequencing, branching, loops, retries, memory, cancellation, and validation.
Pilota owns one explicit agent execution boundary with typed inputs, constrained authority,
structured traces, artifacts, and a typed result.

`returns` accepts dataclasses, Pydantic models, and other types supported by Pydantic's
`TypeAdapter`.

The project is in early development.

- [Start the documentation](docs/index.md)
- [Follow the first-agent tutorial](docs/getting-started/first-agent.md)
- [Read the design specification](docs/design.md)

## OpenRouter

Install the provider extra and select an OpenRouter model explicitly:

```bash
pip install 'pilota[openrouter]'
export OPENROUTER_API_KEY=...
export OPENROUTER_MODEL=...
```

```python
import os
from dataclasses import dataclass

from pilota import agent
from pilota.providers.openrouter import OpenRouterModel


@dataclass
class Plan:
    steps: list[str]


with OpenRouterModel(os.environ["OPENROUTER_MODEL"]) as model:
    plan = agent(
        "Create an implementation plan",
        model=model,
        context={"task": "Add response caching"},
        returns=Plan,
    )
```

The adapter sends Pilota tool schemas plus a strict `final_result` function on every turn,
without `response_format`. The selected model must support tool calling. The name
`final_result` is reserved for completion; invalid results receive validation feedback with
up to `Limits(result_retries=2)` retries, also bounded by the model-call limit.
Tool-call batches execute sequentially with per-call limits and cancellation checks.
Final results must be submitted alone, not mixed with tool calls.

See the [OpenRouter provider guide](docs/openrouter.md) for configuration, typed results, tool
calling, failure behavior, and executable examples.

## Shell tool

`Shell` exposes only caller-configured command aliases, runs argv without shell
interpretation, requires workspace `execute` permission, uses a sanitized environment, and
returns bounded stdout and stderr:

```python
import sys

from pilota import DirectoryWorkspace, Shell

workspace = DirectoryWorkspace(".", allow={"read", "execute"})
shell = Shell({"tests": [sys.executable, "-m", "pytest"]})
```

The local process is not a filesystem or network sandbox. See the
[Shell tool guide](docs/shell.md) for its authority model and safe usage.

## Limits and cancellation

`Limits` prevents further runtime actions after a wall-time deadline, model-call count, or
tool-call count. Cancellation is caller-controlled with a standard `threading.Event` and is
checked between provider responses and tool calls:

```python
from datetime import timedelta
from threading import Event

from pilota import Limits, agent

cancelled = Event()

result = agent(
    "Update the implementation",
    model=model,
    workspace=workspace,
    tools=tools,
    limits=Limits(wall_time=timedelta(minutes=5), tool_calls=25),
    cancel_event=cancelled,
    returns=Change,
)
```

Cancellation raises `ExecutionCancelled` with the execution ID, partial artifacts, and trace.
The event does not interrupt an in-flight provider request or subprocess; it stops the next
runtime action.

## Instructions

Plain strings are always literal instruction text. Files are loaded only through an explicit
`InstructionFile`, once before the first model call:

```python
from pilota import InstructionFile, agent

result = agent(
    "Review the implementation",
    model=model,
    instructions=[
        "Keep the review concise.",
        InstructionFile("instructions/security.md"),
    ],
    returns=Review,
)
```

Missing files and decoding failures raise `ConfigurationError` before the provider is called.
Custom instruction objects can implement `render() -> str`.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev,docs]'
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/mkdocs build --strict
```

Live OpenRouter smoke tests are opt-in:

```bash
PILOTA_RUN_OPENROUTER_TESTS=1 \
OPENROUTER_API_KEY=... \
OPENROUTER_MODEL=... \
.venv/bin/pytest tests/integration/test_openrouter_live.py
```
