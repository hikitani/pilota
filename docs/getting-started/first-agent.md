# Your first agent

An agent call needs three things:

1. a task,
2. a model,
3. a Python type for the result.

Start with `ScriptedModel`. It exercises the real Pilota runtime but returns actions you provide,
so the example is deterministic and uses no network.

## Define the result contract

```python
from dataclasses import dataclass


@dataclass
class Plan:
    summary: str
    steps: list[str]
```

`Plan` is more than a return annotation. Pilota converts it to JSON Schema for the model and
validates the final value before returning it to your program.

## Run the task

```python
from pilota import FinalResult, ScriptedModel, agent

model = ScriptedModel(
    [
        FinalResult(
            {
                "summary": "Add a bounded in-memory cache.",
                "steps": [
                    "Define the cache interface.",
                    "Cache successful responses.",
                    "Add expiration tests.",
                ],
            }
        )
    ]
)

plan = agent(
    "Create an implementation plan",
    model=model,
    context={"request": "Add response caching"},
    returns=Plan,
)

print(plan.summary)
for step in plan.steps:
    print(f"- {step}")
```

`agent(...)` returns `Plan`, not a JSON string or an unvalidated dictionary.

## Understand each input

`task`
: The bounded outcome for this execution. Prefer a concrete verb and completion condition.

`model`
: A provider implementation. `ScriptedModel` is deterministic; real providers call an external
  model service.

`context`
: Structured application data for this execution. Keep it separate from behavioral instructions.

`returns`
: The contract for the final value. Pilota asks the model to satisfy it and validates the answer.

## Inspect what the model received

`ScriptedModel` records every request:

```python
request = model.requests[0]

assert request.task == "Create an implementation plan"
assert request.context == {"request": "Add response caching"}
assert request.result_schema["type"] == "object"
```

This is useful for precise tests of application wiring.

## Keep the boundary small

An agent call should represent one coherent piece of nondeterministic work. Do not ask it to own
your whole application lifecycle.

```python
# Good: Python owns the workflow.
plan = agent("Plan the change", model=model, returns=Plan)
if plan.steps:
    review = agent(
        "Review this plan for missing risks",
        model=model,
        context={"plan": plan},
        returns=Review,
    )
```

The next step is to [replace the scripted model with a real provider](real-model.md).
