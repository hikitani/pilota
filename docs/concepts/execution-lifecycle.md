# Execution lifecycle

One execution has a configuration phase followed by a bounded model and tool loop.

## 1. Configure

Before the first provider call, Pilota:

1. creates an execution ID,
2. selects or validates limits,
3. builds the result codec and schema,
4. renders instruction inputs,
5. combines explicit tools with resource tools,
6. validates unique tool names,
7. snapshots the workspace,
8. records `execution.started`.

Configuration failures stop before the model receives a request.

## 2. Request a model action

Pilota constructs a `ModelRequest` containing:

- execution ID,
- task,
- context,
- rendered instructions,
- tool specifications,
- result schema,
- prior tool calls,
- matching observations.

The provider returns one of:

- a `ToolCall`,
- a batch of `ToolCall` values,
- a `FinalResult`.

## 3. Execute tool actions

Tool-call batches are executed sequentially. For each call, Pilota:

1. checks cancellation and wall time,
2. checks the tool-call budget,
3. finds the named tool,
4. records `tool.started`,
5. invokes the tool,
6. records completion, denial, or failure,
7. stores an observation for the next model request.

A final result submitted in the same batch as other tools is rejected. Completion must be a
separate action after prior tools finish.

## 4. Validate completion

Pilota decodes the submitted value with the requested result type.

If validation fails:

1. it records `result.rejected`,
2. adds the validation error as an observation,
3. requests a corrected result if retry and model-call budgets remain.

If validation succeeds, Pilota records result and artifact events and returns `Execution[T]`.

## 5. Preserve partial evidence

Cancellation, limit exhaustion, and provider failures attach the execution ID, trace, and current
workspace artifacts to the raised error.

```text
configure
   │
   ▼
model request ◄──────────────┐
   │                         │
   ├── tool call(s) ──► observations
   │
   └── final result
            │
            ├── invalid ─────┘
            │
            └── valid ──► Execution[T]
```
