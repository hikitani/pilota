# Shell tool

`Shell` runs explicitly configured local command aliases inside a process-backed workspace.
It never evaluates a shell command string.

## Configure commands

```python
import sys

from pilota import Shell


shell = Shell(
    {
        "tests": [sys.executable, "-m", "pytest"],
        "format-check": [sys.executable, "-m", "ruff", "format", "--check"],
    },
    timeout=60,
    max_output_chars=20_000,
)
```

The mapping is the authority boundary:

- the caller chooses each alias and fixed command prefix;
- the model sees aliases, not executable paths;
- model-supplied arguments are appended as separate argv values;
- `shell=True` is never used, so shell interpolation and pipelines are unavailable;
- unknown aliases are rejected before process creation.

Prefer narrow command prefixes. Granting a generic interpreter such as `python`, `sh`, or
`bash` lets model-supplied arguments turn it into broad code-execution authority.

## Use with an agent

```python
import os
import sys
from dataclasses import dataclass

from pilota import DirectoryWorkspace, Shell, agent
from pilota.providers.openrouter import OpenRouterModel


@dataclass(frozen=True)
class TestReport:
    summary: str
    passed: bool


workspace = DirectoryWorkspace(
    ".",
    allow={"list", "read", "execute"},
    deny_globs={".env", ".git/**"},
)
shell = Shell({"tests": [sys.executable, "-m", "pytest"]})

with OpenRouterModel(os.environ["OPENROUTER_MODEL"]) as model:
    report = agent(
        "Run the tests and report the result.",
        model=model,
        workspace=workspace,
        tools=[shell],
        returns=TestReport,
    )
```

The workspace must grant `execute` for the requested `cwd`. Relative `cwd` values are
resolved beneath the directory workspace and cannot escape through `..` or symlinks.
Files created or modified by commands are included in the execution artifacts.

See [`examples/openrouter_shell.py`](../examples/openrouter_shell.py) for a complete
executable example.

## Command result

A completed command returns one observation:

```python
{
    "command": "tests",
    "exit_code": 0,
    "stdout": "...",
    "stderr": "",
    "stdout_truncated": False,
    "stderr_truncated": False,
}
```

A nonzero exit code is returned normally so the model can inspect and react to it. Process
startup failures raise `ToolError`; timeouts raise `ToolTimeoutError`. Returned stdout and
stderr are each truncated to `max_output_chars`.

## Environment

Child processes do not inherit the Python process environment. They receive only a minimal
`PATH` plus values explicitly supplied through `environment`:

```python
Shell(
    {"tests": [sys.executable, "-m", "pytest"]},
    environment={"PYTHONUNBUFFERED": "1"},
)
```

Do not put secrets in this mapping. A permitted command can print its environment, and tool
output is visible to the model.

## Security boundary

`DirectoryWorkspace` constrains the working directory selected through the tool request. It
does not sandbox the operating-system process. A permitted executable may still access host
files, the network, child processes, or other operating-system capabilities available to the
current user.

Use the local `Shell` only for trusted command configurations and trusted workspaces. Run
untrusted code in a container, virtual machine, or remote sandbox exposed through a custom
`ProcessWorkspaceHandle`.
