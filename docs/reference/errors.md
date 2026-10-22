# Errors

All Pilota runtime errors inherit from `AgentError`.

| Error | Meaning | Typical response |
| --- | --- | --- |
| `ConfigurationError` | The requested execution cannot be configured safely | Fix caller input |
| `ProviderError` | The provider request or response failed | Retry, fail over, or surface |
| `ModelLimitError` | A model-call or tool-call limit was exhausted | Increase budget or narrow task |
| `ToolError` | A tool could not complete an operation | Inspect tool input or implementation |
| `ToolTimeoutError` | A tool exceeded its own timeout | Tune command or timeout |
| `PermissionDenied` | An operation exceeded granted authority | Change policy only if intended |
| `ResultContractError` | Final values exhausted validation retries | Improve task/schema or handle failure |
| `ExecutionCancelled` | The caller cancelled at an execution boundary | Preserve evidence and stop |

## Shared evidence

`AgentError` exposes:

```python
error.execution_id  # str | None
error.artifacts     # tuple[str, ...]
error.trace         # Trace | None
```

Evidence is attached when an error occurs during an active execution. A configuration error raised
while constructing a provider directly may not have an execution ID.

## Tool errors inside the loop

`PermissionDenied`, `ToolError`, and unexpected exceptions raised by tools normally become model
observations rather than escaping immediately. This gives the model a chance to recover.

The exception can still escape when:

- application code invokes a tool directly,
- configuration fails before invocation,
- execution ends later because a limit is exhausted.

## API definitions

::: pilota.errors.AgentError

::: pilota.errors.ConfigurationError

::: pilota.errors.ProviderError

::: pilota.errors.ModelLimitError

::: pilota.errors.ToolError

::: pilota.errors.ToolTimeoutError

::: pilota.errors.PermissionDenied

::: pilota.errors.ResultContractError

::: pilota.errors.ExecutionCancelled
