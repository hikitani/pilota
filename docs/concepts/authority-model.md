# Authority model

Pilota follows a simple rule: the model receives no external authority unless the caller grants it
for this execution.

## Authority is capability-specific

```text
model
  ├── can call explicitly supplied tools
  ├── can invoke operations on named resources
  └── can affect a workspace only through supplied tools
```

A workspace alone does not let the model edit files. `Editor` alone cannot edit files without a
workspace. `Shell` additionally requires a process-backed workspace with `execute` permission.

## Data and actions are different

`context` supplies data directly to the model. Resources let the model request selected external
data. Tools let the model request actions.

Keeping these separate answers three audit questions:

1. What did the caller disclose immediately?
2. What could the model request later?
3. What state could the model change?

## Authorization is enforced at invocation

Model-facing JSON Schema is descriptive, not trusted. Real authorization happens inside resource,
workspace, and tool implementations.

For example, `DirectoryWorkspace`:

- rejects absolute paths,
- rejects parent traversal,
- confines resolved paths to its root,
- checks an operation allowlist,
- checks path deny globs.

The model cannot override these checks with a prompt.

## Denial is observable

When an in-loop action raises `PermissionDenied`, Pilota:

1. records a `tool.denied` event,
2. returns the error as an observation,
3. lets the model continue within the remaining budget.

This allows recovery without silently expanding authority.

## Local process execution is not sandboxing

The built-in `Shell` narrows command selection and filesystem working directories. It does not
isolate the child process from the host kernel or network.

Use OS-level isolation when commands themselves are untrusted:

- containers,
- virtual machines,
- restricted service accounts,
- network policies,
- external sandbox services.

Pilota's policy remains useful inside those boundaries, but does not replace them.

## Secrets are a separate concern

Secrets should be injected into provider or tool implementations, not placed in model-visible
inputs. A tool should return only the minimum data needed for the task and should redact sensitive
failure details.
