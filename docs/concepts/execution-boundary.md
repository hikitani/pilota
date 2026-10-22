# The execution boundary

Pilota wraps one bounded, nondeterministic computation inside an ordinary Python expression:

```python
result = agent(
    task,
    model=model,
    context=context,
    instructions=instructions,
    tools=tools,
    resources=resources,
    workspace=workspace,
    limits=limits,
    returns=Result,
)
```

Outside the call, Python is deterministic application code. Inside the call, a model may choose
tool actions and may need several turns to produce a valid result.

## Why the boundary matters

Model behavior cannot be treated like a normal pure function:

- the same request can produce different actions,
- providers can fail or change behavior,
- tools can mutate state,
- results can violate the requested schema,
- cost and duration can vary.

Pilota makes that uncertainty explicit and attaches controls and evidence to it.

## What crosses into the boundary

```text
task                 desired outcome
context              structured application facts
instructions         behavioral guidance
tools/resources      external actions and data
workspace            mutable file state
limits               execution budget
returns              typed completion contract
```

Nothing else is ambient. An execution does not automatically receive prior conversations, process
memory, filesystem access, or application services.

## What crosses out

On success:

```text
typed value
execution ID
usage counters
trace
workspace artifacts
```

On a structured failure, `AgentError` carries available execution evidence.

## One boundary is not one workflow

A workflow usually has application-level state transitions:

```python
plan = agent("Plan the change", ..., returns=Plan)
if requires_approval(plan):
    wait_for_approval(plan)
implementation = agent(
    "Implement the approved plan",
    context={"plan": plan},
    ...,
    returns=Implementation,
)
```

The approval wait belongs to the application, not to a hidden agent scheduler. This keeps control
flow, persistence, retries, and recovery in ordinary Python.

## Choosing boundary size

A useful agent task has:

- one outcome,
- one result contract,
- one authority set,
- one budget,
- one failure boundary.

Split a task when any of those need to differ.
