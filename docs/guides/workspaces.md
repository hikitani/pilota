# Work with files and commands

A workspace is the explicit file boundary for tools. It provides file operations, authorization,
snapshots, and artifact detection.

## Use an in-memory workspace

`InMemoryWorkspace` is useful for tests and ephemeral transformations:

```python
from pilota import Editor, InMemoryWorkspace, run_agent

workspace = InMemoryWorkspace(
    {"app.py": "print('old')\n"},
    allow={"list", "read", "edit", "create"},
)

execution = run_agent(
    "Change app.py to print 'new'",
    model=model,
    workspace=workspace,
    tools=[Editor()],
    returns=str,
)

print(workspace.read_text("app.py"))
print(execution.artifacts)
```

## Use a directory workspace

`DirectoryWorkspace` confines paths below a resolved root:

```python
from pilota import DirectoryWorkspace

workspace = DirectoryWorkspace(
    "./project",
    allow={"list", "read", "create", "edit"},
    deny_globs={
        ".env",
        "**/.env",
        ".git/**",
        "**/*.pem",
    },
)
```

Absolute paths and paths containing `..` are rejected. Deny globs apply after path normalization.

## Grant only needed operations

Workspace operations are:

- `list`
- `read`
- `create`
- `edit`
- `delete`
- `execute`

The built-in `Editor` currently uses list, read, create, and edit. The built-in `Shell` requires
`execute`.

```python
readonly = DirectoryWorkspace(
    "./project",
    allow={"list", "read"},
)
```

An attempted write raises `PermissionDenied`; the model receives the denied observation and can
choose another action.

## Run constrained commands

`Shell` exposes aliases, not arbitrary command strings:

```python
import sys

from pilota import DirectoryWorkspace, Shell

workspace = DirectoryWorkspace(
    "./project",
    allow={"read", "execute"},
)

shell = Shell(
    {
        "tests": [sys.executable, "-m", "pytest"],
        "format-check": [sys.executable, "-m", "ruff", "format", "--check"],
    },
    timeout=60,
    max_output_chars=20_000,
)
```

The model may choose an alias, arguments, and a relative working directory. Pilota executes argv
directly without shell interpretation.

!!! warning
    `Shell` is a constrained local process runner, not an operating-system sandbox. The process
    inherits the host's network and OS-level permissions. Use a container or sandbox when the
    subprocess itself is not trusted.

See the [Shell guide](../shell.md) for environment handling, output truncation, and failure modes.

## Inspect artifacts

`run_agent` compares workspace snapshots before and after execution:

```python
execution = run_agent(...)

for artifact in execution.artifacts:
    print(artifact.operation, artifact.path)
```

Artifacts record created, modified, and deleted paths. They are evidence of file changes, not file
contents.
