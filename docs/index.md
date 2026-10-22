---
hide:
  - navigation
  - toc
---

<div class="hero" markdown>
<div markdown>

# Put agents inside Python. Keep Python in control.

Pilota runs one bounded AI task as an ordinary typed expression. Your program owns the
workflow. The agent receives only the context, authority, and budget you grant.

<div class="hero__actions" markdown>
[Start the tutorial](getting-started/index.md){ .md-button .md-button--primary }
[Understand the model](concepts/execution-boundary.md){ .md-button }
</div>

</div>
<div class="hero__code" markdown>

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

</div>
</div>

<div class="feature-grid" markdown>
<div class="feature-card" markdown>

### Ordinary Python

Use functions, loops, branches, concurrency, retries, and tests you already understand.

</div>
<div class="feature-card" markdown>

### Typed contracts

Request a dataclass, Pydantic model, collection, scalar, or any `TypeAdapter` type.

</div>
<div class="feature-card" markdown>

### Explicit authority

Expose selected tools, read-only resources, and a policy-controlled workspace.

</div>
<div class="feature-card" markdown>

### Bounded execution

Limit model calls, tool calls, result retries, and elapsed wall time.

</div>
<div class="feature-card" markdown>

### Inspectable outcomes

Keep the typed result, usage, trace, execution ID, and changed-file artifacts.

</div>
<div class="feature-card" markdown>

### Deterministic tests

Drive the complete runtime with `ScriptedModel`, without making network requests.

</div>
</div>

## The whole mental model

```text
Python program
    │
    ├── task + context + instructions
    ├── typed result contract
    ├── tools + resources + workspace
    └── limits + cancellation
             │
             ▼
       one agent(...) call
             │
             ▼
typed value or structured AgentError
```

Pilota is not a workflow language. It is the explicit boundary around one nondeterministic,
possibly tool-using computation. Compose several calls with Python when your application needs
a larger workflow.

## Choose your path

| If you want to… | Read… |
| --- | --- |
| Run a useful example in a few minutes | [Your first agent](getting-started/first-agent.md) |
| Connect a real model | [Use a real model](getting-started/real-model.md) |
| Build a multi-step agent program | [Compose agents with Python](guides/python-orchestration.md) |
| Let an agent read or modify files | [Grant tools and resources](guides/authority.md) |
| Understand the security boundary | [Authority model](concepts/authority-model.md) |
| Integrate a provider or custom tool | [Public API](reference/api.md) |
