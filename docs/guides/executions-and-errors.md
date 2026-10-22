# Inspect executions and failures

Use `agent(...)` when you only need the typed value. Use `run_agent(...)` when your application also
needs execution evidence.

## Inspect a successful execution

```python
from pilota import run_agent

execution = run_agent(
    "Update the implementation",
    model=model,
    workspace=workspace,
    tools=tools,
    returns=ChangeSummary,
)

print(execution.id)
print(execution.value)
print(execution.status)
print(execution.usage.model_calls)
print(execution.usage.tool_calls)
print(execution.artifacts)
print(execution.trace.events)
```

The successful status is `ExecutionStatus.SUCCEEDED`.

## Handle the error hierarchy

All structured runtime failures inherit from `AgentError`:

```python
from pilota.errors import AgentError

try:
    execution = run_agent(...)
except AgentError as error:
    logger.error(
        "agent execution failed",
        extra={
            "execution_id": error.execution_id,
            "artifacts": error.artifacts,
        },
    )
    raise
```

Catch a narrower class when the response differs:

```python
from pilota.errors import (
    ConfigurationError,
    PermissionDenied,
    ProviderError,
    ResultContractError,
)

try:
    value = agent(...)
except ConfigurationError:
    # Fix caller configuration. Retrying unchanged input will not help.
    raise
except ProviderError:
    # Apply provider retry or failover policy.
    raise
except ResultContractError:
    # The model exhausted its result-correction budget.
    raise
except PermissionDenied:
    # A caller-owned operation happened outside the model loop.
    raise
```

Tool failures inside the execution loop normally become observations so the model can recover.
Provider failures terminate the execution.

## Read traces as ordered facts

Each `TraceEvent` contains:

- `kind`,
- `data`,
- a UTC `timestamp`.

```python
for event in execution.trace.events:
    print(event.timestamp, event.kind, event.data)
```

Trace data records runtime events, not hidden model reasoning.

See [Trace events](../reference/trace-events.md) for the emitted event kinds and
[Errors](../reference/errors.md) for the full hierarchy.
