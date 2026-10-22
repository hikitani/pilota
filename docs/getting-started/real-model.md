# Use a real model

Pilota's provider interface separates your application contract from a model service. The first
built-in network provider is OpenRouter.

## Install the provider

```bash
pip install "pilota[openrouter]"
export OPENROUTER_API_KEY="..."
```

Select a model that supports tool calling. The provider always exposes a strict `final_result`
tool because typed completion uses the same mechanism as other tool calls.

## Replace `ScriptedModel`

The task and result type stay unchanged:

```python
import os
from dataclasses import dataclass

from pilota import agent
from pilota.providers.openrouter import OpenRouterModel


@dataclass
class Plan:
    summary: str
    steps: list[str]


with OpenRouterModel(
    os.environ.get("OPENROUTER_MODEL", "openai/gpt-4.1-mini")
) as model:
    plan = agent(
        "Create an implementation plan",
        model=model,
        context={"request": "Add response caching"},
        instructions=["Return concrete implementation steps, not general advice."],
        returns=Plan,
    )

print(plan)
```

Use the context manager, or call `model.close()`, to close the provider's HTTP client.

## Keep credentials outside context

Do not place API keys in `context`, `instructions`, workspace files, or tool arguments. The
OpenRouter adapter reads `OPENROUTER_API_KEY` when `api_key` is omitted.

```python
model = OpenRouterModel("openai/gpt-4.1-mini")
```

You can also pass `api_key` explicitly when your application already has a secret manager:

```python
model = OpenRouterModel(
    "openai/gpt-4.1-mini",
    api_key=secret_store.read("openrouter"),
)
```

## Add a budget before adding tools

Model-only tasks can still loop after invalid results. Set limits appropriate to the operation:

```python
from datetime import timedelta

from pilota import Limits

plan = agent(
    "Create an implementation plan",
    model=model,
    returns=Plan,
    limits=Limits(
        model_calls=4,
        tool_calls=0,
        result_retries=1,
        wall_time=timedelta(seconds=45),
    ),
)
```

The wall-time deadline is cooperative. It stops the next runtime action; it does not interrupt an
HTTP request already in flight.

See the full [OpenRouter provider guide](../openrouter.md) for payload behavior, errors, custom
clients, and executable examples.
