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

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy
```
