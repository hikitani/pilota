<p align="center">
  <a href="https://hikitani.github.io/pilota/">
    <img src="https://raw.githubusercontent.com/hikitani/pilota/main/docs/assets/logo.svg" alt="Pilota" width="96" height="96">
  </a>
</p>

<h1 align="center">Pilota</h1>

<p align="center">
  <strong>Put agents inside Python. Keep Python in control.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/pilota/"><img src="https://img.shields.io/pypi/v/pilota?color=8b5cf6" alt="PyPI"></a>
  <a href="https://pypi.org/project/pilota/"><img src="https://img.shields.io/pypi/pyversions/pilota?color=8b5cf6" alt="Python versions"></a>
  <a href="https://github.com/hikitani/pilota/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-8b5cf6" alt="License: MIT"></a>
  <a href="https://hikitani.github.io/pilota/"><img src="https://img.shields.io/badge/docs-hikitani.github.io%2Fpilota-8b5cf6" alt="Documentation"></a>
</p>

<p align="center">
  <a href="https://hikitani.github.io/pilota/">Documentation</a>
  ·
  <a href="https://hikitani.github.io/pilota/getting-started/first-agent/">Tutorial</a>
  ·
  <a href="https://hikitani.github.io/pilota/reference/api/">API reference</a>
</p>

---

Pilota runs one bounded AI task as an ordinary typed expression. Your program owns the
workflow. The agent receives only the context, authority, and budget you grant.

```python
from dataclasses import dataclass

from pilota import agent
from pilota.providers.openrouter import OpenRouterModel


@dataclass
class Plan:
    steps: list[str]


with OpenRouterModel("openai/gpt-4.1-mini") as model:
    plan = agent(
        "Plan the requested change",
        model=model,
        context={"request": "Add response caching"},
        returns=Plan,
    )

for step in plan.steps:
    print(step)
```

- **Ordinary Python**: loops, branches, retries, and tests stay in your code.
- **Typed contracts**: request a dataclass, Pydantic model, or any `TypeAdapter` type.
- **Explicit authority**: expose selected tools, read-only resources, and a policy-controlled workspace.
- **Bounded execution**: limit model calls, tool calls, result retries, and wall time.
- **Inspectable outcomes**: keep the typed result, usage, trace, and changed-file artifacts.
- **Deterministic tests**: drive the full runtime with `ScriptedModel`, without network calls.

## Installation

```bash
pip install 'pilota[openrouter]'
```

Python 3.11+. The core package (`pip install pilota`) has no HTTP client; the `openrouter`
extra adds the OpenRouter provider.

> **Early development.** Versions `0.0.x` may contain breaking changes.

## License

[MIT](https://github.com/hikitani/pilota/blob/main/LICENSE)
