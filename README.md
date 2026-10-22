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

The project is in early development. See [the design specification](docs/design.md).

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

The adapter sends Pilota tool schemas on every turn and uses OpenRouter structured outputs for
the requested Python result type. The selected model must support the features used by the call.

See the [OpenRouter provider guide](docs/openrouter.md) for configuration, typed results, tool
calling, failure behavior, and executable examples.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy
```

Live OpenRouter smoke tests are opt-in:

```bash
PILOTA_RUN_OPENROUTER_TESTS=1 \
OPENROUTER_API_KEY=... \
OPENROUTER_MODEL=... \
.venv/bin/pytest tests/integration/test_openrouter_live.py
```
