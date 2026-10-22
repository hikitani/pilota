# Bound and cancel execution

Every agent call should have a budget that matches the task. `Limits` bounds how many new actions
Pilota may begin.

```python
from datetime import timedelta

from pilota import Limits

limits = Limits(
    model_calls=8,
    tool_calls=20,
    result_retries=2,
    wall_time=timedelta(minutes=2),
)
```

## Limit model calls

`model_calls` counts provider responses, including calls used to:

- request tools,
- continue after tool observations,
- correct invalid final results.

When the budget is exhausted, Pilota raises `ModelLimitError`.

## Limit tool calls

`tool_calls` counts tool invocations, including calls that fail or are denied after invocation
starts. Unknown tool names are returned as observations without incrementing this counter.

Set `tool_calls=0` for a model-only task:

```python
Limits(model_calls=3, tool_calls=0)
```

## Limit result retries

`result_retries` counts corrected submissions after an initial invalid final value:

```text
initial invalid result
    ├── retry 1
    └── retry 2
```

With the default `result_retries=2`, Pilota accepts at most three submitted final values.

## Set a wall-time deadline

```python
Limits(wall_time=timedelta(seconds=30))
```

The deadline is checked at execution boundaries:

- before and after a provider call,
- before and after each tool call,
- after result validation.

It does not terminate a provider request or subprocess already in progress. Configure provider and
tool timeouts separately.

## Cancel from another thread

```python
from threading import Event, Thread

from pilota import agent

cancel_event = Event()


def run() -> None:
    agent(
        "Perform the bounded task",
        model=model,
        returns=Result,
        cancel_event=cancel_event,
    )


thread = Thread(target=run)
thread.start()

# Later, in response to application state:
cancel_event.set()
thread.join()
```

Pilota raises `ExecutionCancelled` at the next boundary.

## Preserve evidence on interruption

Limit and cancellation errors include:

- `execution_id`,
- workspace artifacts produced so far,
- the trace recorded so far.

```python
from pilota.errors import ExecutionCancelled, ModelLimitError

try:
    result = agent(...)
except (ExecutionCancelled, ModelLimitError) as error:
    audit_log.write(
        execution_id=error.execution_id,
        artifacts=error.artifacts,
        trace=error.trace,
    )
    raise
```
