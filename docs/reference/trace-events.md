# Trace events

Traces are ordered runtime facts. Event data is intentionally small and provider-neutral.

| Event kind | Data | Meaning |
| --- | --- | --- |
| `execution.started` | `task` | Configuration completed and execution began |
| `model.requested` | `call` | A provider call is about to run |
| `model.responded` | `call` | The provider returned an action |
| `model.failed` | `error` | The provider raised an `AgentError` |
| `tool.started` | `tool`, `call_id` | Tool invocation began |
| `tool.completed` | `tool`, `call_id` | Tool invocation returned successfully |
| `tool.failed` | `tool`, `call_id`, `error` | Tool invocation failed |
| `tool.denied` | `tool`, optional `call_id`, `reason` or `error` | Tool was unavailable or unauthorized |
| `human.question` | `text`, `options` | A tool presented a question to a human |
| `human.answer` | `choices`, `text`, `delegated`, optional `reason` | A human answered, delegated, or the question budget was exhausted |
| `result.rejected` | `error` | Submitted result failed the contract |
| `result.produced` | none | A final result passed validation |
| `artifact.created` | `path` | A created workspace file was recorded |
| `artifact.modified` | `path` | A modified workspace file was recorded |
| `artifact.deleted` | `path` | A deleted workspace file was recorded |
| `execution.completed` | none | A successful execution ended |
| `execution.cancelled` | `boundary` | Caller cancellation was observed |
| `execution.limit_exhausted` | `limit`, optional `boundary` | A configured budget was exhausted |

## Consume events defensively

Event kinds and data are structured, but consumers should ignore fields they do not understand:

```python
for event in execution.trace.events:
    if event.kind == "tool.failed":
        report_tool_failure(
            tool=event.data.get("tool"),
            error=event.data.get("error"),
            timestamp=event.timestamp,
        )
```

Do not treat a trace as model chain-of-thought. It records observable runtime transitions and tool
outcomes.

Tools can add their own structured events with `ToolContext.record(kind, data)`. It is a no-op
outside an agent execution and records events in that execution's trace when provided by Pilota.

See the generated [`Trace` and `TraceEvent` API](api.md#pilota.models.Trace).
