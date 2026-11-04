# Resume workflows with a journal

Long workflows can finish several expensive agent calls before a provider outage, exhausted budget,
or invalid result stops the process. Wrap the workflow in `Journal` to reuse completed work on the
next run:

```python
from pilota import Journal

with Journal("output/workflow.jsonl"):
    design_ui(model, human, output)
```

The workflow remains ordinary Python. `Journal` observes successful `agent(...)` and
`run_agent(...)` calls without adding checkpoint keys to each step.

## What gets recorded

A journal appends one JSON object for each fully successful agent call. The record contains:

- a fingerprint of the task, context, rendered instructions, tools, result schema, and non-secret
  model configuration,
- the validated result encoded as JSON,
- artifact paths and operations,
- its position and parent operation in the workflow.

Failed, cancelled, or incomplete agent calls leave no successful record. On the next run, Pilota
replays matching records in workflow order and executes the first missing or changed call normally.
Provider retries remain the responsibility of the provider or caller; the journal records only the
final success.

```text
run 1: analysis ✓  directions ✓  render ✗
run 2: analysis ↺  directions ↺  render → live execution
```

`Execution.usage` is zero for a replayed call because no model or tool runs. The trace contains
`journal.replayed`, and `TerminalProgress` prints the replay explicitly.

## Human answers

Completed answers from `TerminalHuman`, `NoHuman`, and `AskHuman` are journaled as their own
operations. This preserves a choice even when the surrounding agent later fails:

```python
from pilota import Question

direction = human.ask(
    Question("Choose a direction", options=("Carbon", "Polaris"))
)
```

Mark secrets and other sensitive answers so they are always asked live and never written. An agent
that asks a sensitive question is also not persisted as a replayable result:

```python
answer = human.ask(Question("API key?", sensitive=True))
```

An agent can make the same distinction through `AskHuman` by setting `sensitive=true`.

## Changes create a new active branch

If a call fingerprint changes, records after that point belong to the old workflow path. Pilota
atomically moves the old JSONL file to an adjacent `.archive-...` file, creates a new canonical file
with the matching prefix, and appends the new results there. Later runs always open the path passed
to `Journal`; archives are retained only for inspection.

## Concurrency and scope

One journal may be active in a process at a time. Calls from worker threads share that journal and
receive ordered sequence numbers under a lock. If thread scheduling changes the call order on a
later run, Pilota stops using the mismatched path rather than returning a result from another call.

Successful agent replay also skips its tools, so completed side effects are not repeated. For a
workspace-backed call, Pilota records a digest of the post-call workspace state and only replays when
the current workspace and policy still match; otherwise it archives that record and runs live. A
process can still die after an external side effect but before the agent completes; because that
agent has no successful record, it runs again. Tools that require exactly-once delivery still need
their own idempotency keys or transactional boundary.

## Start over

Delete the canonical JSONL file to start from scratch. Archive files do not participate in replay.
