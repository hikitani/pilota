# OpenRouter provider

`OpenRouterModel` connects Pilota's provider-neutral runtime to the OpenRouter Chat
Completions API. Python still owns control flow, tool execution, authorization, limits, and
result validation.

## Install

```bash
pip install 'pilota[openrouter]'
export OPENROUTER_API_KEY=...
export OPENROUTER_MODEL=...
```

The model is always selected by the caller. Choose one that supports every feature used by
the execution:

- tool calling is required for every execution, including calls without user tools;
- strict function schemas describe typed final results through the reserved `final_result` tool.

Feature support varies between models and routed providers.

## Typed result

Pilota converts the type passed through `returns` into a strict JSON Schema, sends that
schema as the parameters of a strict `final_result` function, and validates the final
response before returning it to Python. Non-object result types are wrapped in a required
`value` property and unwrapped on receipt. No `response_format` is sent. Every turn uses
`tool_choice: "required"` and `parallel_tool_calls: false`.

Invalid final results (including plain-text fallback responses) are replayed as
`final_result` tool calls with validation-error observations. `Limits.result_retries`
defaults to 2; exhausting it raises `ResultContractError` with trace and artifacts.
The model-call limit still applies. User and resource tools cannot use the reserved name.

```python
import os
from dataclasses import dataclass

from pilota import agent
from pilota.providers.openrouter import OpenRouterModel


@dataclass(frozen=True)
class Plan:
    steps: list[str]
    risks: list[str]


with OpenRouterModel(os.environ["OPENROUTER_MODEL"]) as model:
    plan = agent(
        "Create an implementation plan",
        model=model,
        context={"task": "Add response caching"},
        returns=Plan,
    )
```

See [`examples/openrouter_typed_result.py`](../examples/openrouter_typed_result.py) for a
complete executable example.

## Tool calling

Tools remain ordinary Pilota tools. The provider asks for a tool call, Pilota validates and
executes it inside the configured scope, then sends the observation back to the model.

```python
import os
from dataclasses import dataclass
from pathlib import Path

from pilota import DirectoryWorkspace, Editor, agent
from pilota.providers.openrouter import OpenRouterModel


@dataclass(frozen=True)
class Change:
    summary: str
    files: list[Path]


workspace = DirectoryWorkspace(
    "project",
    allow={"list", "read", "create", "edit"},
    deny_globs={".env", ".git/**"},
)

with OpenRouterModel(os.environ["OPENROUTER_MODEL"]) as model:
    change = agent(
        "Inspect the project and create NOTES.md describing its files.",
        model=model,
        workspace=workspace,
        tools=[Editor()],
        returns=Change,
    )
```

The workspace, not the provider, controls which paths and operations are allowed. The
current adapter asks OpenRouter for one tool call at a time because Pilota does not yet
execute parallel tool batches.

See [`examples/openrouter_editor.py`](../examples/openrouter_editor.py) for a complete
executable example.

## Configuration

```python
OpenRouterModel(
    "provider/model",
    api_key=None,
    timeout=60.0,
    http_referer="https://example.com",
    app_title="My application",
)
```

- `api_key` overrides `OPENROUTER_API_KEY`.
- `timeout` configures the internally managed HTTP client.
- `http_referer` and `app_title` set OpenRouter attribution headers.
- `base_url` can point at a compatible proxy or test server.
- `client` accepts a caller-managed `httpx.Client`.

Use the model as a context manager so its internally created HTTP client is closed. A
caller-supplied client remains owned by the caller.

## Failures

Pilota keeps configuration, provider, tool, and result-contract failures distinct:

- `ConfigurationError`: missing API key, empty model name, or inconsistent history;
- `ProviderError`: transport, HTTP, malformed response, or invalid provider JSON;
- `ToolError`: a selected tool failed;
- `PermissionDenied`: a tool requested an unauthorized workspace operation;
- `ResultContractError`: the final value did not satisfy `returns`.

Provider errors include the execution ID when one exists. Credentials are never included
in request failure messages.

## Live tests

The default test suite uses a mocked HTTP transport and never calls OpenRouter. Real smoke
tests require an explicit opt-in:

```bash
PILOTA_RUN_OPENROUTER_TESTS=1 \
OPENROUTER_API_KEY=... \
OPENROUTER_MODEL=... \
.venv/bin/pytest tests/integration/test_openrouter_live.py
```

The live tests cover one typed structured result and one real editor tool round trip.
